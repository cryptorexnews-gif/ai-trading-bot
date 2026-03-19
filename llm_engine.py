import json
import logging
import os
import re
import time
from decimal import Decimal
from typing import Any, Dict, List, Optional

import requests

from models import MarketData, PortfolioState, TradingAction

logger = logging.getLogger(__name__)

# Codici stato che sono retryable
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class LLMEngine:
    """
    Engine LLM usando Claude Opus 4.6 via OpenRouter per decisioni di trading.
    Tutti i dati di mercato vengono dall'API Hyperliquid; nessuna fonte dati esterna.
    Prompt ottimizzato per redditività asimmetrica rischio/ricompensa.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://openrouter.ai/api/v1",
        model: str = "anthropic/claude-opus-4.6",
        max_tokens: int = 8192,
        temperature: float = 0.15
    ):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.request_timeout = 120
        self.max_retries = 2
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/hyperliquid-trading-bot",
            "X-Title": "Hyperliquid Trading Bot"
        })
        logger.info(f"Engine LLM inizializzato con modello={self.model}, timeout={self.request_timeout}s")

    def _format_positions(self, positions: Dict[str, Dict[str, Any]]) -> str:
        if not positions:
            return "  Nessuna posizione aperta."
        lines = []
        for coin, pos in positions.items():
            size = pos.get("size", 0)
            entry_px = pos.get("entry_price", 0)
            pnl = pos.get("unrealized_pnl", 0)
            side = "LONG" if Decimal(str(size)) > 0 else "SHORT"
            margin = pos.get("margin_used", "N/A")
            # Calcola PnL percentuale
            entry_d = Decimal(str(entry_px))
            pnl_d = Decimal(str(pnl))
            size_d = abs(Decimal(str(size)))
            pnl_pct = (pnl_d / (size_d * entry_d) * Decimal("100")) if (size_d * entry_d) > 0 else Decimal("0")
            lines.append(
                f"  - {coin}: {side} | Dimensione: {size} | Entrata: ${entry_px} | "
                f"PnL: ${pnl} ({float(pnl_pct):+.2f}%) | Margine: ${margin}"
            )
        return "\n".join(lines)

    def _format_technical_data(self, technical_data: Optional[Dict[str, Any]]) -> str:
        if not technical_data:
            return "  Nessun dato tecnico disponibile."
        key_indicators = [
            "current_price", "change_24h", "volume_24h", "funding_rate",
            "open_interest", "vwap", "volume_ratio", "bb_position",
            "current_ema9", "current_ema20",
            "current_macd", "current_macd_signal", "current_macd_histogram",
            "current_rsi_7", "current_rsi_14",
            "intraday_atr", "bollinger_upper", "bollinger_middle", "bollinger_lower"
        ]
        lines = []
        for key in key_indicators:
            value = technical_data.get(key)
            if value is None:
                continue
            if isinstance(value, Decimal):
                lines.append(f"  {key}: {float(value):.6f}")
            else:
                lines.append(f"  {key}: {value}")

        # Contesto multi-timeframe
        lines.append(f"  intraday_trend (5m): {technical_data.get('intraday_trend', 'unknown')}")
        lines.append(f"  trends_aligned (5m+1h+4h): {technical_data.get('trends_aligned', False)}")

        # Contesto hourly
        hourly = technical_data.get("hourly_context", {})
        if hourly:
            lines.append("  hourly_context (1h):")
            for sub_key in ["ema_9", "ema_20", "rsi_14", "macd", "macd_signal", "atr_14", "trend"]:
                sub_value = hourly.get(sub_key)
                if sub_value is not None:
                    val_str = f"{float(sub_value):.6f}" if isinstance(sub_value, Decimal) else str(sub_value)
                    lines.append(f"    {sub_key}: {val_str}")
            rsi_trend = hourly.get("rsi_trend", [])
            if rsi_trend:
                formatted = [f"{float(v):.2f}" if isinstance(v, Decimal) else str(v) for v in rsi_trend]
                lines.append(f"    rsi_trend: [{', '.join(formatted)}]")

        # Contesto long-term
        lt = technical_data.get("long_term_context", {})
        if lt:
            lines.append(f"  long_term_trend (4h): {lt.get('trend', 'unknown')}")
            for sub_key in ["ema_20", "ema_50", "atr_14", "current_volume", "avg_volume"]:
                sub_value = lt.get(sub_key)
                if sub_value is not None:
                    val_str = f"{float(sub_value):.6f}" if isinstance(sub_value, Decimal) else str(sub_value)
                    lines.append(f"    {sub_key}: {val_str}")
            rsi_list = lt.get("rsi_14", [])
            if rsi_list:
                last_3 = rsi_list[-3:]
                formatted = [f"{float(v):.2f}" if isinstance(v, Decimal) else str(v) for v in last_3]
                lines.append(f"    rsi_14_trend: [{', '.join(formatted)}]")

        return "\n".join(lines)

    def _format_recent_trades(self, recent_trades: List[Dict[str, Any]]) -> str:
        if not recent_trades:
            return "  Nessun trade recente."
        lines = []
        for trade in recent_trades[-5:]:
            success_str = "✓" if trade.get("success") else "✗"
            trigger = trade.get("trigger", "ai")
            lines.append(
                f"  - [{success_str}] {trade.get('coin', '?')} {trade.get('action', '?')} "
                f"dimensione={trade.get('size', '?')} @ ${trade.get('price', '?')} "
                f"conf={trade.get('confidence', '?')} trigger={trigger} "
                f"({trade.get('reasoning', '')[:60]})"
            )
        return "\n".join(lines)

    def _build_prompt(
        self,
        market_data: MarketData,
        portfolio_state: PortfolioState,
        technical_data: Optional[Dict[str, Any]] = None,
        all_mids: Optional[Dict[str, str]] = None,
        funding_data: Optional[Dict[str, Any]] = None,
        recent_trades: Optional[List[Dict[str, Any]]] = None,
        peak_portfolio_value: Decimal = Decimal("0"),
        consecutive_losses: int = 0
    ) -> str:

        all_mids_section = ""
        if all_mids:
            top_coins = ["BTC", "ETH", "SOL", "BNB", "ADA", "DOGE", "XRP", "AVAX"]
            mid_lines = []
            for coin in top_coins:
                if coin in all_mids:
                    mid_lines.append(f"  {coin}: ${all_mids[coin]}")
            if mid_lines:
                all_mids_section = "PANORAMICA MERCATO (Prezzi Mid Hyperliquid):\n" + "\n".join(mid_lines)

        funding_section = ""
        if funding_data:
            funding_section = f"""
