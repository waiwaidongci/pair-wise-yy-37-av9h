import tempfile, unittest
from pathlib import Path
from src.domain import ConflictError, NotFoundError, PermissionDenied, ValidationError
from src.repository import Repository
from src.service import Service
from src.rules import STATES, TRANSITION_ROLES


class ReviewTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Repository(str(Path(self.tmp.name) / "test.db"))
        self.service = Service(self.repo)
        self.item = self.service.create_item(
            {"title": "review item", "description": "multi record review",
             "severity": 'high', "quantity": 8, "threshold": 4,
             "external_ref": "REV-1"}, "creator", 'applicant')
        self.r1 = self.service.add_record(
            self.item["id"], {"kind": "action", "detail": "fix seal",
                              "status": "open", "external_ref": "RC-1"},
            "recorder", 'inspector')
        self.r2 = self.service.add_record(
            self.item["id"], {"kind": "action", "detail": "replace filter",
                              "status": "open", "external_ref": "RC-2"},
            "recorder", 'inspector')

    def tearDown(self):
        self.repo.close()
        self.tmp.cleanup()

    def _to_correction(self):
        current = self.service.get_item(self.item["id"], "viewer")
        for target in STATES[1:-1]:
            current = self.service.transition(
                current["id"], target, current["version"],
                "reviewer", TRANSITION_ROLES[target][0])
        return current

    def test_review_pass_shows_in_list_and_closes_record(self):
        record = self.service.review_record(
            self.item["id"], self.r1["id"],
            {"review_note": "on-site recheck passed", "review_ref": "FS-2026-001"},
            "inspector1", 'inspector')
        self.assertEqual(record["review_note"], "on-site recheck passed")
        self.assertEqual(record["review_ref"], "FS-2026-001")
        self.assertEqual(record["status"], "closed")
        listed = {r["id"]: r for r in self.service.list_records(self.item["id"], "viewer")}
        self.assertEqual(listed[self.r1["id"]]["review_ref"], "FS-2026-001")
        self.assertEqual(listed[self.r1["id"]]["reviewed_by"], "inspector1")
        self.assertIsNone(listed[self.r2["id"]]["review_ref"])

    def test_duplicate_submit_and_duplicate_ref_rejected_without_overwrite(self):
        payload = {"review_note": "first pass", "review_ref": "FS-2026-002"}
        self.service.review_record(self.item["id"], self.r1["id"], payload,
                                   "inspector1", 'inspector')
        with self.assertRaises(ConflictError):
            self.service.review_record(self.item["id"], self.r1["id"],
                                       {"review_note": "second pass",
                                        "review_ref": "FS-2026-003"},
                                       "inspector2", 'inspector')
        with self.assertRaises(ConflictError):
            self.service.review_record(self.item["id"], self.r2["id"],
                                       {"review_note": "reuse number",
                                        "review_ref": "FS-2026-002"},
                                       "inspector2", 'inspector')
        record = {r["id"]: r for r in self.service.list_records(self.item["id"], "viewer")}[self.r1["id"]]
        self.assertEqual(record["review_note"], "first pass")
        self.assertEqual(record["review_ref"], "FS-2026-002")
        self.assertEqual(record["reviewed_by"], "inspector1")

    def test_review_role_and_validation(self):
        with self.assertRaises(PermissionDenied):
            self.service.review_record(self.item["id"], self.r1["id"],
                                       {"review_note": "x", "review_ref": "FS-1"},
                                       "manager", 'compliance_manager')
        with self.assertRaises(ValidationError):
            self.service.review_record(self.item["id"], self.r1["id"],
                                       {"review_note": "", "review_ref": "FS-1"},
                                       "inspector1", 'inspector')
        with self.assertRaises(ValidationError):
            self.service.review_record(self.item["id"], self.r1["id"],
                                       {"review_note": "ok", "review_ref": " "},
                                       "inspector1", 'inspector')
        with self.assertRaises(NotFoundError):
            self.service.review_record(self.item["id"], 9999,
                                       {"review_note": "ok", "review_ref": "FS-1"},
                                       "inspector1", 'inspector')

    def test_approval_requires_all_records_reviewed(self):
        current = self._to_correction()
        with self.assertRaises(ConflictError):
            self.service.transition(current["id"], STATES[-1], current["version"],
                                    "manager", TRANSITION_ROLES[STATES[-1]][0])
        self.service.review_record(self.item["id"], self.r1["id"],
                                   {"review_note": "pass one", "review_ref": "FS-2026-010"},
                                   "inspector1", 'inspector')
        current = self.service.get_item(self.item["id"], "viewer")
        with self.assertRaises(ConflictError):
            self.service.transition(current["id"], STATES[-1], current["version"],
                                    "manager", TRANSITION_ROLES[STATES[-1]][0])
        self.service.review_record(self.item["id"], self.r2["id"],
                                   {"review_note": "pass two", "review_ref": "FS-2026-011"},
                                   "inspector1", 'inspector')
        current = self.service.get_item(self.item["id"], "viewer")
        approved = self.service.transition(current["id"], STATES[-1], current["version"],
                                           "manager", TRANSITION_ROLES[STATES[-1]][0])
        self.assertEqual(approved["status"], STATES[-1])
        events = self.service.audit("viewer", self.item["id"])
        reviews = [e for e in events if e["action"] == "review"]
        approvals = [e for e in events if e["action"] == "transition"
                     and e["detail"].get("to") == STATES[-1]]
        self.assertEqual(len(reviews), 2)
        self.assertEqual(len(approvals), 1)
        self.assertTrue(self.repo.verify_audit_chain())


if __name__ == "__main__":
    unittest.main()
