#!/usr/bin/env python3
"""
Check which files were being modified in the previous session.
This helps identify where to continue the interrupted updates.
"""

import os
import json
import time
from pathlib import Path

def check_recent_modifications():
    """Check for recently modified files that might indicate interrupted updates."""
    print("Checking for recently modified files...")
    
    # Files that were likely being updated based on the chat context
    likely_files = [
        "config/bot_config.py",
        "technical_analyzer_simple.py", 
        "llm_engine.py",
        "cycle_orchestrator.py",
        "risk_manager.py",
        "position_manager.py",
        "execution_engine.py",
        "frontend/src/components/TradingView.jsx",
        "frontend/src/components/StatCard.jsx",
        "frontend/src/components/EquityChart.jsx",
        ".env"
    ]
    
    recent_files = []
    for file_path in likely_files:
        if os.path.exists(file_path):
            mod_time = os.path.getmtime(file_path)
            # Files modified in the last 10 minutes
            if time.time() - mod_time < 600:
                recent_files.append((file_path, time.ctime(mod_time)))
    
    if recent_files:
        print("\nRecently modified files (last 10 minutes):")
        for file_path, mod_time in recent_files:
            print(f"  • {file_path} - {mod_time}")
    else:
        print("\nNo recently modified files found.")
    
    # Check for .env updates
    if os.path.exists(".env"):
        with open(".env", "r") as f:
            env_content = f.read()
            if "PRIMARY_TIMEFRAME=4h" in env_content:
                print("\n✓ .env already has 4h/1d trend configuration")
            else:
                print("\n✗ .env needs 4h/1d trend configuration updates")
    
    # Check bot_config for trend parameters
    if os.path.exists("config/bot_config.py"):
        with open("config/bot_config.py", "r") as f:
            config_content = f.read()
            if "primary_timeframe" in config_content:
                print("✓ bot_config.py has trend parameters")
            else:
                print("✗ bot_config.py needs trend parameter updates")
    
    return recent_files

if __name__ == "__main__":
    check_recent_modifications()