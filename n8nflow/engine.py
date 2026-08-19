"""Workflow execution engine (n8n-style items + connections)."""

from __future__ import annotations

import traceback
from datetime import datetime, timezone
from typing import Any

from croniter import croniter

from . import db
from .nodes import get_spec, is_trigger, items_from


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def find_triggers(wf: dict) -> list[dict]:
    return [n for n in wf.get("nodes") or [] if is_trigger(n.get("type", ""))]


def pick_trigger(wf: dict, mode: str) -> dict | None:
    trigs = find_triggers(wf)
    if not trigs:
        return None
    prefer = {
        "webhook": "n8n-nodes-base.webhook",
        "schedule": "n8n-nodes-base.scheduleTrigger",
        "manual": "n8n-nodes-base.manualTrigger",
    }.get(mode)
    if prefer:
        for n in trigs:
            if n.get("type") == prefer or (mode == "schedule" and n.get("type") == "n8n-nodes-base.cron"):
                return n
    return trigs[0]


def webhook_token(wf: dict) -> str | None:
    for n in wf.get("nodes") or []:
        if n.get("type") == "n8n-nodes-base.webhook":
            path = (n.get("parameters") or {}).get("path")
            return str(path) if path else n.get("id")
    return None


def schedule_cron(wf: dict) -> str | None:
    for n in wf.get("nodes") or []:
        if n.get("type") in ("n8n-nodes-base.scheduleTrigger", "n8n-nodes-base.cron"):
            return (n.get("parameters") or {}).get("cron") or "0 * * * *"
    return None


def incoming_map(wf: dict) -> dict[str, list[tuple[str, int]]]:
    inc: dict[str, list[tuple[str, int]]] = {}
    for src, bundle in (wf.get("connections") or {}).items():
        mains = bundle.get("main") or []
        for idx, targets in enumerate(mains):
            for t in targets or []:
                inc.setdefault(t.get("node"), []).append((src, idx))
    return inc


def outgoing(wf: dict, name: str) -> list[list[dict]]:
    return ((wf.get("connections") or {}).get(name) or {}).get("main") or []


def execute_node(node: dict, items: list, ctx: dict) -> dict:
    if node.get("disabled"):
        return {"ok": True, "outputs": [items], "skipped": True}
    spec = get_spec(node.get("type") or "")
    fn = spec.get("execute")
    if not fn:
        return {"ok": False, "error": f"Unknown node type {node.get('type')}", "outputs": [items]}
    try:
        result = fn(node, items, ctx)
        if not isinstance(result, dict) or "outputs" not in result:
            return {"ok": False, "error": "Node returned invalid result", "outputs": [items]}
        return result
    except Exception as exc:
        return {"ok": False, "error": f"{exc}", "outputs": [items], "trace": traceback.format_exc()}


