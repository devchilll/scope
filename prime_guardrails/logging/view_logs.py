#!/usr/bin/env python3
"""
Audit Log Viewer - Terminal-based visualization of PRIME audit logs

Usage:
    python view_logs.py                          # View all logs from today
    python view_logs.py --user admin             # Filter by user
    python view_logs.py --action safety_decision # Filter by action
    python view_logs.py --date 2025-11-30        # View specific date
    python view_logs.py --tail 20                # Show last 20 entries
    python view_logs.py --follow                 # Follow mode (like tail -f)
"""

import json
import argparse
from pathlib import Path
from datetime import datetime, date
from typing import List, Dict, Optional
import time

# ANSI color codes
class Colors:
    RESET = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    
    # Text colors
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    GRAY = '\033[90m'
    
    # Background colors
    BG_RED = '\033[101m'
    BG_GREEN = '\033[102m'
    BG_YELLOW = '\033[103m'


def get_log_file(log_date: Optional[str] = None) -> Path:
    """Get the audit log file path for a given date."""
    if log_date is None:
        log_date = date.today().isoformat()
    
    # Get log directory relative to this script's location
    log_dir = Path(__file__).parent / "audit_logs"
    log_file = log_dir / f"audit_{log_date}.jsonl"
    
    if not log_file.exists():
        print(f"{Colors.RED}Error: Log file not found: {log_file}{Colors.RESET}")
        print(f"{Colors.GRAY}Available log files:{Colors.RESET}")
        for f in sorted(log_dir.glob("audit_*.jsonl")):
            print(f"  - {f.name}")
        exit(1)
    
    return log_file


def colorize_event_type(event_type: str) -> str:
    """Colorize event type based on category."""
    colors = {
        'user_query': Colors.CYAN,
        'account_access': Colors.BLUE,
        'transaction_query': Colors.MAGENTA,
        'safety_block': Colors.RED,
        'escalation_created': Colors.YELLOW,
        'escalation_resolved': Colors.GREEN,
    }
    color = colors.get(event_type, Colors.WHITE)
    return f"{color}{event_type}{Colors.RESET}"


def colorize_action(action: str) -> str:
    """Colorize action based on type."""
    if 'failed' in action or 'error' in action:
        return f"{Colors.RED}{action}{Colors.RESET}"
    elif 'safety' in action:
        return f"{Colors.YELLOW}{action}{Colors.RESET}"
    elif 'resolved' in action:
        return f"{Colors.GREEN}{action}{Colors.RESET}"
    else:
        return f"{Colors.CYAN}{action}{Colors.RESET}"


def colorize_success(success: bool) -> str:
    """Colorize success status."""
    if success:
        return f"{Colors.GREEN}✓{Colors.RESET}"
    else:
        return f"{Colors.RED}✗{Colors.RESET}"


def format_timestamp(ts_str: str) -> str:
    """Format timestamp for display."""
    try:
        ts = datetime.fromisoformat(ts_str)
        return f"{Colors.GRAY}{ts.strftime('%H:%M:%S')}{Colors.RESET}"
    except:
        return ts_str


def truncate_text(text: str, max_length: int = 80) -> str:
    """Truncate text to max length."""
    if len(text) <= max_length:
        return text
    return text[:max_length-3] + "..."


