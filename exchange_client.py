self.base_url = base_url
        self.private_key = private_key
        self.enable_mainnet_trading = enable_mainnet_trading
        self.execution_mode = execution_mode
        self.meta_cache_ttl_sec = meta_cache_ttl_sec
        self.paper_slippage_bps = paper_slippage_bps
        self.info_timeout = info_timeout
        self.exchange_timeout = exchange_timeout

        self.session = _create_robust_session()
        self.account = Account.from_key(self.private_key)
        self._meta_cache: Optional[Dict[str, Any]] = None
        self._meta_cache_at = 0.0
        self._mids_cache: Optional[Dict[str, str]] = None
        self._mids_cache_at = 0.0
        self._mids_cache_ttl = 30  # 30 secondi per prezzi mid

        # Circuit breaker
        self._info_cb = get_or_create_circuit_breaker(
            "hyperliquid_info",
            failure_threshold=5,
            recovery_timeout=30.0
        )
        self._exchange_cb = get_or_create_circuit_breaker(
            "hyperliquid_exchange",
            failure_threshold=3,
            recovery_timeout=60.0
        )

        logger.info(
            f"Client exchange inizializzato: base_url={self.base_url}, "
            f"mode={self.execution_mode}, mainnet={self.enable_mainnet_trading}"
        )

    def _safe_decimal(self, value: Any, default: Decimal = Decimal("0")) -> Decimal:
        return utils_to_decimal(value, default)

    def _post_info(self, payload: Dict[str, Any], timeout: Optional[int] = None) -> Optional[Any]:
        """POST a /info con circuit breaker e sessione robusta."""
        if timeout is None:
            timeout = self.info_timeout

        def _do_post():
            response = self.session.post(
                f"{self.base_url}/info",
                json=payload,
                timeout=timeout
            )
            if response.status_code != 200:
                logger.error(
                    f"/info type={payload.get('type', 'unknown')} "
                    f"fallito status={response.status_code}"
                )
                response.raise_for_status()
            return response.json()

        try:
            return self._info_cb.call(_do_post)
        except CircuitBreakerOpenError:
            logger.error("Circuit breaker OPEN per endpoint /info")
            return None
        except requests.exceptions.Timeout:
            logger.error(f"/info timeout dopo {timeout}s per type={payload.get('type', 'unknown')}")
            return None
        except requests.exceptions.ConnectionError as e:
            logger.error(f"/info errore connessione: {e}")
            return None
        except Exception as e:
            logger.error(f"/info errore imprevisto: {type(e).__name__}: {str(e)}")
            return None

    def _post_exchange(self, payload: Dict[str, Any], timeout: Optional[int] = None) -> Optional[Any]:
        """POST a /exchange con circuit breaker e sessione robusta."""
        if timeout is None:
            timeout = self.exchange_timeout

        def _do_post():
            response = self.session.post(
                f"{self.base_url}/exchange",
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=timeout
            )
            if response.status_code != 200:
                logger.error(f"/exchange fallito status={response.status_code}")
                response.raise_for_status()
            return response.json()

        try:
            return self._exchange_cb.call(_do_post)
        except CircuitBreakerOpenError:
            logger.error("Circuit breaker OPEN per endpoint /exchange")
            return None
        except requests.exceptions.Timeout:
            logger.error(f"/exchange timeout dopo {timeout}s")
            return None
        except requests.exceptions.ConnectionError as e:
            logger.error(f"/exchange errore connessione: {e}")
            return None
        except Exception as e:
            logger.error(f"/exchange errore imprevisto: {type(e).__name__}: {str(e)}")
            return None

    def get_meta(self, force_refresh: bool = False) -> Optional[Dict[str, Any]]:
        now = time.time()
        if not force_refresh and self._meta_cache and (now - self._meta_cache_at) < self.meta_cache_ttl_sec:
            return self._meta_cache

        meta = self._post_info({"type": "meta"})
        if meta is None:
            return self._meta_cache  # Ritorna cache stale se disponibile
        self._meta_cache = meta
        self._meta_cache_at = now
        return meta

    def get_all_mids(self, force_refresh: bool = False) -> Optional[Dict[str, str]]:
        """Ottieni tutti i prezzi mid con caching."""
        now = time.time()
        if not force_refresh and self._mids_cache and (now - self._mids_cache_at) < self._mids_cache_ttl:
            return self._mids_cache

        mids = self._post_info({"type": "allMids"})
        if mids is None:
            return self._mids_cache
        self._mids_cache = mids
        self._mids_cache_at = now
        return mids

    def get_user_state(self, user: str) -> Optional[Dict[str, Any]]:
        return self._post_info({"type": "clearinghouseState", "user": user})

    def get_asset_id(self, coin: str) -> Optional[int]:
        meta = self.get_meta(force_refresh=False)
        if meta is None:
            return None
        for index, asset in enumerate(meta.get("universe", [])):
            if asset.get("name") == coin:
                return index
        return None

    def get_max_leverage(self, coin: str) -> int:
        meta = self.get_meta(force_refresh=False)
        if meta is None:
            return 10
        for asset in meta.get("universe", []):
            if asset.get("name") == coin:
                return int(asset.get("maxLeverage", 10))
        return 10

    def get_reference_price(self, coin: str, fallback_price: Decimal) -> Decimal:
        mids = self.get_all_mids()
        if mids and coin in mids:
            return self._safe_decimal(mids[coin], fallback_price)

        meta = self.get_meta(force_refresh=False)
        if meta is None:
            return fallback_price
        for asset in meta.get("universe", []):
            if asset.get("name") == coin and asset.get("markPx") is not None:
                return self._safe_decimal(asset.get("markPx"))
        return fallback_price

    def get_tick_size_and_precision(self, asset_id: int) -> Tuple[Decimal, int]:
        mids = self.get_all_mids()
        meta = self.get_meta(force_refresh=False)

        if mids is not None and meta is not None:
            universe = meta.get("universe", [])
            if 0 <= asset_id < len(universe):
                coin = universe[asset_id].get("name", "")
                raw_price = str(mids.get(coin, "0"))
                if "." in raw_price:
                    right_side = raw_price.rstrip("0").split(".")[1]
                    decimals = len(right_side) if right_side else 0
                else:
                    decimals = 0
                tick_size = Decimal("1").scaleb(-decimals) if decimals > 0 else Decimal("1")
                return tick_size, decimals

        default_tick_sizes: Dict[int, Tuple[Decimal, int]] = {
            0: (Decimal("0.1"), 1),
            1: (Decimal("0.01"), 2),
            5: (Decimal("0.001"), 3),
            7: (Decimal("0.01"), 2),
            65: (Decimal("0.00001"), 5)
        }
        return default_tick_sizes.get(asset_id, (Decimal("0.01"), 2))

    def _address_to_bytes(self, address: str) -> bytes:
        return bytes.fromhex(address[2:].lower())

    def _action_hash(
        self,
        action: Dict[str, Any],
        vault_address: Optional[str],
        nonce: int,
        expires_after: Optional[int]
    ) -> bytes:
        data = msgpack.packb(action)
        data += nonce.to_bytes(8, "big")
        if vault_address is None:
            data += b"\x00"
        else:
            data += b"\x01"
            data += self._address_to_bytes(vault_address)
        if expires_after is not None:
            data += b"\x00"
            data += expires_after.to_bytes(8, "big")
        return keccak.new(data=data, digest_bits=256).digest()

    def _l1_payload(self, phantom_agent: Dict[str, str]) -> Dict[str, Any]:
        return {
            "domain": {
                "chainId": 1337,
                "name": "Exchange",
                "verifyingContract": "0x0000000000000000000000000000000000000000",
                "version": "1",
            },
            "types": {
                "Agent": [
                    {"name": "source", "type": "string"},
                    {"name": "connectionId", "type": "bytes32"},
                ],
                "EIP712Domain": [
                    {"name": "name", "type": "string"},
                    {"name": "version", "type": "string"},
                    {"name": "chainId", "type": "uint256"},
                    {"name": "verifyingContract", "type": "address"},
                ],
            },
            "primaryType": "Agent",
            "message": phantom_agent,
        }

    def sign_l1_action_exact(
        self,
        action: Dict[str, Any],
        vault_address: Optional[str],
        nonce: int,
        expires_after: Optional[int],
        is_mainnet: bool = True
    ) -> Dict[str, Any]:
        hash_bytes = self._action_hash(action, vault_address, nonce, expires_after)
        phantom_agent = {
            "source": "a" if is_mainnet else "b",
            "connectionId": "0x" + hash_bytes.hex()
        }
        data = self._l1_payload(phantom_agent)
        structured_data = encode_typed_data(full_message=data)
        signed = self.account.sign_message(structured_data)
        return {"r": hex(signed.r), "s": hex(signed.s), "v": signed.v}

    def set_leverage(self, coin: str, leverage: int) -> bool:
        leverage = max(1, leverage)
        max_leverage = self.get_max_leverage(coin)
        if leverage > max_leverage:
            leverage = max_leverage

        if self.execution_mode != "live" or not self.enable_mainnet_trading:
            logger.info(f"PAPER leverage impostato {coin} -> {leverage}x")
            return True

        asset_id = self.get_asset_id(coin)
        if asset_id is None:
            logger.error(f"ID asset non trovato per {coin}")
            return False

        action = {
            "type": "updateLeverage",
            "asset": asset_id,
            "isCross": True,
            "leverage": leverage
        }
        nonce = int(time.time() * 1000)
        signature = self.sign_l1_action_exact(action, None, nonce, None, True)
        payload = {
            "action": action,
            "nonce": nonce,
            "signature": signature,
            "vaultAddress": None
        }

        result = self._post_exchange(payload)
        if result is None:
            return False
        if result.get("status") == "ok":
            logger.info(f"LIVE leverage impostato {coin} -> {leverage}x")
            return True

        logger.error(f"Impostazione leverage fallita per {coin}: {result}")
        return False

    def place_order(
        self,
        coin: str,
        side: str,
        size: Decimal,
        desired_price: Decimal
    ) -> Dict[str, Any]:
        if self.execution_mode != "live" or not self.enable_mainnet_trading:
            slip = (self.paper_slippage_bps / Decimal("10000"))
            fill_price = desired_price * (Decimal("1") + slip if side.lower() == "buy" else Decimal("1") - slip)
            notional = abs(size * fill_price)
            logger.info(f"PAPER ordine {coin} {side.upper()} size={size} fill={fill_price}")
            return {
                "success": True,
                "mode": "paper",
                "filled_price": str(fill_price),
                "notional": str(notional)
            }

        asset_id = self.get_asset_id(coin)
        if asset_id is None:
            logger.error(f"ID asset non trovato per {coin}")
            return {"success": False, "mode": "live", "reason": "asset_not_found", "notional": "0"}

        is_buy = side.lower() == "buy"
        reference_price = self.get_reference_price(coin, desired_price)
        max_deviation = reference_price * Decimal("0.05")
        if is_buy:
            limit_price = min(desired_price, reference_price + (max_deviation * Decimal("0.5")))
        else:
            limit_price = max(desired_price, reference_price - (max_deviation * Decimal("0.5")))

        lower_bound = reference_price - max_deviation
        upper_bound = reference_price + max_deviation
        if limit_price < lower_bound:
            limit_price = lower_bound
        if limit_price > upper_bound:
            limit_price = upper_bound

        tick_size, precision = self.get_tick_size_and_precision(asset_id)
        rounded_ticks = (limit_price / tick_size).quantize(Decimal("1"))
        limit_price = rounded_ticks * tick_size
        quantizer = Decimal("1").scaleb(-precision)
        limit_price = limit_price.quantize(quantizer)

        size_str = str(size.normalize())

        order_wire = {
            "a": asset_id,
            "b": is_buy,
            "p": str(limit_price),
            "s": size_str,
            "r": False,
            "t": {"limit": {"tif": "Gtc"}}
        }

        action = {"type": "order", "orders": [order_wire], "grouping": "na"}
        nonce = int(time.time() * 1000)
        signature = self.sign_l1_action_exact(action, None, nonce, None, True)

        payload = {
            "action": action,
            "nonce": nonce,
            "signature": signature,
            "vaultAddress": None
        }

        result = self._post_exchange(payload)
        if result is None:
            return {"success": False, "mode": "live", "reason": "http_error", "notional": "0"}
        if result.get("status") != "ok":
            logger.error(f"Exchange ha rifiutato ordine per {coin}: {result}")
            return {"success": False, "mode": "live", "reason": "exchange_rejected", "notional": "0"}

        statuses = result.get("response", {}).get("data", {}).get("statuses", [])
        for status in statuses:
            if "error" in status:
                logger.error(f"Stato ordine errore per {coin}: {status}")
                return {"success": False, "mode": "live", "reason": "status_error", "notional": "0"}

        notional = abs(size * limit_price)
        logger.info(f"LIVE ordine successo {coin} {side.upper()} size={size_str} limit={limit_price}")
        return {
            "success": True,
            "mode": "live",
            "filled_price": str(limit_price),
            "notional": str(notional)
        }