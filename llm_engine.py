# Use Claude Opus 4.6 with reasoning enabled (extended thinking)
        payload = {
            "model": "anthropic/claude-opus-4.6",
            "messages": [
                {
                    "role": "user",
                    "content": self._build_prompt(market_data, portfolio_state)
                }
            ],
            "max_tokens": 4096,  # Increased for reasoning
            "temperature": 0.2,
            "stream": False,
            # Enable reasoning/extended thinking (Claude's extended reasoning feature)
            "extra_body": {
                "thinking": {
                    "type": "enabled",
                    "budget_tokens": 2000  # Allocate tokens for reasoning
                }
            }
        }