def execute_workflow(
    wf: dict,
    *,
    mode: str = "manual",
    trigger_data: Any = None,
    persist: bool = True,
) -> dict[str, Any]:
    started = datetime.now(timezone.utc)
    exec_id = db.new_id()
    trigger_items = items_from(trigger_data if trigger_data is not None else {"triggeredAt": started.isoformat(), "mode": mode})

    if persist:
        db.insert_execution(
            {
                "id": exec_id,
                "workflow_id": wf.get("id"),
                "workflow_name": wf.get("name"),
                "status": "running",
                "mode": mode,
                "started_at": started.isoformat(),
                "trigger_data": trigger_data if trigger_data is not None else {"mode": mode},
            }
        )

    nodes_by_name = {n["name"]: n for n in wf.get("nodes") or [] if n.get("name")}
    trigger = pick_trigger(wf, mode)
    if not trigger:
        result = {
            "id": exec_id,
            "status": "error",
            "error": "No trigger node in workflow",
            "started_at": started.isoformat(),
            "finished_at": now_iso(),
            "node_results": {},
            "items": [],
            "webhook_response": None,
        }
        if persist:
            db.finish_execution(exec_id, status="error", data=result, error=result["error"])
        return result

    def get_credential(cid: str):
        return db.get_credential(cid)

    ctx: dict[str, Any] = {
        "now": started.isoformat(),
        "now_dt": started,
        "workflow": {"id": wf.get("id"), "name": wf.get("name")},
        "execution": {"id": exec_id, "mode": mode},
        "webhook": trigger_data if mode == "webhook" else {},
        "env": {},
        "nodes_out": {},
        "get_credential": get_credential,
        "webhook_response": None,
        "runIndex": 0,
    }

    node_results: dict[str, Any] = {}
    merge_buffer: dict[str, list] = {}
    inc = incoming_map(wf)

    # queue of (node_name, items, from_output_index)
    queue: list[tuple[str, list, int]] = [(trigger["name"], trigger_items, 0)]
    visited_runs = 0
    last_items: list = trigger_items
    error_message = None
    status = "success"

    while queue:
        visited_runs += 1
        if visited_runs > 200:
            error_message = "Execution stopped: too many steps (cycle?)"
            status = "error"
            break
        name, incoming_items, _from = queue.pop(0)
        node = nodes_by_name.get(name)
        if not node:
            continue
        # Merge: wait until all incoming parents produced something (best-effort)
        if node.get("type") == "n8n-nodes-base.merge":
            merge_buffer.setdefault(name, [])
            merge_buffer[name].extend(incoming_items)
            parents = inc.get(name) or []
            # If other parents haven't run yet, stash and continue
            ran_parents = [p for p, _ in parents if p in node_results]
            if parents and len(ran_parents) < len(set(p for p, _ in parents)):
                # still keep buffer; don't execute yet unless this is last remaining
                if name not in {q[0] for q in queue}:
                    # delay
                    queue.append((name, [], 0))
                # Avoid infinite delay: if nothing else on queue except this, run with what we have
                if any(q[0] != name for q in queue):
                    continue
            incoming_items = merge_buffer.pop(name, incoming_items)

        result = execute_node(node, incoming_items, ctx)
        outputs = result.get("outputs") or [[]]
        # normalize to list of branches
        if outputs and outputs[0] and isinstance(outputs[0], dict) and "json" in outputs[0]:
            outputs = [outputs]
        node_results[name] = {
            "ok": result.get("ok", False),
            "error": result.get("error"),
            "items": outputs[0] if outputs else [],
            "outputs": [
                [{"json": it.get("json")} for it in (branch or []) if isinstance(it, dict)]
                for branch in outputs
            ],
            "type": node.get("type"),
        }
        ctx["nodes_out"][name] = node_results[name]
        if outputs and outputs[0]:
            last_items = outputs[0]

        if not result.get("ok"):
            error_message = f"{name}: {result.get('error')}"
            status = "error"
            cont = bool((node.get("parameters") or {}).get("continueOnFail"))
            if not cont:
                break

        targets = outgoing(wf, name)
        for out_idx, dests in enumerate(targets):
            branch_items = outputs[out_idx] if out_idx < len(outputs) else []
            if not dests or not branch_items:
                continue
            for dest in dests:
                dest_name = dest.get("node")
                if dest_name:
                    queue.append((dest_name, branch_items, out_idx))

    finished = datetime.now(timezone.utc)
    duration_ms = int((finished - started).total_seconds() * 1000)
    webhook_response = ctx.get("webhook_response")
    if webhook_response is None and last_items:
        webhook_response = [it.get("json") for it in last_items]

    result = {
        "id": exec_id,
        "status": status,
        "error": error_message,
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "duration_ms": duration_ms,
        "node_results": node_results,
        "items": [it.get("json") for it in last_items] if last_items else [],
        "webhook_response": webhook_response,
        "mode": mode,
        "workflow_id": wf.get("id"),
        "workflow_name": wf.get("name"),
    }
    if persist:
        db.finish_execution(
            exec_id,
            status=status,
            data=result,
            error=error_message,
            finished_at=finished.isoformat(),
        )
        if wf.get("id"):
            db.touch_workflow_run(wf["id"])
    return result


