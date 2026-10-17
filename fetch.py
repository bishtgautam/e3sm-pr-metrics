#!/usr/bin/env python3
"""Update site/data/prs.json with E3SM pull requests targeting master.

    GITHUB_TOKEN=... python3 fetch.py            # incremental (or full on first run)
    GITHUB_TOKEN=... python3 fetch.py --full     # refetch everything
    GITHUB_TOKEN=... python3 fetch.py --limit 50 # quick test
    python3 fetch.py --reclassify                # re-apply component rules, no API calls
"""

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from e3sm_prs.components import COMPONENTS, classify
from e3sm_prs.github import iter_updated

SCHEMA = 1


def load(path):
    if not path.exists():
        return {}, None
    data = json.loads(path.read_text())
    if data.get("schema") != SCHEMA:
        return {}, None
    return {p["number"]: p for p in data["prs"]}, data.get("fetchedAt")


def save(path, prs, fetched_at):
    path.parent.mkdir(parents=True, exist_ok=True)
    out = {
        "schema": SCHEMA,
        "repo": "E3SM-Project/E3SM",
        "fetchedAt": fetched_at,
        "components": COMPONENTS,
        "prs": sorted(prs.values(), key=lambda p: -p["number"]),
    }
    path.write_text(json.dumps(out, separators=(",", ":")))
    print(f"wrote {len(prs)} PRs to {path} ({path.stat().st_size / 1e6:.1f} MB)", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=Path("site/data/prs.json"))
    ap.add_argument("--full", action="store_true", help="ignore existing data and refetch all PRs")
    ap.add_argument("--limit", type=int, help="stop after N PRs (testing)")
    ap.add_argument("--reclassify", action="store_true",
                    help="only re-run component classification on existing data")
    args = ap.parse_args()

    prs, last = load(args.out)
    if args.reclassify:
        for p in prs.values():
            p["components"], p["componentsBy"] = classify(p["dirs"], p["labels"], p["branch"])
        save(args.out, prs, last)
        return

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    stop = None
    if prs and last and not args.full:
        # re-read a day of overlap so nothing is missed between runs
        stop = (datetime.fromisoformat(last.replace("Z", "+00:00")) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        print(f"incremental update: PRs updated since {stop}", file=sys.stderr)
    elif args.full:
        prs = {}

    n = 0
    for rec in iter_updated(stop_before=stop, limit=args.limit):
        prs[rec["number"]] = rec
        n += 1
    print(f"fetched {n} PRs", file=sys.stderr)
    # a --limit run is partial, so don't let the next run treat it as complete
    save(args.out, prs, last if args.limit else now)


if __name__ == "__main__":
    main()