DATI FUNDING (da Hyperliquid):
  Tasso Funding Corrente: {funding_data.get('funding_rate', 'N/A')}
  Interesse Aperto: {funding_data.get('open_interest', 'N/A')}
  Premium: {funding_data.get('premium', 'N/A')}"""

        drawdown_section = ""
        if peak_portfolio_value > 0:
            current_dd = (peak_portfolio_value - portfolio_state.total_balance) / peak_portfolio_value
            drawdown_section = f"""
CONTESTO RISCHIO:
  Valore Portfolio di Picco: ${peak_portfolio_value}
  Drawdown Corrente: {float(current_dd) * 100:.2f}%
  Drawdown Massimo Consentito: 12%
  Trade Perdenti Consecutivi: {consecutive_losses}"""

        total_exposure = portfolio_state.get_total_exposure()
        total_pnl = portfolio_state.get_total_unrealized_pnl()

        recent_trades_section = ""
        if recent_trades:
            recent_trades_section = f"""
STORIA TRADE RECENTE (ultimi 5):
{self._format_recent_trades(recent_trades)}"""

        # Determina allineamento trend per enfasi
        trends_aligned = technical_data.get("trends_aligned", False) if technical_data else False
        alignment_note = ""
        if trends_aligned:
            alignment_note = "\n⚡ TUTTI I TIMEFRAME ALLINEATI — aperture ad alta confidenza appropriate."
        else:
            alignment_note = "\n⚠️ TIMEFRAME DIVERGENTI — preferisci dimensioni più piccole o hold se non c'è forte edge."

        prompt = f"""Sei un trader di criptovalute d'élite su exchange Hyperliquid, ottimizzato per CONSISTENTE PROFITTABILITÀ con rischio/ricompensa asimmetrico.
