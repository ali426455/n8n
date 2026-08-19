"""Example workflows seeded on first launch."""

from __future__ import annotations

from . import db
from .engine import connect_nodes


def _n(name, type_id, x, y, params=None, nid=None):
    return {
        "id": nid or db.new_id(),
        "name": name,
        "type": type_id,
        "typeVersion": 1,
        "position": [x, y],
        "parameters": params or {},
    }


def examples() -> list[dict]:
    hello_nodes = [
        _n("Manual Trigger", "n8n-nodes-base.manualTrigger", 160, 200),
        _n(
            "Set Greeting",
            "n8n-nodes-base.set",
            400,
            200,
            {"assignments": "message=سلام دنیا — n8n Flow آنلاین است\nlang=fa\nsource=streamlit.app", "includeOtherFields": True},
        ),
        _n("Done", "n8n-nodes-base.noOp", 640, 200),
    ]
    hello = {
        "name": "سلام دنیا",
        "active": False,
        "nodes": hello_nodes,
        "connections": {},
        "tags": ["example"],
        "settings": {},
    }
    connect_nodes(hello, "Manual Trigger", "Set Greeting")
    connect_nodes(hello, "Set Greeting", "Done")

    http_nodes = [
        _n("Manual Trigger", "n8n-nodes-base.manualTrigger", 140, 180),
        _n(
            "HTTP Request",
            "n8n-nodes-base.httpRequest",
            380,
            180,
            {
                "method": "GET",
                "url": "https://jsonplaceholder.typicode.com/todos/1",
                "bodyType": "none",
                "timeout": 20,
            },
        ),
        _n(
            "Edit Fields",
            "n8n-nodes-base.set",
            640,
            180,
            {"assignments": "todo={{ $json.title }}\ncompleted={{ $json.completed }}\nid={{ $json.id }}", "includeOtherFields": False},
        ),
    ]
    http_wf = {
        "name": "HTTP — JSONPlaceholder",
        "active": False,
        "nodes": http_nodes,
        "connections": {},
        "tags": ["example", "http"],
        "settings": {},
    }
    connect_nodes(http_wf, "Manual Trigger", "HTTP Request")
    connect_nodes(http_wf, "HTTP Request", "Edit Fields")

    hook_id = db.new_id()
    hook_nodes = [
        _n(
            "Webhook",
            "n8n-nodes-base.webhook",
            140,
            200,
            {"path": hook_id[:12], "method": "ANY", "responseMode": "responseNode"},
            nid=hook_id,
        ),
        _n(
            "Normalize",
            "n8n-nodes-base.set",
            390,
            200,
            {"assignments": "echo={{ $json }}\nserver=n8n Flow\nok=true", "includeOtherFields": True},
        ),
        _n("Respond", "n8n-nodes-base.respondToWebhook", 640, 200, {"response": "{{ $json }}"}),
    ]
    hook = {
        "name": "Webhook Echo",
        "active": True,
        "nodes": hook_nodes,
        "connections": {},
        "tags": ["example", "webhook"],
        "settings": {},
    }
    connect_nodes(hook, "Webhook", "Normalize")
    connect_nodes(hook, "Normalize", "Respond")

    rss_nodes = [
        _n("Manual Trigger", "n8n-nodes-base.manualTrigger", 140, 160),
        _n("RSS", "n8n-nodes-base.rssFeedRead", 370, 160, {"url": "https://hnrss.org/frontpage"}),
        _n("Keep titled", "n8n-nodes-base.filter", 600, 160, {"left": "{{ $json.title }}", "operator": "exists", "right": ""}),
        _n(
            "Code",
            "n8n-nodes-base.code",
            830,
            160,
            {
                "mode": "all",
                "code": "result = [{'json': {'count': len(items), 'headlines': [i['json'].get('title') for i in items[:8]]}}]",
            },
        ),
    ]
    rss = {
        "name": "RSS Headlines",
        "active": False,
        "nodes": rss_nodes,
        "connections": {},
        "tags": ["example", "rss"],
        "settings": {},
    }
    connect_nodes(rss, "Manual Trigger", "RSS")
    connect_nodes(rss, "RSS", "Keep titled")
    connect_nodes(rss, "Keep titled", "Code")

    return [hello, http_wf, hook, rss]


def seed_if_empty() -> int:
    if db.list_workflows():
        return 0
    return seed_examples()


def seed_examples() -> int:
    n = 0
    existing = {w["name"] for w in db.list_workflows()}
    for wf in examples():
        if wf["name"] in existing:
            continue
        wf["id"] = db.new_id()
        db.save_workflow(wf)
        n += 1
    return n
