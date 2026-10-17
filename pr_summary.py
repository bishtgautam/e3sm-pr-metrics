#!/usr/bin/env python3
"""Summarize how long one E3SM pull request took to integrate.

    python3 pr_summary.py 8705            # from data/prs.json, live API if missing there
    python3 pr_summary.py 8705 --live     # always ask GitHub (needs GITHUB_TOKEN)
    python3 pr_summary.py 8705 --json
"""

import argparse
import json
import os
import sys
from pathlib import Path

from e3sm_prs.summary import text


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("number", type=int)
    ap.add_argument("--data", type=Path, default=Path("site/data/prs.json"))
    ap.add_argument("--live", action="store_true", help="fetch from GitHub instead of the data file")
    ap.add_argument("--json", action="store_true", help="print the raw record")
    args = ap.parse_args()

    rec = None
    if not args.live and args.data.exists():
        prs = json.loads(args.data.read_text())["prs"]
        rec = next((p for p in prs if p["number"] == args.number), None)
    if rec is None:
        from e3sm_prs.github import TOKEN_FILE, fetch_one
        if not (os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or os.path.exists(TOKEN_FILE)):
            sys.exit(f"PR #{args.number} is not in {args.data}; set GITHUB_TOKEN to fetch it live.")
        rec = fetch_one(args.number)
    print(json.dumps(rec, indent=2) if args.json else text(rec))


if __name__ == "__main__":
    main()