def format_log_entry(entry: Dict, verbose: bool = False) -> str:
    """Format a single log entry for display."""
    timestamp = format_timestamp(entry.get('timestamp', ''))
    event_type = colorize_event_type(entry.get('event_type', 'unknown'))
    user_id = f"{Colors.BOLD}{entry.get('user_id', 'unknown')}{Colors.RESET}"
    action = colorize_action(entry.get('action', 'unknown'))
    success = colorize_success(entry.get('success', True))
    
    # Get raw values for spacing calculations (without color codes)
    raw_event_type = entry.get('event_type', 'unknown')
    raw_user_id = entry.get('user_id', 'unknown')
    
    # Calculate padding to align columns
    event_padding = max(0, 30 - len(raw_event_type))
    user_padding = max(0, 15 - len(raw_user_id))
    
    # Basic line with proper spacing
    line = f"{timestamp} {success} {event_type}{' ' * event_padding} {user_id}{' ' * user_padding} {action}"
    
    # Add details if verbose
    if verbose:
        details = entry.get('details', {})
        if details:
            line += f"\n{Colors.DIM}"
            
            # Show important details
            if 'input' in details:
                line += f"\n  Input: {truncate_text(details['input'], 100)}"
            
            if 'analysis' in details and isinstance(details['analysis'], dict):
                analysis = details['analysis']
                if 'safety_score' in analysis:
                    score = analysis['safety_score']
                    score_color = Colors.GREEN if score >= 0.8 else Colors.YELLOW if score >= 0.5 else Colors.RED
                    line += f"\n  Safety: {score_color}{score:.2f}{Colors.RESET}{Colors.DIM}"
                if 'violated_rules' in analysis and analysis['violated_rules']:
                    line += f"\n  {Colors.RED}Violated: {', '.join(analysis['violated_rules'])}{Colors.DIM}"
                if 'analysis' in analysis:
                    line += f"\n  Analysis: {truncate_text(analysis['analysis'], 120)}"
            
            if 'decision' in details and isinstance(details['decision'], dict):
                decision = details['decision']
                action_val = decision.get('action', '')
                action_color = Colors.GREEN if action_val == 'approve' else Colors.RED if action_val == 'reject' else Colors.YELLOW
                line += f"\n  Decision: {action_color}{action_val}{Colors.RESET}{Colors.DIM}"
                if 'reasoning' in decision:
                    line += f"\n  Reasoning: {truncate_text(decision['reasoning'], 120)}"
            
            if 'summary' in details:
                line += f"\n  Summary: {truncate_text(details['summary'], 120)}"
            
            # Transaction details
            if 'amount' in details and 'from_account' in details and 'to_account' in details:
                amount = details['amount']
                from_acc = details['from_account']
                to_acc = details['to_account']
                desc = details.get('description', '')
                txn_id = details.get('transaction_id', '')
                
                line += f"\n  Transaction: {Colors.CYAN}{txn_id}{Colors.DIM}"
                line += f"\n  Amount: {Colors.GREEN}${amount:.2f}{Colors.DIM}"
                line += f"\n  From: {Colors.BOLD}{from_acc}{Colors.DIM} → To: {Colors.BOLD}{to_acc}{Colors.DIM}"
                if desc:
                    line += f"\n  Description: {desc}"
            
            if 'error' in details:
                line += f"\n  {Colors.RED}Error: {details['error']}{Colors.DIM}"
            
            line += Colors.RESET
        
        # Add divider after verbose entries
        line += f"\n{Colors.GRAY}{'─' * 100}{Colors.RESET}"
    
    return line


def read_logs(log_file: Path, 
              user_filter: Optional[str] = None,
              action_filter: Optional[str] = None,
              event_filter: Optional[str] = None,
              tail: Optional[int] = None) -> List[Dict]:
    """Read and filter log entries."""
    entries = []
    
    with open(log_file, 'r') as f:
        for line in f:
            try:
                entry = json.loads(line.strip())
                
                # Apply filters
                if user_filter and entry.get('user_id') != user_filter:
                    continue
                if action_filter and action_filter not in entry.get('action', ''):
                    continue
                if event_filter and entry.get('event_type') != event_filter:
                    continue
                
                entries.append(entry)
            except json.JSONDecodeError:
                continue
    
    # Apply tail limit
    if tail:
        entries = entries[-tail:]
    
    return entries


