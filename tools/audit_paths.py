#!/usr/bin/env python3
"""Check the component map against the full history of an E3SM clone.

Lists every directory changed on master (with first/last commit dates) and
the component it maps to, flagging ``components/*`` and ``models/*``
directories that fall through to "infrastructure" -- usually a renamed or
new component that needs adding to e3sm_prs/components.py.

    python3 tools/audit_paths.py ~/projects/e3sm/e3sm [--ref origin/master]
"""

import argparse
import subprocess
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from e3sm_prs.components import DEFAULT_PATH_COMPONENT, PATH_PREFIXES, from_dirs, path_dir  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("clone", type=Path)
    ap.add_argument("--ref", default="origin/master")
    ap.add_argument("--min-commits", type=int, default=20)
    args = ap.parse_args()

    log = subprocess.run(["git", "-C", str(args.clone), "log", args.ref, "--format=@%cs", "--name-only"],
                         capture_output=True, text=True, check=True).stdout
    count, first, last, date = Counter(), {}, {}, None
    for line in log.splitlines():
        if line.startswith("@"):
            date = line[1:]
        elif line:
            d = path_dir(line)
            if "/" not in line:
                continue
            count[d] += 1
            last.setdefault(d, date)
            first[d] = date

    flagged = 0
    print(f"{'commits':>8}  {'first':10}  {'last':10}  {'directory':34} component")
    for d in sorted(count):
        if count[d] < args.min_commits:
            continue
        comp = from_dirs([d])[0]
        flag = ""
        if d not in PATH_PREFIXES and d.split("/")[0] in ("components", "models"):
            flag, flagged = "   <-- unmapped model directory?", flagged + 1
        print(f"{count[d]:8d}  {first[d]}  {last[d]}  {d:34} {comp}{flag}")
    print(f"\n{flagged} model directories are not mapped explicitly (they count as '{DEFAULT_PATH_COMPONENT}')")


if __name__ == "__main__":
    main()
