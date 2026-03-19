f"Adaptive cycle: {self._next_cycle_sec}s -> {clamped}s "
                f"(volatility={vol_signal.get('volatility_level', 'unknown')})"
            )

        return clamped

    def _log_performance_summary(self, state: Dict[str, Any]):
        summary = self.state_store.get_performance_summary(state)
        if summary["total_trades"] > 0:
            logging.info(
                f"Performance: {summary['total_trades']} trade, "
                f"win_rate={summary['win_rate']:.1f}%, "
                f"wins={summary['wins']}, losses={summary['losses']}, "
                f"holds={summary['holds']}, "
                f"consecutive_losses={summary['consecutive_losses']}"
            )

    def _persist_metrics(self):
        metrics_data = self.metrics.get_all_metrics()
        serializable = {}
        for key, value in metrics_data.items():
            if isinstance(value, Decimal):
                serializable[key] = str(value)
            elif isinstance(value, list):
                serializable[key] = [float(v) if isinstance(v, (Decimal, float)) else v for v in value]
            else:
                serializable[key] = value
        self.state_store.save_metrics(serializable)

    def _run_trading_cycle(self) -> bool:
        cycle_start = time.time()
        self._cycle_count += 1
        success = True

        try:
            logging.info("=" * 60)
            logging.info(f"Avvio ciclo trading #{self._cycle_count}")

            portfolio_state = self._get_portfolio_state()
            self._last_portfolio_state = portfolio_state

            logging.info(
                f"Portfolio: balance=${portfolio_state.total_balance}, "
                f"available=${portfolio_state.available_balance}, "
                f"margin_usage={float(portfolio_state.margin_usage) * 100:.1f}%, "
                f"positions={len(portfolio_state.positions)}, "
                f"unrealized_pnl=${portfolio_state.get_total_unrealized_pnl()}"
            )

            write_live_status(
                is_running=True, execution_mode=EXECUTION_MODE,
                cycle_count=self._cycle_count, last_cycle_duration=self._last_cycle_duration,
                portfolio=portfolio_state, current_coin="scanning..."
            )

            if portfolio_state.total_balance <= 0:
                logging.warning("Saldo portfolio zero o negativo, skip ciclo")
                return True

            state = self.state_store.load_state()
            daily_notional_used = self._get_daily_notional_used(state)
            peak = Decimal(str(state.get("peak_portfolio_value", "0")))
            consecutive_losses = state.get("consecutive_losses", 0)

            # === FASE 1: Controllo SL/TP/Trailing Stop ===
            sl_tp_triggered = self._process_sl_tp_trailing(portfolio_state)
            if sl_tp_triggered > 0:
                logging.info(f"SL/TP/Trailing attivati {sl_tp_triggered} chiusure, refresh portfolio")
                portfolio_state = self._get_portfolio_state()
                self._last_portfolio_state = portfolio_state

            # === FASE 2: De-risk emergenza ===
            if self.risk_manager.check_emergency_derisk(portfolio_state):
                logging.warning("EMERGENZA: Uso margine critico, tentativo de-risk")
                self._handle_emergency_derisk(portfolio_state)
                portfolio_state = self._get_portfolio_state()
                self._last_portfolio_state = portfolio_state

            # === FASE 3: Analisi correlazione ===
            correlations = self.correlation_engine.calculate_correlations(TRADING_PAIRS, "1h", 50)
            corr_summary = self.correlation_engine.get_correlation_summary(correlations)
            if corr_summary["high_correlation_pairs"]:
                logging.info(f"Coppie correlazione alta: {corr_summary['high_correlation_pairs'][:3]}")

            # Ottieni tutti prezzi mid e trade recenti
            all_mids = technical_fetcher.get_all_mids()
            recent_trades = self.state_store.get_recent_trades(state, count=5)

            trades_executed = 0

            for coin in TRADING_PAIRS:
                if self._shutdown_requested:
                    logging.info("Shutdown richiesto, stop analisi coin")
                    break
                if trades_executed >= MAX_TRADES_PER_CYCLE:
                    logging.info(f"Max trade per ciclo ({MAX_TRADES_PER_CYCLE}) raggiunto")
                    break

                logging.info(f"--- Analisi {coin} ---")
                write_live_status(
                    is_running=True, execution_mode=EXECUTION_MODE,
                    cycle_count=self._cycle_count, last_cycle_duration=self._last_cycle_duration,
                    portfolio=portfolio_state, current_coin=coin
                )

                market_data, tech_data = self._get_market_data_and_technicals(coin)
                if not market_data:
                    logging.warning(f"Skip {coin}: nessun dato mercato")
                    continue

                # Log allineamento multi-timeframe
                trends_aligned = tech_data.get("trends_aligned", False)
                intraday_trend = tech_data.get("intraday_trend", "unknown")
                hourly_ctx = tech_data.get("hourly_context", {})
                hourly_trend = hourly_ctx.get("trend", "unknown")

                logging.info(
                    f"{coin}: price=${market_data.last_price}, "
                    f"RSI14={float(tech_data.get('current_rsi_14', 50)):.1f}, "
                    f"BB={float(tech_data.get('bb_position', 0.5)):.2f}, "
                    f"vol_ratio={float(tech_data.get('volume_ratio', 1)):.2f}, "
                    f"trends={'ALLINEATI' if trends_aligned else 'DIVERGENTI'} "
                    f"(5m={intraday_trend}, 1h={hourly_trend})"
                )

                funding_data = technical_fetcher.get_funding_for_coin(coin)

                # === Controllo correlazione rischio ===
                corr_ok, corr_reason = self.correlation_engine.check_correlation_risk(
                    coin, "buy", portfolio_state.positions, correlations
                )
                if not corr_ok:
                    logging.info(f"{coin} rischio correlazione: {corr_reason}")

                # Ottieni decisione da LLM
                if self.llm_engine:
                    self.metrics.increment("llm_calls_total")
                    decision = self.llm_engine.get_trading_decision(
                        market_data=market_data,
                        portfolio_state=portfolio_state,
                        technical_data=tech_data,
                        all_mids=all_mids,
                        funding_data=funding_data,
                        recent_trades=recent_trades,
                        peak_portfolio_value=peak,
                        consecutive_losses=consecutive_losses
                    )
                    if not decision:
                        self.metrics.increment("llm_errors_total")
                        decision = self._get_fallback_decision()
                        logging.warning(f"LLM fallito per {coin}, uso fallback")
                else:
                    decision = self._get_fallback_decision()

                logging.info(
                    f"{coin} decisione: action={decision['action']}, "
                    f"size={decision['size']}, leverage={decision['leverage']}, "
                    f"confidence={decision['confidence']}"
                )

                # === Gate rischio correlazione ===
                if not corr_ok and decision["action"] in ["buy", "sell", "increase_position"]:
                    logging.info(f"{coin} bloccato da rischio correlazione: {corr_reason}")
                    self.metrics.increment("risk_rejections_total")
                    continue

                # Controllo rischio
                volatility = Decimal("0")
                if tech_data and tech_data.get("intraday_atr", Decimal("0")) > 0 and market_data.last_price > 0:
                    volatility = tech_data["intraday_atr"] / market_data.last_price

                risk_ok, risk_reason = self.risk_manager.check_order(
                    coin, decision, market_data.last_price, portfolio_state,
                    state.get("last_trade_timestamp_by_coin", {}),
                    daily_notional_used, time.time(), volatility, peak
                )

                if not risk_ok:
                    logging.info(f"{coin} rischio rifiutato: {risk_reason}")
                    self.metrics.increment("risk_rejections_total")
                    continue

                # === Snapshot prima ordine (per verifica fill) ===
                snapshot = None
                if EXECUTION_MODE == "live" and ENABLE_MAINNET_TRADING:
                    snapshot = self.order_verifier.snapshot_position(self.wallet_address, coin)

                # Esegui
                result = self.execution_engine.execute(
                    coin, decision, market_data, portfolio_state.positions
                )

                # === Verifica fill (solo modalità live) ===
                fill_status = "unknown"
                if snapshot and result["success"] and decision["action"] in ["buy", "sell", "increase_position"]:
                    expected_side = "buy" if decision["action"] in ["buy", "increase_position"] else "sell"
                    verification = self.order_verifier.verify_fill(
                        self.wallet_address, coin, expected_side,
                        Decimal(str(decision["size"])), snapshot
                    )
                    fill_status = verification.get("fill_status", "unknown")
                    if fill_status == "not_filled":
                        logging.warning(f"{coin} ordine NON RIEMPITO — marco come fallito")
                        result["success"] = False
                        result["reason"] = "order_not_filled"

                # Registra trade
                trade_record = {
                    "timestamp": time.time(),
                    "coin": coin,
                    "action": decision["action"],
                    "size": str(decision["size"]),
                    "price": str(market_data.last_price),
                    "notional": str(result.get("notional", "0")),
                    "leverage": decision["leverage"],
                    "confidence": decision["confidence"],
                    "reasoning": decision.get("reasoning", "")[:200],
                    "success": result["success"],
                    "mode": EXECUTION_MODE,
                    "trigger": "ai",
                    "order_status": fill_status,
                }
                self.state_store.add_trade_record(state, trade_record)

                if result["success"]:
                    notional = Decimal(str(result["notional"]))
                    if notional > 0:
                        trades_executed += 1
                        daily_notional_used += notional
                        state.setdefault("last_trade_timestamp_by_coin", {})[coin] = time.time()
                        self.metrics.increment("trades_executed_total")
                        state["consecutive_losses"] = 0

                        # Registra con position manager per tracking SL/TP
                        if decision["action"] in ["buy", "sell", "increase_position"]:
                            is_long = decision["action"] in ["buy", "increase_position"]
                            self.position_manager.register_position(
                                coin=coin,
                                size=Decimal(str(decision["size"])),
                                entry_price=market_data.last_price,
                                is_long=is_long,
                                leverage=decision["leverage"],
                            )

                        # Notifica via Telegram
                        self.notifier.notify_trade(trade_record)

                        logging.info(f"{coin} eseguito: reason={result['reason']}, notional=${notional}")
                    else:
                        self.metrics.increment("holds_total")
                        logging.info(f"{coin}: hold (nessun trade)")
                else:
                    self.metrics.increment("execution_failures_total")
                    state["consecutive_losses"] = state.get("consecutive_losses", 0) + 1
                    logging.warning(f"{coin} esecuzione fallita: {result.get('reason', 'unknown')}")

            # Aggiorna stato
            state["daily_notional_by_day"] = self.state_store.add_daily_notional(
                state.get("daily_notional_by_day", {}),
                time.time(),
                daily_notional_used - self._get_daily_notional_used(state)
            )

            if portfolio_state.total_balance > peak:
                state["peak_portfolio_value"] = str(portfolio_state.total_balance)
                self.metrics.set_gauge("peak_portfolio_value", portfolio_state.total_balance)

            state["consecutive_failed_cycles"] = 0
            self.state_store.save_state(state)

            cycle_duration = time.time() - cycle_start
            self._last_cycle_duration = cycle_duration
            self.metrics.record_histogram("cycle_duration_seconds", cycle_duration)
            self.metrics.increment("cycles_total")
            self._persist_metrics()
            self._log_performance_summary(state)

            # Timing ciclo adattivo
            self._next_cycle_sec = self._calculate_adaptive_cycle()

            write_live_status(
                is_running=True, execution_mode=EXECUTION_MODE,
                cycle_count=self._cycle_count, last_cycle_duration=cycle_duration,
                portfolio=portfolio_state, current_coin="idle"
            )

            logging.info(
                f"Ciclo #{self._cycle_count} completo: {trades_executed} trade, "
                f"duration={cycle_duration:.1f}s, next_cycle={self._next_cycle_sec}s"
            )

        except Exception as e:
            logging.error(f"Ciclo fallito: {type(e).__name__}: {e}", exc_info=True)
            success = False
            self.metrics.increment("cycles_failed")
            self.notifier.notify_error(f"Ciclo fallito: {type(e).__name__}: {str(e)[:200]}")

            write_live_status(
                is_running=True, execution_mode=EXECUTION_MODE,
                cycle_count=self._cycle_count, last_cycle_duration=self._last_cycle_duration,
                portfolio=self._last_portfolio_state,
                error=f"{type(e).__name__}: {str(e)[:200]}"
            )

            state = self.state_store.load_state()
            state["consecutive_failed_cycles"] = state.get("consecutive_failed_cycles", 0) + 1
            self.state_store.save_state(state)

        return success

    def run(self, single_cycle: bool = False):
        logging.info("=" * 60)
        logging.info("BOT TRADING HYPERLIQUID AVVIATO")
        logging.info("=" * 60)
        logging.info(f"Wallet: {self._mask_wallet(self.wallet_address)}")
        logging.info(f"Modalità esecuzione: {EXECUTION_MODE}")
        logging.info(f"Trading mainnet: {ENABLE_MAINNET_TRADING}")
        logging.info(f"Modello LLM: {LLM_MODEL}")
        logging.info(f"Coppie trading: {TRADING_PAIRS}")
        logging.info(f"Strategia: R:R Asimmetrico — SL {float(DEFAULT_SL_PCT)*100}% / TP {float(DEFAULT_TP_PCT)*100}% / Trailing {float(DEFAULT_TRAILING_CALLBACK)*100}%")
        logging.info(f"Soglia confidenza: open={MIN_CONFIDENCE_OPEN} manage={MIN_CONFIDENCE_MANAGE}")
        logging.info(f"Ciclo adattivo: {ENABLE_ADAPTIVE_CYCLE} ({MIN_CYCLE_SEC}-{MAX_CYCLE_SEC}s)")
        logging.info(f"Soglia correlazione: {CORRELATION_THRESHOLD}")
        logging.info(f"Drawdown massimo: {float(MAX_DRAWDOWN_PCT)*100}%")
        logging.info(f"Telegram: {'abilitato' if self.notifier.telegram_enabled else 'disabilitato'}")
        logging.info("=" * 60)

        self.notifier.notify_bot_started(EXECUTION_MODE, TRADING_PAIRS)

        write_live_status(
            is_running=True, execution_mode=EXECUTION_MODE,
            cycle_count=0, last_cycle_duration=0.0, current_coin="starting..."
        )

        meta = self.exchange_client.get_meta(force_refresh=True)
        if meta:
            logging.info(f"Hyperliquid connesso: {len(meta.get('universe', []))} asset disponibili")
        else:
            logging.error("FAILED to connect to Hyperliquid API at startup!")
            self.notifier.notify_error("Failed to connect to Hyperliquid API at startup")
            if not single_cycle:
                write_live_status(
                    is_running=False, execution_mode=EXECUTION_MODE,
                    cycle_count=0, last_cycle_duration=0.0,
                    error="Failed to connect to Hyperliquid API"
                )
                return

        consecutive_failures = 0

        while not self._shutdown_requested:
            if self._run_trading_cycle():
                consecutive_failures = 0
            else:
                consecutive_failures += 1
                logging.warning(f"Fallimenti consecutivi: {consecutive_failures}/{MAX_CONSECUTIVE_FAILED_CYCLES}")
                if consecutive_failures >= MAX_CONSECUTIVE_FAILED_CYCLES:
                    logging.error("Troppi fallimenti consecutivi, shutdown")
                    self.notifier.notify_error(f"Bot shutdown: {consecutive_failures} fallimenti consecutivi")
                    break

            if single_cycle:
                logging.info("Modalità ciclo singolo: uscita")
                break

            # Attesa interrompibile adattiva
            wait_sec = self._next_cycle_sec
            logging.info(f"Attesa {wait_sec} secondi prima prossimo ciclo...")
            for _ in range(wait_sec):
                if self._shutdown_requested:
                    break
                time.sleep(1)

        # Shutdown graceful
        logging.info("=" * 60)
        logging.info("BOT SHUTDOWN GRACEFUL")
        state = self.state_store.load_state()
        self._log_performance_summary(state)
        self.state_store.save_state(state)
        self._persist_metrics()
        self.notifier.notify_bot_stopped("graceful_shutdown")
        write_live_status(
            is_running=False, execution_mode=EXECUTION_MODE,
            cycle_count=self._cycle_count, last_cycle_duration=self._last_cycle_duration,
            portfolio=self._last_portfolio_state, current_coin="stopped"
        )
        logging.info("Stato salvato. Arrivederci.")
        logging.info("=" * 60)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Bot Trading Hyperliquid - Claude Opus 4.6")
    parser.add_argument("--single-cycle", action="store_true", help="Esegui singolo ciclo ed esci")
    args = parser.parse_args()

    bot = HyperliquidBot()
    bot.run(single_cycle=args.single_cycle)


if __name__ == "__main__":
    main()