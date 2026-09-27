import tempfile, unittest
from pathlib import Path
from src.repository import Repository
from src.service import Service
from src.rules import STATES, TRANSITION_ROLES
class WorkflowTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.repo=Repository(str(Path(self.tmp.name)/"test.db")); self.service=Service(self.repo)
    def tearDown(self): self.repo.close(); self.tmp.cleanup()
    def test_complete_workflow_and_audit(self):
        item=self.service.create_item({"title":"workflow item","description":"complete business flow","severity":'high',"quantity":12,"threshold":6,"external_ref":"WF-1"},"creator",'applicant')
        self.assertEqual(item["status"],STATES[0])
        record=self.service.add_record(item["id"],{"kind":"evidence","detail":"evidence registered","status":"closed","external_ref":"EV-1"},"recorder",'applicant')
        reviewed=self.service.review_record(item["id"],record["id"],{"review_note":"rectification verified on site","review_ref":"RV-1"},"inspector1",'inspector')
        self.assertEqual(reviewed["review_note"],"rectification verified on site"); self.assertEqual(reviewed["review_ref"],"RV-1"); self.assertEqual(reviewed["status"],"closed")
        current=item
        for target in STATES[1:]:
            current=self.service.transition(current["id"],target,current["version"],"reviewer",TRANSITION_ROLES[target][0])
        self.assertEqual(current["status"],STATES[-1])
        records=self.service.list_records(current["id"],"viewer"); self.assertEqual(len(records),1)
        self.assertEqual(records[0]["review_ref"],"RV-1"); self.assertEqual(records[0]["review_note"],"rectification verified on site")
        events=self.service.audit("viewer",current["id"]); self.assertGreaterEqual(len(events),len(STATES)+2)
        actions=[e["action"] for e in events]; self.assertIn("review",actions); self.assertIn("transition",actions)
        self.assertTrue(self.repo.verify_audit_chain())
if __name__=="__main__": unittest.main()
