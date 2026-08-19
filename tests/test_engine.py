import json
import os
import tempfile
import unittest
from pathlib import Path


def _prep_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    os.environ["N8NFLOW_DB"] = tmp.name
    return tmp.name


DBFILE = _prep_db()

from n8nflow import db  # noqa: E402
from n8nflow.engine import connect_nodes, execute_workflow  # noqa: E402
from n8nflow.expressions import compare, interpolate  # noqa: E402
from n8nflow.seed import examples  # noqa: E402


class ExpressionsTest(unittest.TestCase):
    def test_json_path(self):
        ctx = {"item": {"json": {"user": {"name": "Ali"}, "n": 3}}}
        self.assertEqual(interpolate("Hi {{ $json.user.name }}", ctx), "Hi Ali")
        self.assertEqual(interpolate("{{ $json.n }}", ctx), 3)

    def test_compare(self):
        self.assertTrue(compare(200, "equals", "200"))
        self.assertTrue(compare("hello world", "contains", "world"))
        self.assertTrue(compare(5, "gt", 2))
        self.assertTrue(compare(None, "isEmpty", None))


class EngineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.init_db()

    def test_hello_workflow(self):
        wf = examples()[0]
        wf["id"] = db.new_id()
        res = execute_workflow(wf, mode="manual", persist=True)
        self.assertEqual(res["status"], "success", res.get("error"))
        self.assertTrue(res["items"])
        self.assertIn("سلام", str(res["items"][0].get("message", "")))

    def test_set_and_if(self):
        nodes = [
            {
                "id": "t",
                "name": "Manual Trigger",
                "type": "n8n-nodes-base.manualTrigger",
                "position": [0, 0],
                "parameters": {},
            },
            {
                "id": "s",
                "name": "Set",
                "type": "n8n-nodes-base.set",
                "position": [200, 0],
                "parameters": {"assignments": "status=200\nok=yes", "includeOtherFields": True},
            },
            {
                "id": "i",
                "name": "IF",
                "type": "n8n-nodes-base.if",
                "position": [400, 0],
                "parameters": {"left": "{{ $json.status }}", "operator": "equals", "right": "200"},
            },
            {
                "id": "y",
                "name": "Yes",
                "type": "n8n-nodes-base.set",
                "position": [600, 0],
                "parameters": {"assignments": "branch=true", "includeOtherFields": True},
            },
            {
                "id": "n",
                "name": "No",
                "type": "n8n-nodes-base.set",
                "position": [600, 160],
                "parameters": {"assignments": "branch=false", "includeOtherFields": True},
            },
        ]
        wf = {"id": db.new_id(), "name": "if-test", "nodes": nodes, "connections": {}, "active": False}
        connect_nodes(wf, "Manual Trigger", "Set")
        connect_nodes(wf, "Set", "IF")
        connect_nodes(wf, "IF", "Yes", 0)
        connect_nodes(wf, "IF", "No", 1)
        res = execute_workflow(wf, mode="manual", persist=False)
        self.assertEqual(res["status"], "success", res.get("error"))
        self.assertEqual(res["items"][0].get("branch"), "true")

    def test_code_node(self):
        nodes = [
            {
                "id": "t",
                "name": "Manual Trigger",
                "type": "n8n-nodes-base.manualTrigger",
                "position": [0, 0],
                "parameters": {},
            },
            {
                "id": "c",
                "name": "Code",
                "type": "n8n-nodes-base.code",
                "position": [200, 0],
                "parameters": {"mode": "all", "code": "result = [{'json': {'n': len(items) + 41}}]"},
            },
        ]
        wf = {"id": db.new_id(), "name": "code", "nodes": nodes, "connections": {}, "active": False}
        connect_nodes(wf, "Manual Trigger", "Code")
        res = execute_workflow(wf, mode="manual", persist=False)
        self.assertEqual(res["status"], "success", res.get("error"))
        self.assertEqual(res["items"][0]["n"], 42)

    def test_http_placeholder(self):
        from unittest.mock import MagicMock, patch

        import n8nflow.nodes as node_mod

        wf = examples()[1]
        wf["id"] = db.new_id()
        fake = MagicMock()
        fake.status_code = 200
        fake.headers = {"content-type": "application/json"}
        fake.json.return_value = {"title": "buy milk", "id": 1, "completed": False}
        fake.url = "https://jsonplaceholder.typicode.com/todos/1"
        fake.ok = True
        with patch.object(node_mod.requests, "request", return_value=fake):
            res = execute_workflow(wf, mode="manual", persist=False)
        self.assertEqual(res["status"], "success", res.get("error"))
        self.assertEqual(res["items"][0].get("todo"), "buy milk")


if __name__ == "__main__":
    unittest.main()
