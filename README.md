# E3SM PR integration dashboard

Tracks how long pull requests to `master` of
[E3SM-Project/E3SM](https://github.com/E3SM-Project/E3SM) take to integrate, by
component and over time. A GitHub Actions job refreshes the data every night and
publishes a static dashboard to GitHub Pages.

## What it measures

For every PR targeting `master` it records:

| milestone | source |
|---|---|
| opened, ready for review | PR creation, `ReadyForReviewEvent` (draft time can be excluded) |
| first review | first review by someone other than the author (bots/Copilot ignored) |
| last approval | last `APPROVED` review before the merge |
| merged to `next` | the `Merge branch '<branch>' into next (PR #N)` commit referenced on the PR |
| merged to `master` | `mergedAt` |

and from those the time spent in each stage: waiting for review → in review →
approved, waiting for `next` → testing on `next`, waiting for `master`.

### Components

Each PR is classified three ways, and all three are kept:

* **files**: directories the PR changes (most reliable). Every historical name is
  mapped (`models/lnd`, `components/clm`, `components/elm` → land; `mpas-o`,
  `mpas-ocean`, `omega` → ocean; `cam`, `eam` → atmosphere; `scream`, `eamxx` →
  EAMxx; ...). See [`e3sm_prs/components.py`](e3sm_prs/components.py).
* **labels**: GitHub labels (`ELM`, `MOSART`, `MPAS-ocean`, ...).
* **branch**: the `<user>/<comp>/<topic>` naming convention.

The dashboard uses files, then labels, then branch, and flags PRs whose labels
disagree with the files they change. To check the mapping against the whole
history of a local clone (it flags any `components/*` directory that isn't
mapped):

```bash
python3 tools/audit_paths.py ~/projects/e3sm/e3sm
```

After editing the mapping, re-apply it to existing data without calling GitHub:

```bash
python3 fetch.py --reclassify
```

## Local use

Needs Python 3.9+ and nothing else. Provide a GitHub token, either in
`GITHUB_TOKEN` or in `~/.config/e3sm-pr-metrics/token`. Read-only access to public
repositories is enough.

```bash
python3 fetch.py                       # first run: all PRs (a few minutes); then incremental
python3 pr_summary.py 8705             # integration timeline of one PR
python3 -m http.server -d site 8000    # dashboard at http://localhost:8000
python3 -m unittest discover tests
```

## Publishing

1. Push this repo to GitHub (e.g. under `E3SM-Project` or your account).
2. Settings → Pages → Source: **GitHub Actions**.
3. Actions → *Update dashboard* → **Run workflow**.

The workflow runs daily at 06:17 UTC, on every push to `main`, and on demand. It
uses the built-in `GITHUB_TOKEN` and needs no secrets. Each run starts from the
previously published `data/prs.json` and fetches only PRs updated since then.

Filters are kept in the URL, so a link to a filtered view (for example land and
river over the last 3 months) can be shared directly.

## Later

* Use the local git history (`git log origin/next --merges`) to backfill
  merge-to-next times for old PRs whose timeline lacks the reference.
* Classify by the merge commit's diff instead of the PR file list for PRs whose
  file list GitHub truncates (over 3000 files).
