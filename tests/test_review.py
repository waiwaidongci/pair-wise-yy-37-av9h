import tempfile, unittest
from pathlib import Path
from src.domain import ConflictError, NotFoundError, PermissionDenied, ValidationError
from src.repository import Repository
from src.service import Service
from src.rules import STATES, TRANSITION_ROLES
class ReviewTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.repo=Repository(str(Path(self.tmp.name)/"test.db")); self.service=Service(self.repo)
        self.item=self.service.create_item({"title":"review item","description":"review scenarios","severity":'medium',"quantity":2,"threshold":10,"external_ref":"RV-ITEM"},"creator",'applicant')
        self.record=self.service.add_record(self.item["id"],{"kind":"correction","detail":"fix scrubber","status":"open","external_ref":"COR-1"},"inspector0",'inspector')
    def tearDown(self): self.repo.close(); self.tmp.cleanup()
    def _to_correction(self):
        current=self.service.get_item(self.item["id"],"viewer")
        for target in STATES[1:-1]: current=self.service.transition(current["id"],target,current["version"],"reviewer",TRANSITION_ROLES[target][0])
        return current
    def test_review_passes_and_shows_in_list(self):
        reviewed=self.service.review_record(self.item["id"],self.record["id"],{"review_note":"materials verified","review_ref":"RV-100"},"inspector1",'inspector')
        self.assertEqual(reviewed["review_note"],"materials verified"); self.assertEqual(reviewed["review_ref"],"RV-100")
        self.assertEqual(reviewed["reviewed_by"],"inspector1"); self.assertEqual(reviewed["status"],"closed")
        listed=self.service.list_records(self.item["id"],"compliance_manager")
        self.assertEqual(listed[0]["review_note"],"materials verified"); self.assertEqual(listed[0]["review_ref"],"RV-100")
    def test_review_rejects_duplicate_and_repeated_submission(self):
        self.service.review_record(self.item["id"],self.record["id"],{"review_note":"first pass","review_ref":"RV-200"},"inspector1",'inspector')
        with self.assertRaises(ConflictError): self.service.review_record(self.item["id"],self.record["id"],{"review_note":"overwrite attempt","review_ref":"RV-201"},"inspector1",'inspector')
        other=self.service.add_record(self.item["id"],{"kind":"correction","detail":"second issue","status":"open","external_ref":"COR-2"},"inspector0",'inspector')
        with self.assertRaises(ConflictError): self.service.review_record(self.item["id"],other["id"],{"review_note":"duplicate ref","review_ref":"RV-200"},"inspector1",'inspector')
        listed=self.service.list_records(self.item["id"],"viewer")
        self.assertEqual(listed[0]["review_note"],"first pass"); self.assertEqual(listed[0]["review_ref"],"RV-200")
        self.assertIsNone(listed[1]["review_ref"])
    def test_review_role_and_validation_guards(self):
        with self.assertRaises(PermissionDenied): self.service.review_record(self.item["id"],self.record["id"],{"review_note":"x","review_ref":"RV-300"},"creator",'applicant')
        with self.assertRaises(PermissionDenied): self.service.review_record(self.item["id"],self.record["id"],{"review_note":"x","review_ref":"RV-300"},"boss",'compliance_manager')
        with self.assertRaises(ValidationError): self.service.review_record(self.item["id"],self.record["id"],{"review_note":"","review_ref":"RV-300"},'inspector1','inspector')
        with self.assertRaises(ValidationError): self.service.review_record(self.item["id"],self.record["id"],{"review_note":"x","review_ref":""},'inspector1','inspector')
        with self.assertRaises(NotFoundError): self.service.review_record(self.item["id"],9999,{"review_note":"x","review_ref":"RV-300"},'inspector1','inspector')
    def test_approval_requires_all_records_reviewed(self):
        current=self._to_correction()
        with self.assertRaises(ConflictError): self.service.transition(current["id"],STATES[-1],current["version"],"boss",TRANSITION_ROLES[STATES[-1]][0])
        self.service.review_record(self.item["id"],self.record["id"],{"review_note":"verified","review_ref":"RV-400"},"inspector1",'inspector')
        current=self.service.get_item(self.item["id"],"viewer")
        approved=self.service.transition(current["id"],STATES[-1],current["version"],"boss",TRANSITION_ROLES[STATES[-1]][0])
        self.assertEqual(approved["status"],STATES[-1])
        actions=[e["action"] for e in self.service.audit("viewer",self.item["id"])]
        self.assertIn("review",actions); self.assertIn("transition",actions); self.assertTrue(self.repo.verify_audit_chain())
if __name__=="__main__": unittest.main()
