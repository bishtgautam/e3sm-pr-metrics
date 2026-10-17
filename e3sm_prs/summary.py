"""Turn a PR record into an integration timeline."""

from datetime import datetime, timezone


def ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


def days(a, b):
    return (b - a).total_seconds() / 86400 if a and b else None


def phases(rec, now=None):
    """Ordered (label, start, end) phases; ``end`` is None for a phase still running."""
    now = now or datetime.now(timezone.utc)
    created, ready = ts(rec["createdAt"]), ts(rec["readyAt"])
    review, approval = ts(rec["firstReviewAt"]), ts(rec["lastApprovalAt"])
    nxt, merged = ts(rec["nextAt"]), ts(rec["mergedAt"])
    end = merged or ts(rec["closedAt"]) or now

    out = []
    if ready and ready > created:
        out.append(("Draft", created, ready))
    start = ready or created
    if review and review >= start:
        out.append(("Waiting for first review", start, review))
        start = review
    if approval and approval >= start:
        out.append(("In review until last approval", start, approval))
        start = approval
    if nxt and nxt >= start:
        out.append(("Approved, waiting for merge to next", start, nxt))
        out.append(("Testing on next, waiting for master", nxt, merged))
    elif merged:
        out.append(("Waiting for merge to master", start, merged))
    elif rec["state"] == "OPEN":
        out.append(("Open (current stage)", start, None))
    else:
        out.append(("Closed without merge", start, end))
    return out


def text(rec, now=None):
    now = now or datetime.now(timezone.utc)
    fmt = lambda d: d.strftime("%Y-%m-%d %H:%M UTC") if d else "-"
    created, merged = ts(rec["createdAt"]), ts(rec["mergedAt"])
    by = rec["componentsBy"]
    lines = [
        f"PR #{rec['number']}: {rec['title']}",
        f"  {rec['url']}",
        f"  author {rec['author']}  branch {rec['branch']}  state {rec['state']}",
        f"  components: {', '.join(rec['components']) or '-'}"
        f"   (files: {', '.join(by['files']) or '-'}; labels: {', '.join(by['labels']) or '-'};"
        f" branch: {', '.join(by['branch']) or '-'})",
        f"  labels: {', '.join(rec['labels']) or '-'}",
        "",
        f"  {'Opened':<32}{fmt(created)}",
    ]
    milestones = [
        ("Ready for review", rec["readyAt"], None),
        ("First review", rec["firstReviewAt"], rec["firstReviewer"]),
        ("Last approval", rec["lastApprovalAt"], ", ".join(rec["approvers"]) or None),
        ("Merged to next", rec["nextAt"], rec["nextSha"]),
        ("Merged to master", rec["mergedAt"], rec["mergedBy"]),
    ]
    for label, when, who in milestones:
        d = ts(when)
        if not d or (label == "Ready for review" and d == created):
            continue
        lines.append(f"  {label:<32}{fmt(d)}  +{days(created, d):6.1f} d"
                     + (f"  ({who})" if who else ""))
    lines.append("")
    lines.append("  Time in each stage:")
    for label, a, b in phases(rec, now):
        lines.append(f"    {label:<40}{days(a, b or now):6.1f} d" + ("  (ongoing)" if b is None else ""))
    total_end = merged or ts(rec["closedAt"]) or now
    what = "opened -> merged to master" if merged else (
        "opened -> closed (not merged)" if rec["closedAt"] else "open so far")
    lines.append("")
    lines.append(f"  Total: {days(created, total_end):.1f} days ({what})")
    return "\n".join(lines)
