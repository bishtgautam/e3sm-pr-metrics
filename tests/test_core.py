"""Offline tests: python3 -m unittest discover tests"""

import unittest

from e3sm_prs.components import classify, from_branch, from_dirs, path_dir
from e3sm_prs.github import to_record
from e3sm_prs.summary import days, phases, text, ts

# Shape of a GraphQL node, with the real milestones of E3SM PR #8705
# (the file list is illustrative, to exercise multi-component PRs).
PR_8705 = {
    "number": 8705, "title": "fixes energy conservation in ocean frazil routine",
    "url": "https://github.com/E3SM-Project/E3SM/pull/8705",
    "state": "MERGED", "isDraft": False,
    "createdAt": "2026-09-04T16:59:13Z", "updatedAt": "2026-10-16T18:58:17Z",
    "closedAt": "2026-10-16T18:42:53Z", "mergedAt": "2026-10-16T18:42:53Z",
    "headRefName": "njeffery/ocean/fix-frazil-energy", "baseRefName": "master",
    "additions": 1, "deletions": 1, "changedFiles": 3,
    "author": {"login": "njeffery"}, "mergedBy": {"login": "jonbob"},
    "labels": {"nodes": [{"name": n} for n in ["MPAS-ocean", "bug fix PR", "NML", "non-BFB"]]},
    "files": {"pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": [
        {"path": "components/mpas-ocean/src/shared/mpas_ocn_frazil_forcing.F"},
        {"path": "components/mpas-ocean/bld/build-namelist"},
        {"path": "components/mpas-albany-landice/src/Registry.xml"},
    ]},
    "reviews": {"nodes": [
        {"state": "COMMENTED", "submittedAt": "2026-09-04T17:04:13Z",
         "author": {"login": "copilot-pull-request-reviewer", "__typename": "Bot"}},
        {"state": "COMMENTED", "submittedAt": "2026-09-22T17:16:38Z",
         "author": {"login": "vanroekel", "__typename": "User"}},
    ]},
    "approvals": {"nodes": [
        {"submittedAt": "2026-09-22T21:03:32Z", "author": {"login": "cbegeman", "__typename": "User"}},
        {"submittedAt": "2026-09-22T21:10:40Z", "author": {"login": "vanroekel", "__typename": "User"}},
        {"submittedAt": "2026-10-12T18:22:40Z", "author": {"login": "proteanplanet", "__typename": "User"}},
    ]},
    "drafts": {"nodes": []},
    "refs": {"nodes": [
        {},  # cross-references from other sources come back empty
        {"createdAt": "2026-10-15T18:35:10Z", "commit": {
            "oid": "40d946d75f0000000000",
            "messageHeadline": "Merge branch 'njeffery/ocean/fix-frazil-energy' into next (PR #8705)"}},
    ]},
}


class Components(unittest.TestCase):
    def test_path_dir(self):
        self.assertEqual(path_dir("components/elm/src/main/foo.F90"), "components/elm")
        self.assertEqual(path_dir("driver-mct/main/x.F90"), "driver-mct")
        self.assertEqual(path_dir("README.md"), "README.md")

    def test_historical_names(self):
        self.assertEqual(from_dirs(["models/lnd", "components/clm", "components/elm"]), ["land"])
        self.assertEqual(from_dirs(["components/scream"]), ["eamxx"])
        self.assertEqual(from_dirs(["components/mpas-o"]), ["ocean"])

    def test_branch(self):
        self.assertEqual(from_branch("bishtgautam/lnd/soil-temperature-refactor"), ["land"])
        self.assertEqual(from_branch("claude/eamxx-ci/unify-gpu-jobs"), ["eamxx"])
        self.assertEqual(from_branch("ccr-38ca8368-hmc48r"), [])

    def test_infrastructure_dropped_when_model_code_touched(self):
        best, by = classify(["components/elm", "cime_config"], [], "")
        self.assertEqual(best, ["land"])
        self.assertEqual(by["files"], ["infrastructure", "land"])
        best, _ = classify(["cime_config"], ["ELM"], "")
        self.assertEqual(best, ["infrastructure"])

    def test_wrong_label_does_not_win(self):
        best, by = classify(["components/mosart"], ["ELM"], "user/lnd/x")
        self.assertEqual(best, ["river"])
        self.assertEqual(by["labels"], ["land"])


class Record(unittest.TestCase):
    def setUp(self):
        self.rec = to_record(PR_8705)

    def test_milestones(self):
        r = self.rec
        self.assertEqual(r["readyAt"], r["createdAt"])
        self.assertEqual(r["firstReviewer"], "vanroekel")  # Copilot ignored
        self.assertEqual(r["lastApprovalAt"], "2026-10-12T18:22:40Z")
        self.assertEqual(r["nextAt"], "2026-10-15T18:35:10Z")
        self.assertEqual(r["components"], ["landice", "ocean"])
        self.assertEqual(r["componentsBy"]["labels"], ["ocean"])

    def test_phases_add_up(self):
        ph = phases(self.rec)
        self.assertEqual([p[0] for p in ph], [
            "Waiting for first review", "In review until last approval",
            "Approved, waiting for merge to next", "Testing on next, waiting for master"])
        total = sum(days(a, b) for _, a, b in ph)
        self.assertAlmostEqual(total, days(ts(self.rec["createdAt"]), ts(self.rec["mergedAt"])))
        self.assertIn("Total: 42.1 days", text(self.rec))

    def test_draft_then_ready(self):
        pr = dict(PR_8705, drafts={"nodes": [
            {"__typename": "ReadyForReviewEvent", "createdAt": "2026-09-10T00:00:00Z"}]})
        rec = to_record(pr)
        self.assertEqual(rec["readyAt"], "2026-09-10T00:00:00Z")
        self.assertEqual(phases(rec)[0][0], "Draft")

    def test_next_merge_of_other_branch_ignored(self):
        pr = dict(PR_8705, refs={"nodes": [{"createdAt": "2026-10-01T00:00:00Z", "commit": {
            "oid": "x" * 10, "messageHeadline": "Merge branch 'someone/else' into next (PR #8000)"}}]})
        self.assertIsNone(to_record(pr)["nextAt"])


if __name__ == "__main__":
    unittest.main()
