"""
Monitor MoneyBot activity every 5 minutes and report what happened.
"""
import time
import os
from datetime import datetime

log_file = "moneybot_main.log"

def get_file_tail(filepath, lines=50):
    """Get last N lines of file."""
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            return f.readlines()[-lines:]
    except:
        return []

def main():
    print("📊 MoneyBot Activity Monitor - Reports every 5 minutes\n")
    print("=" * 80)
    
    last_lines = []
    cycle = 0
    
    while True:
        cycle += 1
        current_lines = get_file_tail(log_file, 100)
        
        # Find new lines
        if last_lines:
            new_lines = current_lines[len(last_lines):]
        else:
            new_lines = current_lines
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n[Cycle {cycle}] {timestamp}")
        print("-" * 80)
        
        if not new_lines:
            print("✓ No new activity")
        else:
            print(f"✓ New events ({len(new_lines)} lines):\n")
            for line in new_lines:
                print(line.rstrip())
        
        last_lines = current_lines
        
        # Count activity types
        activity_counts = {
            'FREELANCE': 0,
            'TRADE': 0,
            'NEWS': 0,
            'ERROR': 0
        }
        
        for line in new_lines:
            if 'FREELANCE' in line:
                activity_counts['FREELANCE'] += 1
            elif 'TRADE' in line or '[TRADE]' in line:
                activity_counts['TRADE'] += 1
            elif 'NEWS' in line:
                activity_counts['NEWS'] += 1
            elif 'ERROR' in line or 'Traceback' in line:
                activity_counts['ERROR'] += 1
        
        print("\n📈 Summary:")
        print(f"   Freelance events: {activity_counts['FREELANCE']}")
        print(f"   Trading events:   {activity_counts['TRADE']}")
        print(f"   News signals:     {activity_counts['NEWS']}")
        print(f"   Errors:           {activity_counts['ERROR']}")
        print("=" * 80)
        
        print("⏳ Waiting 5 minutes for next update...")
        time.sleep(300)  # 5 minutes

if __name__ == "__main__":
    main()