TUTTI i dati sotto vengono direttamente dall'API Hyperliquid. Prendi la tua decisione basandoti SOLO su questi dati.

{all_mids_section}

ASSET TARGET: {market_data.coin}
  Prezzo Corrente: ${market_data.last_price}
  Cambiamento 24h: {float(market_data.change_24h) * 100:.4f}%
  Volume 24h: ${float(market_data.volume_24h):,.2f}
  Tasso Funding: {float(market_data.funding_rate):.6f}%
{funding_section}

INDICATORI TECNICI (da candele Hyperliquid — multi-timeframe):
{self._format_technical_data(technical_data)}
{alignment_note}

STATO PORTFOLIO:
  Saldo Totale: ${portfolio_state.total_balance}
  Saldo Disponibile: ${portfolio_state.available_balance}
  Uso Margine: {float(portfolio_state.margin_usage) * 100:.2f}%
  Esposizione Totale: ${total_exposure}
  PnL Non Realizzato Totale: ${total_pnl}
  Posizioni Aperte: {len(portfolio_state.positions)}
{drawdown_section}

POSIZIONI CORRENTI:
{self._format_positions(portfolio_state.positions)}
{recent_trades_section}

=== REGOLE STRATEGIA (SEGUI STRETTAMENTE) ===

CRITERI APERTURA — Apri nuove posizioni solo quando:
1. Confluenza multi-timeframe: Almeno 2 di 3 timeframe (5m, 1h, 4h) concordano su direzione
2. Conferma RSI: RSI-14 tra 30-45 per long (rimbalzo oversold), 55-70 per short (rifiuto overbought)
3. Conferma volume: volume_ratio > 1.2 (sopra volume medio conferma mossa)
4. Allineamento MACD: direzione istogramma corrisponde direzione trade
5. Posizione Bollinger: bb_position < 0.3 per long (vicino banda inferiore), > 0.7 per short (vicino banda superiore)
6. VWAP: Prezzo sotto VWAP per long (sconto), sopra VWAP per short (premium)

GESTIONE POSIZIONE:
- Rapporto rischio/ricompensa minimo 1:3 (SL 2%, TP 6%) — il bot gestisce SL/TP automaticamente
- Se una posizione è profittevole > 3%, considera lasciare trailing stop gestire
- Se una posizione sta perdendo > 1.5%, considera chiudere presto se tecnici si sono girati contro
- Chiudi posizioni quando tesi originale è invalidata (inversione trend su 1h)
- Riduci posizione se uso margine > 60%

REGOLE DIMENSIONAMENTO:
- Dimensioni minime: BTC 0.001, ETH 0.001, SOL 0.1, BNB 0.001, ADA 16.0
- Usa leverage 3-7x per trade ad alta confidenza (tutti timeframe allineati)
- Usa leverage 2-4x per trade a media confidenza
- Non superare mai 10x leverage
- Max 40% del saldo su singolo asset

REGOLE CRITICHE:
- NON aprire BUY se già SHORT sullo stesso asset (chiudi prima)
- NON aprire SELL se già LONG sullo stesso asset (chiudi prima)
- Se drawdown > 8%, SOLO consenti close_position o reduce_position o hold
- Se perdite consecutive > 3, DEVI rispondere con "hold" a meno che non stai chiudendo posizione perdente
- Se tasso funding è estremo (> 0.01% o < -0.01%), fattorizzalo nel bias direzione
- Funding negativo = short pagano long = pressione rialzista
- Funding positivo = long pagano short = pressione ribassista
- Se non c'è chiaro edge esistente, SEMPRE hold — preservazione capitale è prioritaria #1

