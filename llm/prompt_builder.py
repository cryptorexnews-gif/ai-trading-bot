from decimal import Decimal
from typing import Any, Dict, List, Optional

from models import MarketData, PortfolioState


class LLMPromptBuilder:
    """Builds structured prompts for the trading LLM."""

    @staticmethod
    def _safe_dict(value: Any) -> Dict[str, Any]:
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _safe_list(value: Any) -> List[Any]:
        return value if isinstance(value, list) else []

    def _format_positions(self, positions: Dict[str, Dict[str, Any]]) -> str:
        if not isinstance(positions, dict) or not positions:
            return "  No open positions."

        lines = []
        for coin, pos in positions.items():
            if not isinstance(pos, dict):
                continue

            size = pos.get("size", 0)
            entry_px = pos.get("entry_price", 0)
            pnl = pos.get("unrealized_pnl", 0)
            side = "LONG" if Decimal(str(size)) > 0 else "SHORT"
            margin = pos.get("margin_used", "N/A")

            entry_d = Decimal(str(entry_px))
            pnl_d = Decimal(str(pnl))
            size_d = abs(Decimal(str(size)))
            pnl_pct = (pnl_d / (size_d * entry_d) * Decimal("100")) if (size_d * entry_d) > 0 else Decimal("0")

            lines.append(
                f"  - {coin}: {side} | Size: {size} | Entry: ${entry_px} | "
                f"PnL: ${pnl} ({float(pnl_pct):+.2f}%) | Margin: ${margin}"
            )

        return "\n".join(lines) if lines else "  No open positions."

    def _format_technical_data(self, technical_data: Optional[Dict[str, Any]]) -> str:
        td = self._safe_dict(technical_data)
        if not td:
            return "  No technical data available."

        lines = []
        lines.append(f"  Current Price: ${float(td.get('current_price', 0)):.2f}")
        lines.append(f"  24h Change: {float(td.get('change_24h', 0)) * 100:+.2f}%")
        lines.append(f"  Volume 24h: ${float(td.get('volume_24h', 0)):,.0f}")
        lines.append(f"  Funding Rate: {float(td.get('funding_rate', 0)) * 100:+.4f}%")
        lines.append(f"  Trend Direction: {td.get('trend_direction', 'neutral').upper()}")
        lines.append(f"  Trend Strength: {td.get('trend_strength', 0)}/3 timeframes aligned")
        lines.append(f"  Trends Aligned: {'YES ✅' if td.get('trends_aligned', False) else 'NO ⚠️'}")

        lines.append("\n  ⏰ 1H TIMEFRAME (Entry Timing):")
        lines.append(f"    EMA9: ${float(td.get('current_ema9', 0)):.2f}")
        lines.append(f"    EMA21: ${float(td.get('current_ema21', 0)):.2f}")
        lines.append(f"    RSI14: {float(td.get('current_rsi_14', 50)):.1f}")
        lines.append(f"    MACD Hist: {float(td.get('current_macd_histogram', 0)):.4f}")
        lines.append(f"    ATR14: ${float(td.get('intraday_atr', 0)):.2f}")
        lines.append(f"    BB Position: {float(td.get('bb_position', 0.5)) * 100:.1f}%")
        lines.append(f"    VWAP: ${float(td.get('vwap', 0)):.2f}")
        lines.append(f"    Volume Ratio: {float(td.get('volume_ratio', 1)):.2f}x")

        hourly = self._safe_dict(td.get("hourly_context", {}))
        if hourly:
            lines.append("\n  📊 4H TIMEFRAME (Primary Trend):")
            lines.append(f"    Trend: {hourly.get('trend', 'unknown').upper()}")
            lines.append(f"    EMA9: ${float(hourly.get('ema_9', 0)):.2f}")
            lines.append(f"    EMA21: ${float(hourly.get('ema_21', 0)):.2f}")
            lines.append(f"    EMA50: ${float(hourly.get('ema_50', 0)):.2f}")
            lines.append(f"    RSI14: {float(hourly.get('rsi_14', 50)):.1f}")
            lines.append(f"    MACD: {float(hourly.get('macd_line', 0)):.4f}")
            lines.append(f"    ATR14: ${float(hourly.get('atr_14', 0)):.2f}")

        lt = self._safe_dict(td.get("long_term_context", {}))
        if lt:
            lines.append("\n  📈 1D TIMEFRAME (Main Trend):")
            lines.append(f"    Trend: {lt.get('trend', 'unknown').upper()}")
            lines.append(f"    EMA21: ${float(lt.get('ema_21', 0)):.2f}")
            lines.append(f"    EMA50: ${float(lt.get('ema_50', 0)):.2f}")
            lines.append(f"    EMA200: ${float(lt.get('ema_200', 0)):.2f}")
            lines.append(f"    ATR14: ${float(lt.get('atr_14', 0)):.2f}")

            rsi_current = lt.get("rsi_14", Decimal("50"))
            lines.append(f"    RSI14: {float(rsi_current):.1f}")

            rsi_trend = self._safe_list(lt.get("rsi_trend", []))
            if len(rsi_trend) >= 3:
                last_3 = rsi_trend[-3:]
                lines.append(f"    RSI14 Trend: {', '.join([f'{float(v):.1f}' for v in last_3])}")

        return "\n".join(lines)

    def _format_recent_trades(self, recent_trades: List[Dict[str, Any]]) -> str:
        trades = self._safe_list(recent_trades)
        if not trades:
            return "  No recent trades."

        lines = []
        for trade in trades[-5:]:
            if not isinstance(trade, dict):
                continue
            success_str = "OK" if trade.get("success") else "FAIL"
            trigger = trade.get("trigger", "ai")
            lines.append(
                f"  - [{success_str}] {trade.get('coin', '?')} {trade.get('action', '?')} "
                f"size={trade.get('size', '?')} @ ${trade.get('price', '?')} "
                f"conf={trade.get('confidence', '?')} trigger={trigger} "
                f"({str(trade.get('reasoning', ''))[:60]})"
            )

        return "\n".join(lines) if lines else "  No recent trades."

    def _format_managed_position(self, managed_position: Optional[Dict[str, Any]]) -> str:
        mp = self._safe_dict(managed_position)
        if not mp:
            return "  No managed position context for this coin."

        side = "LONG" if bool(mp.get("is_long", False)) else "SHORT"
        lines = [
            f"  Side: {side}",
            f"  Size: {mp.get('size', '0')}",
            f"  Entry: ${mp.get('entry_price', '0')}",
            f"  Managed SL: {mp.get('stop_loss_pct', 'n/a')} (price ${mp.get('stop_loss_price', '0')})",
            f"  Managed TP: {mp.get('take_profit_pct', 'n/a')} (price ${mp.get('take_profit_price', '0')})",
            f"  Break-even active: {bool(mp.get('break_even_activated', False))}",
            f"  Managed SL Order ID: {mp.get('stop_loss_order_id')}",
            f"  Managed TP Order ID: {mp.get('take_profit_order_id')}",
        ]
        return "\n".join(lines)

    def _format_protective_orders(self, protective_orders: Optional[List[Dict[str, Any]]]) -> str:
        orders = self._safe_list(protective_orders)
        if not orders:
            return "  No protective TP/SL open orders found on exchange for this coin."

        lines: List[str] = []
        for order in orders:
            if not isinstance(order, dict):
                continue
            lines.append(
                f"  - oid={order.get('oid')} type={str(order.get('tpsl', '')).upper()} "
                f"trigger=${order.get('trigger_px', '0')} side={order.get('side', '')} "
                f"reduce_only={order.get('reduce_only', False)}"
            )

        return "\n".join(lines) if lines else "  No protective TP/SL open orders found on exchange for this coin."

    def _build_protection_consistency(
        self,
        managed_position: Optional[Dict[str, Any]],
        protective_orders: Optional[List[Dict[str, Any]]]
    ) -> str:
        mp = self._safe_dict(managed_position)
        orders = [o for o in self._safe_list(protective_orders) if isinstance(o, dict)]

        sl_ids = [o.get("oid") for o in orders if str(o.get("tpsl", "")).lower() == "sl"]
        tp_ids = [o.get("oid") for o in orders if str(o.get("tpsl", "")).lower() == "tp"]

        managed_sl_id = mp.get("stop_loss_order_id")
        managed_tp_id = mp.get("take_profit_order_id")

        managed_sl_on_exchange = managed_sl_id is not None and managed_sl_id in sl_ids
        managed_tp_on_exchange = managed_tp_id is not None and managed_tp_id in tp_ids

        return (
            f"  managed_sl_id_present_on_exchange: {managed_sl_on_exchange}\n"
            f"  managed_tp_id_present_on_exchange: {managed_tp_on_exchange}\n"
            f"  sl_open_orders_count: {len(sl_ids)}\n"
            f"  tp_open_orders_count: {len(tp_ids)}"
        )

    def build_prompt(
        self,
        market_data: MarketData,
        portfolio_state: PortfolioState,
        technical_data: Optional[Dict[str, Any]] = None,
        all_mids: Optional[Dict[str, str]] = None,
        funding_data: Optional[Dict[str, Any]] = None,
        recent_trades: Optional[List[Dict[str, Any]]] = None,
        peak_portfolio_value: Decimal = Decimal("0"),
        consecutive_losses: int = 0,
        managed_position: Optional[Dict[str, Any]] = None,
        protective_orders: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        mids = self._safe_dict(all_mids)
        all_mids_section = ""
        if mids:
            ordered_coins = sorted([c for c in mids.keys() if c])
            if market_data.coin in ordered_coins:
                ordered_coins.remove(market_data.coin)
            ordered_coins = [market_data.coin] + ordered_coins
            ordered_coins = ordered_coins[:120]

            mid_lines = [f"  {coin}: ${mids[coin]}" for coin in ordered_coins if coin in mids]
            if mid_lines:
                all_mids_section = "MARKET OVERVIEW (Hyperliquid Mid Prices):\n" + "\n".join(mid_lines)

        fd = self._safe_dict(funding_data)
        funding_section = ""
        if fd:
            funding_section = f"""
FUNDING DATA (from Hyperliquid):
  Current Funding Rate: {fd.get('funding_rate', 'N/A')}
  Open Interest: {fd.get('open_interest', 'N/A')}
  Premium: {fd.get('premium', 'N/A')}"""

        drawdown_section = ""
        if peak_portfolio_value > 0:
            current_dd = (peak_portfolio_value - portfolio_state.total_balance) / peak_portfolio_value
            drawdown_section = f"""
RISK CONTEXT:
  Peak Portfolio Value: ${peak_portfolio_value}
  Current Drawdown: {float(current_dd) * 100:.2f}%
  Max Allowed Drawdown: 15%
  Consecutive Losing Trades: {consecutive_losses}"""

        total_exposure = portfolio_state.get_total_exposure()
        total_pnl = portfolio_state.get_total_unrealized_pnl()

        recent_trades_section = ""
        if recent_trades:
            recent_trades_section = f"""
RECENT TRADE HISTORY (last 5):
{self._format_recent_trades(recent_trades)}"""

        td = self._safe_dict(technical_data)
        trend_strength = td.get("trend_strength", 0)

        trend_analysis = ""
        if trend_strength == 3:
            trend_analysis = "✅ ALL TIMEFRAMES ALIGNED (1H+4H+1D) — High conviction trend trade opportunity."
        elif trend_strength == 2:
            trend_analysis = "⚠️ TWO TIMEFRAMES ALIGNED — Moderate conviction, wait for better alignment or use smaller size."
        else:
            trend_analysis = "🚫 NO TIMEFRAME ALIGNMENT — Avoid new positions, only manage existing ones."

        protective_section = f"""
PROTECTIVE ORDERS STATUS (for target coin):
Managed position risk config:
{self._format_managed_position(managed_position)}

Exchange open protective orders:
{self._format_protective_orders(protective_orders)}

Consistency checks:
{self._build_protection_consistency(managed_position, protective_orders)}
"""

        prompt = f"""You are an elite cryptocurrency trend trader on Hyperliquid exchange, specialized in 4HOUR and 1DAY trend following.
ALL data below comes directly from the Hyperliquid API. Make your decision based ONLY on this data.

{all_mids_section}

TARGET ASSET: {market_data.coin}
  Current Price: ${market_data.last_price}
  24h Change: {float(market_data.change_24h) * 100:.4f}%
  24h Volume: ${float(market_data.volume_24h):,.2f}
  Funding Rate: {float(market_data.funding_rate):.6f}%
{funding_section}

TECHNICAL INDICATORS (Multi-timeframe analysis for trend trading):
{self._format_technical_data(technical_data)}

{trend_analysis}

PORTFOLIO STATE:
  Total Balance: ${portfolio_state.total_balance}
  Available Balance: ${portfolio_state.available_balance}
  Margin Usage: {float(portfolio_state.margin_usage) * 100:.2f}%
  Total Exposure: ${total_exposure}
  Total Unrealized PnL: ${total_pnl}
  Open Positions: {len(portfolio_state.positions)}
{drawdown_section}

CURRENT POSITIONS:
{self._format_positions(portfolio_state.positions)}
{protective_section}
{recent_trades_section}

=== TREND TRADING STRATEGY RULES (4H/1D FOCUS) ===

TREND IDENTIFICATION CRITERIA — Enter ONLY when:
1. PRIMARY TREND (4H): EMA9 > EMA21 > EMA50 (uptrend) or EMA9 < EMA21 < EMA50 (downtrend)
2. MAIN TREND (1D): Confirms primary trend direction
3. TREND STRENGTH: At least 2/3 timeframes aligned (preferably 3/3)
4. VOLUME CONFIRMATION: volume_ratio > 1.3 on breakout/breakdown
5. RSI POSITION: RSI14 between 40-60 for continuation, <30/>70 for reversal setups
6. NO MAJOR DIVERGENCES: Price making higher highs with indicators confirming

ENTRY TIMING (1H timeframe):
- Wait for pullback to key levels: EMA21, VWAP, or previous support/resistance
- RSI14 between 30-40 for longs, 60-70 for shorts (pullback zones)
- MACD histogram turning positive (longs) or negative (shorts)
- Price above VWAP for longs, below VWAP for shorts
- Bollinger Band position <30% for longs, >70% for shorts (reversion to mean)

STOP-LOSS / TAKE-PROFIT DECISION:
- You MUST choose dynamic stop_loss_pct and take_profit_pct based on volatility and market structure.
- Use ATR and trend strength to set distances.
- In high volatility, use wider SL/TP; in low volatility, tighter levels.
- Prefer minimum risk/reward around 1:1.5 unless setup quality is very low.
- For HOLD actions, set stop_loss_pct and take_profit_pct to null.
- If protective TP/SL orders are missing or inconsistent, prefer actions that restore proper protection.

CRITICAL RULES FOR TREND TRADING:
- DO NOT counter-trend trade (no buying in downtrend, no selling in uptrend)
- If drawdown > 10%, reduce position sizes by 50%
- If consecutive losses > 2, switch to 1% position sizes until recovery
- Monitor funding rates: Extreme positive (>0.01%) = caution on longs
- Monitor funding rates: Extreme negative (<-0.01%) = caution on shorts
- Weekend rule: Reduce leverage by 30% before weekends (higher volatility)
- News events: Avoid opening new positions 1 hour before/after major announcements
- If no clear trend exists, ALWAYS hold — capital preservation is priority #1
- If there is an open position and protective TP/SL orders are missing (sl_open_orders_count=0 or tp_open_orders_count=0), DO NOT open/increase risk. Prefer HOLD with valid stop_loss_pct and take_profit_pct to restore protection.

CONFIDENCE SCORING FOR TREND TRADES:
- 0.90-1.0: All 3 timeframes aligned + strong volume + clean pullback
- 0.80-0.89: 2/3 timeframes aligned + decent volume + good entry timing
- 0.70-0.79: Trend present but entry timing suboptimal
- 0.60-0.69: Weak trend signal — only for managing existing positions
- Below 0.60: No trade — wait for better setup

Respond with ONLY this JSON (no markdown, no extra text):
{{
  "action": "buy|sell|hold|close_position|increase_position|reduce_position|change_leverage",
  "size": 0.001,
  "leverage": 4,
  "confidence": 0.85,
  "stop_loss_pct": 0.03,
  "take_profit_pct": 0.06,
  "reasoning": "Trend analysis: [timeframe alignment] + [entry timing] + [risk assessment]"
}}"""
        return prompt.strip()