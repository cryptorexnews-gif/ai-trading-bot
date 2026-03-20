#!/usr/bin/env python3
"""
Continue interrupted updates for 4h/1d trend strategy.
Utility script to patch .env and verify bot_config fields.
"""

import os
import sys


def update_env_file() -> bool:
    """Update .env file with 4h/1d trend configuration."""
    env_path = ".env"

    if not os.path.exists(env_path):
        print(f"Error: {env_path} not found")
        return False

    try:
        with open(env_path, "r", encoding="utf-8") as f:
            content = f.read()

        if "PRIMARY_TIMEFRAME=4h" in content:
            print("✓ .env already has 4h/1d trend configuration")
            return True

        trend_config = [
            "",
            "# Trend 4h/1D Strategy Configuration",
            "PRIMARY_TIMEFRAME=4h",
            "SECONDARY_TIMEFRAME=1d",
            "ENTRY_TIMEFRAME=1h",
            "MIN_TREND_DURATION_HOURS=24",
            "VOLUME_CONFIRMATION_THRESHOLD=1.5",
            "",
        ]

        lines = content.splitlines()
        new_lines = []
        trend_added = False

        for line in lines:
            new_lines.append(line)
            if line.startswith("TRADING_PAIRS=") and not trend_added:
                new_lines.extend(trend_config)
                trend_added = True

        if not trend_added:
            new_lines.extend(trend_config)

        with open(env_path, "w", encoding="utf-8") as f:
            f.write("\n".join(new_lines) + "\n")

        print("✓ Updated .env with 4h/1d trend configuration")
        return True

    except Exception as e:
        print(f"✗ Error updating .env: {e}")
        return False


def check_bot_config() -> bool:
    """Check if bot_config.py has trend parameters."""
    config_path = "config/bot_config.py"

    if not os.path.exists(config_path):
        print(f"Error: {config_path} not found")
        return False

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            content = f.read()

        required_params = [
            "primary_timeframe",
            "secondary_timeframe",
            "entry_timeframe",
            "min_trend_duration_hours",
            "volume_confirmation_threshold",
        ]

        missing_params = [param for param in required_params if param not in content]

        if missing_params:
            print(f"✗ bot_config.py missing parameters: {', '.join(missing_params)}")
            return False

        print("✓ bot_config.py has all trend parameters")
        return True

    except Exception as e:
        print(f"✗ Error checking bot_config.py: {e}")
        return False


def main() -> int:
    """Main function."""
    print("Continuing 4h/1d trend strategy updates...")
    print("=" * 50)

    print("\n1. Updating .env file...")
    env_updated = update_env_file()

    print("\n2. Checking bot_config.py...")
    config_ok = check_bot_config()

    print("\n" + "=" * 50)
    print("Update Status:")
    print(f"  • .env configuration: {'✓ Complete' if env_updated else '✗ Needs work'}")
    print(f"  • bot_config.py: {'✓ Complete' if config_ok else '✗ Needs work'}")

    if not config_ok:
        print("\nNext steps needed:")
        print("1. Update config/bot_config.py with trend parameters")
        print("2. Update technical_analyzer_simple.py for multi-timeframe analysis")
        print("3. Update llm_engine.py prompts for trend trading")
        print("4. Update frontend components to display trend information")

    return 0 if (env_updated and config_ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())