"""Fetch E3SM pull requests from the GitHub GraphQL API (stdlib only)."""

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

from .components import classify, path_dir

API = "https://api.github.com/graphql"
OWNER, NAME = "E3SM-Project", "E3SM"

PR_FIELDS = """
fragment PR on PullRequest {
  number title url state isDraft createdAt updatedAt closedAt mergedAt
  headRefName baseRefName additions deletions changedFiles
  author { login }
  mergedBy { login }
  labels(first: 40) { nodes { name } }
  files(first: 100) { pageInfo { hasNextPage endCursor } nodes { path } }
  reviews(first: 30) { nodes { state submittedAt author { login __typename } } }
  approvals: reviews(last: 30, states: [APPROVED]) {
    nodes { submittedAt author { login __typename } }
  }
  drafts: timelineItems(first: 20, itemTypes: [READY_FOR_REVIEW_EVENT, CONVERT_TO_DRAFT_EVENT]) {
    nodes {
      __typename
      ... on ReadyForReviewEvent { createdAt }
      ... on ConvertToDraftEvent { createdAt }
    }
  }
  refs: timelineItems(last: 60, itemTypes: [REFERENCED_EVENT]) {
    nodes { ... on ReferencedEvent { createdAt commit { oid messageHeadline } } }
  }
}
"""

LIST_QUERY = PR_FIELDS + """
query($owner: String!, $name: String!, $first: Int!, $after: String) {
  rateLimit { cost remaining resetAt }
  repository(owner: $owner, name: $name) {
    pullRequests(baseRefName: "master", first: $first, after: $after,
                 orderBy: {field: UPDATED_AT, direction: DESC}) {
      pageInfo { hasNextPage endCursor }
      nodes { ...PR }
    }
  }
}
"""

ONE_QUERY = PR_FIELDS + """
query($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) { pullRequest(number: $number) { ...PR } }
}
"""

FILES_QUERY = """
query($owner: String!, $name: String!, $number: Int!, $after: String) {
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      files(first: 100, after: $after) { pageInfo { hasNextPage endCursor } nodes { path } }
    }
  }
}
"""


TOKEN_FILE = os.path.expanduser("~/.config/e3sm-pr-metrics/token")


def token():
    tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not tok and os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE) as f:
            tok = f.read().strip()
    if not tok:
        sys.exit(f"Set GITHUB_TOKEN or save a token in {TOKEN_FILE} (public read access is enough).")
    return tok


