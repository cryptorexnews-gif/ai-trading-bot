### No Trades Executing
1. Check `ALLOW_EXTERNAL_LLM` – if `false`, bot only uses fallback (hold/de-risk)
2. Check `MIN_CONFIDENCE_OPEN` – may be too high
3. Review health snapshot for risk rejections
4. Check market data freshness (Binance API reachable)
5. Verify `EXECUTION_MODE=paper` for testing