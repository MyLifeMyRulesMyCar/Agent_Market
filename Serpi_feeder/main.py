"""
main.py — Google Trends feeder via SerpAPI.

Usage:
    python main.py                              # standard profile, config defaults
    python main.py --profile quick              # only core layer (~3 credits/market)
    python main.py --profile full               # all layers + related queries
    python main.py --range "today 5-y"          # override time range
    python main.py --profile standard --force   # ignore cache, re-fetch everything
    python main.py --credits                    # just show credit status, don't run
"""

import sys
import os
import argparse
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.dirname(__file__))


def main():
    parser = argparse.ArgumentParser(description="Serpi — Google Trends Feeder")
    parser.add_argument("--profile",  type=str, default="standard",
                        choices=["quick", "standard", "full"],
                        help="Run profile: quick | standard | full")
    parser.add_argument("--range",    type=str, default=None,
                        help='Override time range, e.g. "today 5-y" or "now 7-d"')
    parser.add_argument("--force",    action="store_true",
                        help="Ignore cache and re-fetch everything")
    parser.add_argument("--credits",  action="store_true",
                        help="Show credit usage and exit")
    args = parser.parse_args()

    if args.credits:
        # Just show credit status
        import yaml, json
        from scripts.fetch_trends import CreditTracker
        data_dir = Path(os.getcwd()) / "data"
        data_dir.mkdir(exist_ok=True)
        tracker = CreditTracker(data_dir)
        tracker.status()
        return

    from scripts.runner import run
    run(
        profile_name=args.profile,
        time_range_override=args.range,
        force_refresh=args.force,
    )


if __name__ == "__main__":
    main()