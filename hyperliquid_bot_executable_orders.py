#!/usr/bin/env python3
"""
Hyperliquid Trading Bot — Thin Entry Point
Delegates initialization to bot/bootstrap.py and runtime loop to bot/runner.py.
"""

import logging

from dotenv import load_dotenv

load_dotenv()

from bot.bootstrap import BotBootstrap
from bot.runner import BotRunner, parse_args
from bot.runtime_config_applier import RuntimeConfigApplier


def main():
    args = parse_args()
    context = BotBootstrap.build()
    runtime_applier = RuntimeConfigApplier(context)
    runner = BotRunner(context, runtime_applier)
    runner.run(single_cycle=args.single_cycle)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    main()