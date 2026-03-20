#!/usr/bin/env python3
"""
Continue the interrupted file updates for the 4h/1d trend strategy.
Based on the chat context, we need to complete the configuration updates.
"""

import os
import sys

def update_env_file():
    """Update .env file with 4h/1d trend configuration."""
    env_path = ".env"
    
    if not os.path.exists(env_path):
        print(f"Error: {env_path} not found")
        return False
    
    with open(env_path, "r") as f:
        content = f.read()
    
    # Check if already updated
    if "PRIMARY_TIMEFRAME=4h" in content:
            print("✓ .env already has 4h/1d trend configuration")
            return True
        
        # Add trend configuration parameters
        trend_config = """
# Trend 4h/1D Strategy Configuration
PRIMARY_TIMEFRAME=4h
SECONDARY_TIMEFRAME=1d
ENTRY_TIMEFRAME=1h
MIN_TREND_DURATION_HOURS=24
VOLUME_CONFIRMATION_THRESHOLD=1.5
"""
        
        # Find where to insert the trend config (after trading pairs)
        lines = content.split('\n')
        new_lines = []
        trend_added = False
        
        for line in lines:
            new_lines.append(line)
            if line.startswith("TRADING_PAIRS=") and not trend_added:
                new_lines.append(trend_config)
                trend_added = True
        
        if not trend_added:
            # Append at the end
            new_lines.append(trend_config)
        
        with open(env_path, 'w') as f:
            f.write('\n'.join(new_lines))
        
        print("✓ Updated .env with 4h/1d trend configuration")
        return True
    
    except Exception as e:
        print(f"✗ Error updating .env: {e}")
        return False

def check_bot_config():
    """Check if bot_config.py has the trend parameters."""
    config_path = "config/bot_config.py"
    
    if not os.path.exists(config_path):
        print(f"Error: {config_path} not found")
        return False
    
    try:
        with open(config_path, 'r') as f:
            content = f.read()
            
        required_params = [
            "primary_timeframe",
            "secondary_timeframe", 
            "entry_timeframe",
            "min_trend_duration_hours",
            "volume_confirmation_threshold"
        ]
        
        missing_params = []
        for param in required_params:
            if param not in content:
                missing_params.append(param)
        
        if missing_params:
            print(f"✗ bot_config.py missing parameters: {', '.join(missing_params)}")
            return False
        else:
            print("✓ bot_config.py has all trend parameters")
            return True
            
    except Exception as e:
        print(f"✗ Error checking bot_config.py: {e}")
        return False

def main():
    """Main function to continue the interrupted updates."""
    print("Continuing 4h/1d trend strategy updates...")
    print("=" * 50)
    
    # Step 1: Update .env file
    print("\n1. Updating .env file...")
    env_updated = update_env_file()
    
    # Step 2: Check bot_config
    print("\n2. Checking bot_config.py...")
    config_ok = check_bot_config()
    
    # Step 3: Summary
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
    
    return env_updated and config_ok

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)