def run_due_schedules(now: datetime | None = None) -> list[dict]:
    from datetime import timedelta

    now = now or datetime.now(timezone.utc)
    ran = []
    for wf in db.list_workflows():
        if not wf.get("active"):
            continue
        cron = schedule_cron(wf)
        if not cron:
            continue
        try:
            last = None
            if wf.get("last_run_at"):
                try:
                    last = datetime.fromisoformat(str(wf["last_run_at"]).replace("Z", "+00:00"))
                except Exception:
                    last = None
            if last is None:
                last = now - timedelta(hours=1)
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            itr = croniter(cron, last)
            nxt = itr.get_next(datetime)
            if nxt.tzinfo is None:
                nxt = nxt.replace(tzinfo=timezone.utc)
            if nxt <= now:
                ran.append(
                    execute_workflow(wf, mode="schedule", trigger_data={"cron": cron, "at": now.isoformat()})
                )
        except Exception:
            continue
    return ran


def import_n8n_workflow(payload: dict) -> dict:
    """Accept official-ish n8n JSON; map unknown types to NoOp."""
    from .nodes import SPECS

    nodes = []
    unknown = []
    for n in payload.get("nodes") or []:
        n = dict(n)
        n.setdefault("id", db.new_id())
        n.setdefault("name", n.get("type", "Node"))
        n.setdefault("parameters", {})
        n.setdefault("position", [200, 200])
        if n.get("type") not in SPECS:
            unknown.append(n.get("type"))
            n["type"] = "n8n-nodes-base.noOp"
            n.setdefault("notes", f"Imported unknown type")
        nodes.append(n)
    wf = {
        "id": db.new_id(),
        "name": payload.get("name") or "Imported",
        "active": False,
        "nodes": nodes,
        "connections": payload.get("connections") or {},
        "settings": payload.get("settings") or {},
        "tags": payload.get("tags") or [],
    }
    saved = db.save_workflow(wf)
    saved["_unknown"] = unknown
    return saved


def unique_node_name(nodes: list[dict], base: str) -> str:
    names = {n.get("name") for n in nodes}
    if base not in names:
        return base
    i = 1
    while f"{base} {i}" in names:
        i += 1
    return f"{base} {i}"


def empty_workflow(name: str = "New workflow") -> dict:
    tid = db.new_id()
    node = {
        "id": tid,
        "name": "Manual Trigger",
        "type": "n8n-nodes-base.manualTrigger",
        "typeVersion": 1,
        "position": [180, 220],
        "parameters": {},
    }
    return {
        "id": db.new_id(),
        "name": name,
        "active": False,
        "nodes": [node],
        "connections": {},
        "settings": {},
        "tags": [],
    }


def connect_nodes(wf: dict, source: str, target: str, output_index: int = 0) -> None:
    conns = wf.setdefault("connections", {})
    bundle = conns.setdefault(source, {})
    main = bundle.setdefault("main", [])
    while len(main) <= output_index:
        main.append([])
    already = any(t.get("node") == target for t in (main[output_index] or []))
    if not already:
        main[output_index].append({"node": target, "type": "main", "index": 0})


def disconnect_node(wf: dict, name: str) -> None:
    wf.get("connections", {}).pop(name, None)
    for src, bundle in list((wf.get("connections") or {}).items()):
        mains = bundle.get("main") or []
        for i, dests in enumerate(mains):
            mains[i] = [d for d in (dests or []) if d.get("node") != name]


def auto_layout(wf: dict) -> None:
    nodes = wf.get("nodes") or []
    if not nodes:
        return
    inc = incoming_map(wf)
    names = [n["name"] for n in nodes]
    roots = [n["name"] for n in nodes if not inc.get(n["name"]) and n.get("type") != "n8n-nodes-base.stickyNote"]
    if not roots:
        roots = names[:1]
    level: dict[str, int] = {r: 0 for r in roots}
    changed = True
    guard = 0
    while changed and guard < 50:
        changed = False
        guard += 1
        for src, bundle in (wf.get("connections") or {}).items():
            sl = level.get(src, 0)
            for dests in bundle.get("main") or []:
                for d in dests or []:
                    nm = d.get("node")
                    if nm is None:
                        continue
                    nl = sl + 1
                    if nm not in level or level[nm] < nl:
                        level[nm] = nl
                        changed = True
    buckets: dict[int, list[str]] = {}
    for n in nodes:
        buckets.setdefault(level.get(n["name"], 0), []).append(n["name"])
    by_name = {n["name"]: n for n in nodes}
    for lv, group in buckets.items():
        for i, nm in enumerate(group):
            by_name[nm]["position"] = [160 + lv * 230, 80 + i * 130]
