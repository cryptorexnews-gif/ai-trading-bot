if drawdown >= self.max_drawdown_pct * Decimal("0.66"):
            logger.info(
                f"Drawdown warning: {float(drawdown) * 100:.1f}% "
                f"approaching limit of {float(self.max_drawdown_pct) * 100:.1f}%"
            )