SCORING CONFIDENZA:
- 0.85-1.0: Tutti timeframe allineati + volume forte + segnale RSI chiaro
- 0.72-0.84: 2/3 timeframe allineati + volume decente
- 0.50-0.71: Segnali misti — solo per gestire posizioni esistenti
- Sotto 0.50: Hold

Rispondi con SOLO questo JSON (nessun markdown, nessun testo extra):
{{
  "action": "buy|sell|hold|close_position|increase_position|reduce_position|change_leverage",
  "size": 0.001,
  "leverage": 5,
  "confidence": 0.75,
  "reasoning": "Analisi concisa: [allineamento timeframe] + [indicatore chiave] + [valutazione rischio/ricompensa]"
}}"""
        return prompt.strip()

    def _parse_llm_response(self, response_text: str) -> Optional[Dict[str, Any]]:
        cleaned = response_text.strip()

        # Strategia 1: Parse JSON diretto
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        # Strategia 2: Estrazione da blocchi codice markdown
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', cleaned, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Strategia 3: Trova primo oggetto JSON completo con matching parentesi graffe
        start = cleaned.find('{')
        if start != -1:
            depth = 0
            for i in range(start, len(cleaned)):
                if cleaned[i] == '{':
                    depth += 1
                elif cleaned[i] == '}':
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(cleaned[start:i + 1])
                        except json.JSONDecodeError:
                            break

        # Strategia 4: Regex estrazione di campi individuali
        try:
            action_match = re.search(r'"action"\s*:\s*"([^"]+)"', cleaned)
            size_match = re.search(r'"size"\s*:\s*([\d.]+)', cleaned)
            leverage_match = re.search(r'"leverage"\s*:\s*(\d+)', cleaned)
            confidence_match = re.search(r'"confidence"\s*:\s*([\d.]+)', cleaned)
            reasoning_match = re.search(r'"reasoning"\s*:\s*"([^"]*(?:\\.[^"]*)*)"', cleaned)

            if action_match and size_match and leverage_match and confidence_match:
                return {
                    "action": action_match.group(1),
                    "size": float(size_match.group(1)),
                    "leverage": int(leverage_match.group(1)),
                    "confidence": float(confidence_match.group(1)),
                    "reasoning": reasoning_match.group(1) if reasoning_match else "Estratto da risposta parziale"
                }
        except (ValueError, AttributeError):
            pass

        logger.error(f"Tutte le strategie parse JSON fallite. Anteprima risposta: {cleaned[:500]}...")
        return None

    def _validate_decision(self, parsed: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        required_keys = ["action", "size", "leverage", "confidence", "reasoning"]
        if not all(key in parsed for key in required_keys):
            missing = [k for k in required_keys if k not in parsed]
            logger.error(f"Risposta LLM manca chiavi: {missing}")
            return None

        action = str(parsed["action"]).strip().lower()
        valid_actions = {a.value for a in TradingAction}
        if action not in valid_actions:
            logger.warning(f"Azione invalida da LLM: '{action}'. Default a hold.")
            return {
                "action": "hold",
                "size": Decimal("0"),
                "leverage": 1,
                "confidence": 0.0,
                "reasoning": f"Azione originale '{action}' invalida, default a hold."
            }

        confidence = float(parsed.get("confidence", 0))
        if not (0.0 <= confidence <= 1.0):
            confidence = max(0.0, min(1.0, confidence))
            logger.warning(f"Confidence clamped a {confidence}")

        leverage = int(parsed.get("leverage", 1))
        if leverage < 1:
            leverage = 1
        if leverage > 50:
            leverage = 50

        size = Decimal(str(parsed.get("size", 0)))
        if size < 0:
            size = Decimal("0")

        return {
            "action": action,
            "size": size,
            "leverage": leverage,
            "confidence": confidence,
            "reasoning": str(parsed.get("reasoning", ""))
        }

    def _call_openrouter(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        last_error = None

       <dyad-write path="risk_manager.py">
import logging
from decimal import Decimal
from typing import Any, Dict, Tuple

from models import PortfolioState, PositionSide, TradingAction

logger = logging.getLogger(__name__)


class RiskManager:
    def __init__(
        self,
        min_size_by_coin: Dict[str, Decimal],
        hard_max_leverage: Decimal,
        min_confidence_open: Decimal,
        min_confidence_manage: Decimal,
        max_margin_usage: Decimal,
        max_order_margin_pct: Decimal,
        trade_cooldown_sec: int,
        daily_notional_limit_usd: Decimal,
        volatility_multiplier: Decimal = Decimal("1.2"),
        max_drawdown_pct: Decimal = Decimal("0.12"),
        max_single_asset_pct: Decimal = Decimal("0.35"),
        emergency_margin_threshold: Decimal = Decimal("0.88")
    ):
        self.min_size_by_coin = min_size_by_coin
        self.hard_max_leverage = hard_max_leverage
        self.min_confidence_open = min_confidence_open
        self.min_confidence_manage = min_confidence_manage
        self.max_margin_usage = max_margin_usage
        self.max_order_margin_pct = max_order_margin_pct
        self.trade_cooldown_sec = trade_cooldown_sec
        self.daily_notional_limit_usd = daily_notional_limit_usd
        self.volatility_multiplier = volatility_multiplier
        self.max_drawdown_pct = max_drawdown_pct
        self.max_single_asset_pct = max_single_asset_pct
        self.emergency_margin_threshold = emergency_margin_threshold
        self.allowed_actions = {action.value for action in TradingAction}

    def _safe_decimal(self, value: Any, default: Decimal = Decimal("0")) -> Decimal:
        if value is None:
            return default
        return Decimal(str(value))

    def _calculate_volatility_adjusted_size(self, base_size: Decimal, volatility: Decimal) -> Decimal:
        """
        Regola dimensione posizione basata su volatilità mercato.
        Volatilità più alta = dimensione più piccola per mantenere rischio costante per trade.
        Usa scaling inverso volatilità con floor per evitare ordini zero-size.
        """
        if volatility <= 0:
            return base_size
        # Normalizza: se volatilità è "normale" (~0.005), aggiustamento ≈ 1.0
        # Se volatilità è 2x normale, aggiustamento ≈ 0.7
        # Se volatilità è 0.5x normale, aggiustamento ≈ 1.15 (capped a 1.2)
        normal_vol = Decimal("0.005")
        ratio = volatility / normal_vol
        adjustment = Decimal("1") / (Decimal("1") + ((ratio - Decimal("1")) * self.volatility_multiplier))
        # Clamp tra 0.4 e 1.2
        adjustment = max(Decimal("0.4"), min(Decimal("1.2"), adjustment))
        return base_size * adjustment

    def check_drawdown(
        self,
        portfolio_state: PortfolioState,
        peak_portfolio_value: Decimal
    ) -> Tuple[bool, str]:
        if peak_portfolio_value <= 0:
            return True, "ok"
        current = portfolio_state.total_balance
        drawdown = (peak_portfolio_value - current) / peak_portfolio_value
        if drawdown >= self.max_drawdown_pct:
            logger.warning(
                f"Drawdown massimo superato: {float(drawdown) * 100:.1f}% "
                f"(limite={float(self.max_drawdown_pct) * 100:.1f}%)"
            )
            return False, "max_drawdown_breached"
        # Avviso morbido al 66% di drawdown massimo
        if drawdown >= self.max_drawdown_pct * Decimal("0.66"):
            logger.info(
                f"Avviso drawdown: {float(drawdown) * 100:.1f}% "
                f"avvicinandosi limite di {float(self.max_drawdown_pct) * 100:.1f}%"
            )
        return True, "ok"

    def check_emergency_derisk(self, portfolio_state: PortfolioState) -> bool:
        return portfolio_state.margin_usage >= self.emergency_margin_threshold

    def get_emergency_close_coin(self, portfolio_state: PortfolioState) -> str:
        worst_coin = ""
        worst_pnl = Decimal("0")
        for coin, pos in portfolio_state.positions.items():
            pnl = Decimal(str(pos.get("unrealized_pnl", 0)))
            if pnl < worst_pnl:
                worst_pnl = pnl
                worst_coin = coin
        return worst_coin

    def check_order(
        self,
        coin: str,
        order: Dict[str, Any],
        market_price: Decimal,
        portfolio_state: PortfolioState,
        last_trade_timestamp_by_coin: Dict[str, float],
        daily_notional_used: Decimal,
        now_ts: float,
        volatility: Decimal = Decimal("0"),
        peak_portfolio_value: Decimal = Decimal("0")
    ) -> Tuple[bool, str]:
        action = str(order.get("action", "")).strip().lower()
        size = self._safe_decimal(order.get("size", 0))
        leverage = self._safe_decimal(order.get("leverage", 1))
        confidence = self._safe_decimal(order.get("confidence", 0))

        if action not in self.allowed_actions:
            return False, "unknown_action"

        if action == TradingAction.HOLD.value:
            return True, "hold"

        if leverage < Decimal("1") or leverage > self.hard_max_leverage:
            return False, "leverage_out_of_bounds"

        manage_actions = {
            TradingAction.CLOSE_POSITION.value,
            TradingAction.REDUCE_POSITION.value,
            TradingAction.CHANGE_LEVERAGE.value
        }
        open_actions = {
            TradingAction.BUY.value,
            TradingAction.SELL.value,
            TradingAction.INCREASE_POSITION.value
        }

        if action in manage_actions and confidence < self.min_confidence_manage:
            return False, "confidence_manage_too_low"

        if action in open_actions and confidence < self.min_confidence_open:
            return False, "confidence_open_too_low"

        if action in open_actions:
            # Controllo drawdown
            dd_ok, dd_reason = self.check_drawdown(portfolio_state, peak_portfolio_value)
            if not dd_ok:
                return False, dd_reason

            if portfolio_state.margin_usage > self.max_margin_usage:
                return False, "margin_usage_too_high"

            if market_price <= 0 or size <= 0:
                return False, "invalid_price_or_size"

            # Rilevamento conflitto posizione
            current_side = portfolio_state.get_position_side(coin)
            if action == TradingAction.BUY.value and current_side == PositionSide.SHORT:
                return False, "conflict_buy_while_short"
            if action == TradingAction.SELL.value and current_side == PositionSide.LONG:
                return False, "conflict_sell_while_long"

            # Applica aggiustamento volatilità a dimensione
            adjusted_size = self._calculate_volatility_adjusted_size(size, volatility)

            min_size = self.min_size_by_coin.get(coin, Decimal("0"))
            if adjusted_size < min_size:
                return False, "adjusted_size_below_min"

            required_margin = (adjusted_size * market_price) / leverage
            max_margin_per_trade = portfolio_state.total_balance * self.max_order_margin_pct
            if required_margin > portfolio_state.available_balance:
                return False, "insufficient_available_balance"
            if required_margin > max_margin_per_trade:
                return False, "per_trade_margin_cap_exceeded"

            # Limite concentrazione per-asset
            new_notional = adjusted_size * market_price
            existing_notional = Decimal("0")
            if coin in portfolio_state.positions:
                pos = portfolio_state.positions[coin]
                existing_notional = abs(Decimal(str(pos.get("size", 0)))) * Decimal(str(pos.get("entry_price", 0)))
            total_asset_exposure = existing_notional + new_notional
            max_asset_exposure = portfolio_state.total_balance * self.max_single_asset_pct
            if total_asset_exposure > max_asset_exposure:
                return False, "single_asset_concentration_exceeded"

            last_ts = float(last_trade_timestamp_by_coin.get(coin, 0))
            if (now_ts - last_ts) < self.trade_cooldown_sec:
                return False, "cooldown_active"

            projected_daily = daily_notional_used + new_notional
            if projected_daily > self.daily_notional_limit_usd:
                return False, "daily_notional_cap_exceeded"

            # Scrivi dimensione aggiustata indietro nell'ordine così esecuzione la usa
            order["size"] = adjusted_size

        return True, "ok"