def print_summary(entries: List[Dict]):
    """Print summary statistics."""
    if not entries:
        print(f"{Colors.YELLOW}No log entries found{Colors.RESET}")
        return
    
    # Count by event type
    event_counts = {}
    user_counts = {}
    success_count = 0
    failure_count = 0
    
    for entry in entries:
        event_type = entry.get('event_type', 'unknown')
        event_counts[event_type] = event_counts.get(event_type, 0) + 1
        
        user_id = entry.get('user_id', 'unknown')
        user_counts[user_id] = user_counts.get(user_id, 0) + 1
        
        if entry.get('success', True):
            success_count += 1
        else:
            failure_count += 1
    
    print(f"\n{Colors.BOLD}=== Summary ==={Colors.RESET}")
    print(f"Total entries: {len(entries)}")
    print(f"Success: {Colors.GREEN}{success_count}{Colors.RESET} | Failures: {Colors.RED}{failure_count}{Colors.RESET}")
    
    print(f"\n{Colors.BOLD}Event Types:{Colors.RESET}")
    for event_type, count in sorted(event_counts.items(), key=lambda x: -x[1]):
        print(f"  {colorize_event_type(event_type):40} {count:4}")
    
    print(f"\n{Colors.BOLD}Users:{Colors.RESET}")
    for user_id, count in sorted(user_counts.items(), key=lambda x: -x[1]):
        print(f"  {Colors.BOLD}{user_id:20}{Colors.RESET} {count:4}")
    print()


def follow_logs(log_file: Path, verbose: bool = False):
    """Follow log file in real-time (like tail -f)."""
    print(f"{Colors.BOLD}Following {log_file.name}... (Ctrl+C to stop){Colors.RESET}\n")
    
    # Read existing entries first
    with open(log_file, 'r') as f:
        f.seek(0, 2)  # Go to end of file
        
        try:
            while True:
                line = f.readline()
                if line:
                    try:
                        entry = json.loads(line.strip())
                        print(format_log_entry(entry, verbose))
                    except json.JSONDecodeError:
                        pass
                else:
                    time.sleep(0.1)
        except KeyboardInterrupt:
            print(f"\n{Colors.GRAY}Stopped following logs{Colors.RESET}")


def main():
    parser = argparse.ArgumentParser(
        description='View and analyze PRIME audit logs',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                              # View all logs from today
  %(prog)s --user admin                 # Filter by user
  %(prog)s --action safety_decision     # Filter by action
  %(prog)s --event user_query           # Filter by event type
  %(prog)s --date 2025-11-30            # View specific date
  %(prog)s --tail 20                    # Show last 20 entries
  %(prog)s --verbose                    # Show detailed information
  %(prog)s --follow                     # Follow mode (real-time)
  %(prog)s --summary                    # Show summary only
        """
    )
    
    parser.add_argument('--date', help='Date to view logs (YYYY-MM-DD)')
    parser.add_argument('--user', help='Filter by user ID')
    parser.add_argument('--action', help='Filter by action (partial match)')
    parser.add_argument('--event', help='Filter by event type')
    parser.add_argument('--tail', type=int, help='Show last N entries')
    parser.add_argument('--verbose', '-v', action='store_true', help='Show detailed information')
    parser.add_argument('--follow', '-f', action='store_true', help='Follow log file in real-time')
    parser.add_argument('--summary', '-s', action='store_true', help='Show summary only')
    
    args = parser.parse_args()
    
    # Get log file
    log_file = get_log_file(args.date)
    
    print(f"{Colors.BOLD}Viewing: {log_file.name}{Colors.RESET}")
    
    # Follow mode
    if args.follow:
        follow_logs(log_file, args.verbose)
        return
    
    # Read and filter logs
    entries = read_logs(
        log_file,
        user_filter=args.user,
        action_filter=args.action,
        event_filter=args.event,
        tail=args.tail
    )
    
    # Show summary
    if args.summary:
        print_summary(entries)
        return
    
    # Print header
    print()
    print(f"{Colors.BOLD}{Colors.GRAY}{'TIME':<10} {'✓':<2} {'EVENT TYPE':<30} {'USER':<15} {'ACTION':<30}{Colors.RESET}")
    print(f"{Colors.GRAY}{'─' * 100}{Colors.RESET}")
    
    # Print entries
    for entry in entries:
        print(format_log_entry(entry, args.verbose))
    
    # Print summary at the end
    print_summary(entries)


if __name__ == '__main__':
    main()