def graphql(query, variables, retries=5):
    body = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(API, data=body, headers={
        "Authorization": f"bearer {token()}",
        "Content-Type": "application/json",
        "User-Agent": "e3sm-pr-metrics",
    })
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                out = json.load(r)
            if out.get("errors"):
                msg = json.dumps(out["errors"])[:500]
                if "RATE_LIMITED" in msg:
                    time.sleep(60)
                    continue
                raise RuntimeError(msg)
            return out["data"]
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
            code = getattr(e, "code", None)
            if code in (401, 403) and attempt == retries - 1:
                raise
            wait = 2 ** attempt * 5
            print(f"  request failed ({e}); retrying in {wait}s", file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError("GitHub API request failed repeatedly")


def _is_human(author, pr_author):
    if not author or author.get("__typename") == "Bot":
        return False
    login = author.get("login", "")
    return login != pr_author and "copilot" not in login.lower()


NEXT_RE = re.compile(r"^Merge (branch|pull request|remote-tracking branch).* into next\b")


def to_record(pr, extra_files=()):
    """Flatten a GraphQL PR node into the compact record stored in prs.json."""
    author = (pr.get("author") or {}).get("login", "ghost")
    labels = [n["name"] for n in pr["labels"]["nodes"]]
    paths = [n["path"] for n in pr["files"]["nodes"]] + list(extra_files)
    dirs = sorted({path_dir(p) for p in paths})

    # Ready for review: if the first draft-related event is "ready", the PR
    # was opened as a draft; otherwise it was ready when opened.
    events = sorted(pr["drafts"]["nodes"], key=lambda n: n["createdAt"])
    ready_at = pr["createdAt"]
    if events and events[0]["__typename"] == "ReadyForReviewEvent":
        ready_at = events[0]["createdAt"]
    if pr["isDraft"]:
        ready_at = None

    reviews = [r for r in pr["reviews"]["nodes"]
               if r.get("submittedAt") and _is_human(r.get("author"), author)]
    first_review = min(reviews, key=lambda r: r["submittedAt"], default=None)
    approvals = [r for r in pr["approvals"]["nodes"]
                 if r.get("submittedAt") and _is_human(r.get("author"), author)]
    if pr["mergedAt"]:
        approvals = [r for r in approvals if r["submittedAt"] <= pr["mergedAt"]]
    last_approval = max(approvals, key=lambda r: r["submittedAt"], default=None)

    # Merge to next: E3SM integrators merge the branch into ``next`` for
    # nightly testing, which shows up as a referenced commit on the PR.
    next_at = next_sha = None
    tag = f"(PR #{pr['number']})"
    branch = f"'{pr['headRefName']}'" if pr["headRefName"] not in ("master", "main", "next") else None
    for ref in sorted((n for n in pr["refs"]["nodes"] if n and n.get("commit")),
                      key=lambda n: n["createdAt"]):
        head = ref["commit"]["messageHeadline"]
        # a re-merge to next after the PR reached master is not its integration
        if pr["mergedAt"] and ref["createdAt"] > pr["mergedAt"]:
            continue
        if NEXT_RE.search(head) and (tag in head or (branch and branch in head)):
            next_at, next_sha = ref["createdAt"], ref["commit"]["oid"][:10]
            break

    components, by = classify(dirs, labels, pr["headRefName"])
    return {
        "number": pr["number"],
        "title": pr["title"],
        "url": pr["url"],
        "author": author,
        "state": pr["state"],  # OPEN / CLOSED / MERGED
        "draft": pr["isDraft"],
        "branch": pr["headRefName"],
        "labels": labels,
        "dirs": dirs,
        "changedFiles": pr["changedFiles"],
        "additions": pr["additions"],
        "deletions": pr["deletions"],
        "createdAt": pr["createdAt"],
        "updatedAt": pr["updatedAt"],
        "readyAt": ready_at,
        "firstReviewAt": first_review and first_review["submittedAt"],
        "firstReviewer": first_review and first_review["author"]["login"],
        "lastApprovalAt": last_approval and last_approval["submittedAt"],
        "approvers": sorted({r["author"]["login"] for r in approvals}),
        "nextAt": next_at,
        "nextSha": next_sha,
        "mergedAt": pr["mergedAt"],
        "mergedBy": (pr.get("mergedBy") or {}).get("login"),
        "closedAt": pr["closedAt"],
        "components": components,
        "componentsBy": by,
    }


def _remaining_files(pr):
    """Page through the changed files of a PR with more than 100 of them."""
    paths, info = [], pr["files"]["pageInfo"]
    while info["hasNextPage"] and len(paths) < 3000:
        data = graphql(FILES_QUERY, {"owner": OWNER, "name": NAME,
                                     "number": pr["number"], "after": info["endCursor"]})
        files = data["repository"]["pullRequest"]["files"]
        paths += [n["path"] for n in files["nodes"]]
        info = files["pageInfo"]
    return paths


def fetch_one(number):
    data = graphql(ONE_QUERY, {"owner": OWNER, "name": NAME, "number": number})
    pr = data["repository"]["pullRequest"]
    if pr is None:
        raise SystemExit(f"PR #{number} not found in {OWNER}/{NAME}")
    return to_record(pr, _remaining_files(pr))


def iter_updated(stop_before=None, page_size=40, limit=None):
    """Yield records, most recently updated first.

    Stops once PRs are older than ``stop_before`` (an ISO timestamp), which
    makes nightly runs incremental.
    """
    after, seen = None, 0
    while True:
        data = graphql(LIST_QUERY, {"owner": OWNER, "name": NAME,
                                    "first": page_size, "after": after})
        conn = data["repository"]["pullRequests"]
        rl = data["rateLimit"]
        print(f"  page of {len(conn['nodes'])} PRs (rate limit left {rl['remaining']})",
              file=sys.stderr)
        for pr in conn["nodes"]:
            if stop_before and pr["updatedAt"] < stop_before:
                return
            yield to_record(pr, _remaining_files(pr))
            seen += 1
            if limit and seen >= limit:
                return
        if not conn["pageInfo"]["hasNextPage"]:
            return
        after = conn["pageInfo"]["endCursor"]
