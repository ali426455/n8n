"""Node catalogue and executors."""

from __future__ import annotations

import base64
import copy
import hashlib
import hmac
import json
import math
import random
import re
import smtplib
import textwrap
import time
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from typing import Any, Callable
from urllib.parse import urlencode

import requests

from .expressions import as_bool, compare, interpolate, parse_json_maybe

Item = dict[str, Any]
Executor = Callable[[dict, list[Item], dict], dict]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def items_from(data: Any) -> list[Item]:
    if data is None:
        return [{"json": {}}]
    if isinstance(data, list):
        out = []
        for el in data:
            if isinstance(el, dict) and "json" in el:
                out.append({"json": el.get("json") if el.get("json") is not None else {}})
            elif isinstance(el, dict):
                out.append({"json": el})
            else:
                out.append({"json": {"value": el}})
        return out or [{"json": {}}]
    if isinstance(data, dict) and "json" in data:
        return [{"json": data.get("json") or {}}]
    if isinstance(data, dict):
        return [{"json": data}]
    return [{"json": {"value": data}}]


def ok(outputs: list[list[Item]] | list[Item], extra: dict | None = None) -> dict:
    if outputs and outputs and isinstance(outputs[0], dict) and "json" in outputs[0]:
        branches = [outputs]  # type: ignore[list-item]
    else:
        branches = outputs  # type: ignore[assignment]
    return {"ok": True, "outputs": branches, **(extra or {})}


def fail(message: str, items: list[Item] | None = None) -> dict:
    return {"ok": False, "error": message, "outputs": [items or []]}


def resolve_params(params: dict, item: Item, ctx: dict, item_index: int = 0) -> dict:
    local = dict(ctx)
    local["item"] = item
    local["itemIndex"] = item_index
    return interpolate(params, local)


def first_json(items: list[Item]) -> dict:
    if not items:
        return {}
    return items[0].get("json") or {}


def cred_from_ctx(ctx: dict, cred_id: str | None) -> dict:
    if not cred_id:
        return {}
    resolver = ctx.get("get_credential")
    if not resolver:
        return {}
    try:
        cred = resolver(cred_id)
        return (cred or {}).get("data") or {}
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# executors
# ---------------------------------------------------------------------------

def ex_trigger(node, items, ctx):
    return ok(items or [{"json": {"triggered": True, "at": ctx.get("now")}}])


def ex_webhook(node, items, ctx):
    payload = ctx.get("webhook") or first_json(items)
    return ok(items_from(payload if payload else {"headers": {}, "query": {}, "body": {}}))


def ex_schedule(node, items, ctx):
    return ok([{"json": {"scheduled": True, "at": ctx.get("now"), "cron": node.get("parameters", {}).get("cron")}}])


def ex_http(node, items, ctx):
    out: list[Item] = []
    for i, item in enumerate(items or [{"json": {}}]):
        p = resolve_params(node.get("parameters") or {}, item, ctx, i)
        method = str(p.get("method") or "GET").upper()
        url = str(p.get("url") or "").strip()
        if not url:
            return fail("HTTP Request: URL is empty", items)
        headers = parse_json_maybe(p.get("headers") or {}) or {}
        if not isinstance(headers, dict):
            headers = {}
        query = parse_json_maybe(p.get("query") or {}) or {}
        if not isinstance(query, dict):
            query = {}
        timeout = float(p.get("timeout") or 20)
        timeout = max(1.0, min(timeout, 45.0))
        cred = cred_from_ctx(ctx, p.get("credentials") or node.get("credentials", {}).get("id"))
        auth_type = p.get("auth") or cred.get("_type") or "none"
        if cred.get("token") and auth_type in ("none", "bearer", "generic"):
            headers.setdefault("Authorization", f"Bearer {cred['token']}")
        if cred.get("headerName") and cred.get("headerValue"):
            headers[cred["headerName"]] = cred["headerValue"]
        auth = None
        if cred.get("username") is not None and cred.get("password") is not None:
            auth = (cred.get("username") or "", cred.get("password") or "")
        if cred.get("baseUrl") and url.startswith("/"):
            url = cred["baseUrl"].rstrip("/") + url
        body = None
        json_body = None
        body_type = p.get("bodyType") or "none"
        raw_body = p.get("body")
        if body_type == "json":
            json_body = parse_json_maybe(raw_body) if raw_body not in (None, "") else {}
            if not isinstance(json_body, (dict, list)):
                json_body = {"value": json_body}
        elif body_type == "raw" and raw_body not in (None, ""):
            body = str(raw_body)
        elif body_type == "form":
            form = parse_json_maybe(raw_body) if raw_body else {}
            body = urlencode(form if isinstance(form, dict) else {})
            headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
        try:
            resp = requests.request(
                method,
                url,
                headers={str(k): str(v) for k, v in headers.items()},
                params=query if isinstance(query, dict) else None,
                json=json_body,
                data=body,
                timeout=timeout,
                auth=auth,
            )
        except requests.RequestException as exc:
            if as_bool((node.get("parameters") or {}).get("continueOnFail")):
                out.append({"json": {"error": str(exc), "url": url}})
                continue
            return fail(f"HTTP Request failed: {exc}", items)
        parsed: Any
        ctype = resp.headers.get("content-type", "")
        try:
            parsed = resp.json()
        except Exception:
            parsed = resp.text
        if as_bool(p.get("fullResponse")):
            payload = {
                "statusCode": resp.status_code,
                "headers": dict(resp.headers),
                "body": parsed,
                "url": resp.url,
            }
        else:
            payload = parsed if isinstance(parsed, dict) else {"data": parsed, "statusCode": resp.status_code}
            if not isinstance(parsed, dict):
                payload = {"data": parsed, "statusCode": resp.status_code}
            elif as_bool(p.get("fullResponse")):
                pass
        if isinstance(payload, list):
            for el in payload:
                out.extend(items_from(el))
        else:
            out.append({"json": payload if isinstance(payload, dict) else {"data": payload}})
    return ok(out)


def ex_set(node, items, ctx):
    out: list[Item] = []
    params = node.get("parameters") or {}
    keep = as_bool(params.get("includeOtherFields", True))
    raw_assign = params.get("assignments") or ""
    pairs: list[tuple[str, Any]] = []
    if isinstance(raw_assign, list):
        for row in raw_assign:
            if isinstance(row, dict) and row.get("name"):
                pairs.append((str(row["name"]), row.get("value")))
    else:
        for line in str(raw_assign).splitlines():
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            if k:
                pairs.append((k, v.strip()))
    for i, item in enumerate(items or [{"json": {}}]):
        base = copy.deepcopy(item.get("json") or {}) if keep else {}
        local = dict(ctx)
        local["item"] = item
        local["itemIndex"] = i
        for name, val in pairs:
            base[name] = interpolate(val, local)
        out.append({"json": base})
    return ok(out)


def ex_if(node, items, ctx):
    params = node.get("parameters") or {}
    truthy: list[Item] = []
    falsy: list[Item] = []
    for i, item in enumerate(items or [{"json": {}}]):
        p = resolve_params(params, item, ctx, i)
        left = interpolate(params.get("left", "{{ $json }}"), {**ctx, "item": item, "itemIndex": i})
        # if left still looks like the whole json object when user used $json.field
        if isinstance(p.get("left"), str):
            left = interpolate(params.get("left"), {**ctx, "item": item, "itemIndex": i})
        right = interpolate(params.get("right", ""), {**ctx, "item": item, "itemIndex": i})
        op = p.get("operator") or params.get("operator") or "equals"
        (truthy if compare(left, op, right) else falsy).append(item)
    return ok([truthy, falsy])


def ex_switch(node, items, ctx):
    params = node.get("parameters") or {}
    rules_raw = params.get("rules") or ""
    rules = []
    if isinstance(rules_raw, list):
        rules = rules_raw
    else:
        for line in str(rules_raw).splitlines():
            line = line.strip()
            if line:
                rules.append(line)
    buckets: list[list[Item]] = [[] for _ in range(len(rules) + 1)]
    for i, item in enumerate(items or [{"json": {}}]):
        val = interpolate(params.get("value", "{{ $json.value }}"), {**ctx, "item": item, "itemIndex": i})
        placed = False
        for idx, rule in enumerate(rules):
            if str(val) == str(interpolate(rule, {**ctx, "item": item, "itemIndex": i})):
                buckets[idx].append(item)
                placed = True
                break
        if not placed:
            buckets[-1].append(item)
    return ok(buckets if buckets else [items])


def ex_filter(node, items, ctx):
    params = node.get("parameters") or {}
    kept: list[Item] = []
    for i, item in enumerate(items or []):
        left = interpolate(params.get("left", "{{ $json }}"), {**ctx, "item": item, "itemIndex": i})
        right = interpolate(params.get("right", ""), {**ctx, "item": item, "itemIndex": i})
        if compare(left, params.get("operator") or "exists", right):
            kept.append(item)
    return ok(kept)


def ex_code(node, items, ctx):
    params = node.get("parameters") or {}
    src = str(params.get("code") or "result = items")
    banned = [
        "__import__",
        "import ",
        "open(",
        "exec(",
        "eval(",
        "compile(",
        "os.",
        "sys.",
        "subprocess",
        "socket",
        "pathlib",
        "shutil",
        "requests",
        "Popen",
        "from_thread",
        "globals(",
        "locals(",
        "getattr(",
        "setattr(",
        "delattr(",
        "memoryview",
        "breakpoint",
    ]
    lower = src
    for token in banned:
        if token in lower:
            return fail(f"Code node blocked token: {token}", items)
    if len(src) > 8000:
        return fail("Code node too large", items)
    safe_builtins = {
        "abs": abs,
        "all": all,
        "any": any,
        "bool": bool,
        "dict": dict,
        "enumerate": enumerate,
        "filter": filter,
        "float": float,
        "int": int,
        "len": len,
        "list": list,
        "map": map,
        "max": max,
        "min": min,
        "print": print,
        "range": range,
        "repr": repr,
        "reversed": reversed,
        "round": round,
        "sorted": sorted,
        "str": str,
        "sum": sum,
        "tuple": tuple,
        "zip": zip,
    }
    mode = params.get("mode") or "all"
    payload_items = copy.deepcopy(items or [{"json": {}}])

    def run_once(current_items: list[Item]) -> Any:
        env = {
            "items": current_items,
            "item": current_items[0] if current_items else {"json": {}},
            "json": first_json(current_items),
            "result": None,
            "datetime": datetime,
            "timedelta": timedelta,
            "timezone": timezone,
            "math": math,
            "re": re,
            "json": json,
            "random": random,
            "hashlib": hashlib,
            "base64": base64,
        }
        wrapped = (
            "def __user_fn__(items, item, json):\n"
            + textwrap.indent(src, "    ")
            + "\n"
        )
        local = {"__builtins__": safe_builtins}
        try:
            if re.search(r"^\s*return\b", src, re.M):
                exec(wrapped, local, local)
                return local["__user_fn__"](current_items, env["item"], env["json"])
            exec(src, {"__builtins__": safe_builtins}, env)
            return env.get("result", env.get("items"))
        except Exception as exc:
            raise RuntimeError(str(exc)) from exc

    try:
        if mode == "each":
            collected: list[Item] = []
            for it in payload_items:
                ret = run_once([it])
                collected.extend(items_from(ret))
            return ok(collected)
        ret = run_once(payload_items)
        return ok(items_from(ret))
    except Exception as exc:
        return fail(f"Code error: {exc}", items)


def ex_noop(node, items, ctx):
    return ok(items or [{"json": {}}])


def ex_sticky(node, items, ctx):
    return ok(items or [{"json": {}}])


def ex_wait(node, items, ctx):
    seconds = float((node.get("parameters") or {}).get("seconds") or 1)
    time.sleep(max(0.0, min(seconds, 8.0)))
    return ok(items or [{"json": {"waited": seconds}}])


def ex_merge(node, items, ctx):
    # Engine may call this once per incoming branch; just pass through.
    return ok(items or [])


def ex_split(node, items, ctx):
    size = int((node.get("parameters") or {}).get("batchSize") or 1)
    size = max(1, size)
    # Return first batch only (Streamlit can't loop like n8n easily)
    return ok((items or [])[:size] or [{"json": {}}])


def ex_json(node, items, ctx):
    params = node.get("parameters") or {}
    mode = params.get("mode") or "parse"
    field = params.get("field") or "data"
    out = []
    for i, item in enumerate(items or [{"json": {}}]):
        data = copy.deepcopy(item.get("json") or {})
        val = interpolate(params.get("value", "{{ $json." + field + " }}"), {**ctx, "item": item, "itemIndex": i})
        if mode == "parse":
            data[field] = parse_json_maybe(val)
        else:
            data[field] = json.dumps(val, ensure_ascii=False) if not isinstance(val, str) else val
        out.append({"json": data})
    return ok(out)


def ex_datetime(node, items, ctx):
    params = node.get("parameters") or {}
    fmt = params.get("format") or "%Y-%m-%dT%H:%M:%SZ"
    amount = int(params.get("amount") or 0)
    unit = params.get("unit") or "minutes"
    now = datetime.now(timezone.utc)
    delta_map = {
        "seconds": timedelta(seconds=amount),
        "minutes": timedelta(minutes=amount),
        "hours": timedelta(hours=amount),
        "days": timedelta(days=amount),
    }
    now = now + delta_map.get(unit, timedelta())
    out = []
    for item in items or [{"json": {}}]:
        data = copy.deepcopy(item.get("json") or {})
        data[params.get("field") or "datetime"] = now.strftime(fmt)
        out.append({"json": data})
    return ok(out)


def ex_crypto(node, items, ctx):
    params = node.get("parameters") or {}
    algo = (params.get("algorithm") or "sha256").lower()
    out = []
    for i, item in enumerate(items or [{"json": {}}]):
        val = str(interpolate(params.get("value", "{{ $json }}"), {**ctx, "item": item, "itemIndex": i}))
        if isinstance(item.get("json"), dict) and params.get("value") in (None, "", "{{ $json }}"):
            val = json.dumps(item.get("json"), ensure_ascii=False, sort_keys=True)
        raw = val.encode("utf-8")
        if algo == "md5":
            digest = hashlib.md5(raw).hexdigest()
        elif algo == "sha1":
            digest = hashlib.sha1(raw).hexdigest()
        elif algo == "sha256":
            digest = hashlib.sha256(raw).hexdigest()
        elif algo == "base64":
            digest = base64.b64encode(raw).decode("ascii")
        elif algo == "hmac-sha256":
            secret = str(params.get("secret") or "")
            digest = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
        else:
            digest = hashlib.sha256(raw).hexdigest()
        data = copy.deepcopy(item.get("json") or {})
        data[params.get("field") or "hash"] = digest
        out.append({"json": data})
    return ok(out)


def ex_rss(node, items, ctx):
    try:
        import feedparser
    except ImportError:
        return fail("feedparser is not installed", items)
    url = None
    params = node.get("parameters") or {}
    if items:
        url = interpolate(params.get("url", ""), {**ctx, "item": items[0], "itemIndex": 0})
    url = url or params.get("url")
    if not url:
        return fail("RSS: url is empty", items)
    parsed = feedparser.parse(str(url))
    entries = []
    for e in parsed.entries[:50]:
        entries.append(
            {
                "json": {
                    "title": e.get("title"),
                    "link": e.get("link"),
                    "summary": e.get("summary"),
                    "published": e.get("published"),
                    "feed": parsed.feed.get("title") if parsed.feed else None,
                }
            }
        )
    return ok(entries or [{"json": {"title": None, "empty": True}}])


def ex_telegram(node, items, ctx):
    params = node.get("parameters") or {}
    cred = cred_from_ctx(ctx, params.get("credentials") or (node.get("credentials") or {}).get("id"))
    token = cred.get("token") or cred.get("botToken") or params.get("token")
    if not token:
        return fail("Telegram: missing bot token (add a credential)", items)
    out = []
    for i, item in enumerate(items or [{"json": {}}]):
        p = resolve_params(params, item, ctx, i)
        chat = p.get("chatId") or cred.get("chatId")
        text = p.get("text") or json.dumps(item.get("json"), ensure_ascii=False)
        if not chat:
            return fail("Telegram: chatId is empty", items)
        try:
            resp = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat, "text": str(text), "parse_mode": p.get("parseMode") or None},
                timeout=20,
            )
            body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {"text": resp.text}
        except requests.RequestException as exc:
            return fail(f"Telegram failed: {exc}", items)
        out.append({"json": {"ok": body.get("ok", resp.ok), "result": body}})
    return ok(out)


def ex_discord(node, items, ctx):
    params = node.get("parameters") or {}
    cred = cred_from_ctx(ctx, params.get("credentials") or (node.get("credentials") or {}).get("id"))
    url = cred.get("url") or params.get("url")
    if not url:
        return fail("Discord: missing webhook url", items)
    out = []
    for i, item in enumerate(items or [{"json": {}}]):
        p = resolve_params(params, item, ctx, i)
        content = p.get("text") or json.dumps(item.get("json"), ensure_ascii=False)
        try:
            resp = requests.post(url, json={"content": str(content)[:1900]}, timeout=20)
        except requests.RequestException as exc:
            return fail(f"Discord failed: {exc}", items)
        out.append({"json": {"statusCode": resp.status_code}})
    return ok(out)


def ex_email(node, items, ctx):
    params = node.get("parameters") or {}
    cred = cred_from_ctx(ctx, params.get("credentials") or (node.get("credentials") or {}).get("id"))
    host = cred.get("host") or params.get("host")
    port = int(cred.get("port") or params.get("port") or 587)
    user = cred.get("username") or params.get("username")
    password = cred.get("password") or params.get("password")
    use_tls = as_bool(cred.get("tls") if cred.get("tls") is not None else params.get("tls", True))
    if not host:
        return fail("Email: missing SMTP host", items)
    out = []
    for i, item in enumerate(items or [{"json": {}}]):
        p = resolve_params(params, item, ctx, i)
        to = p.get("to")
        subject = p.get("subject") or "n8n Flow"
        body = p.get("text") or json.dumps(item.get("json"), ensure_ascii=False)
        if not to:
            return fail("Email: missing recipient", items)
        msg = MIMEText(str(body), "plain", "utf-8")
        msg["Subject"] = str(subject)
        msg["From"] = user or "n8nflow@localhost"
        msg["To"] = str(to)
        try:
            with smtplib.SMTP(host, port, timeout=20) as smtp:
                if use_tls:
                    smtp.starttls()
                if user:
                    smtp.login(str(user), str(password or ""))
                smtp.sendmail(msg["From"], [str(to)], msg.as_string())
        except Exception as exc:
            return fail(f"Email failed: {exc}", items)
        out.append({"json": {"sent": True, "to": to, "subject": subject}})
    return ok(out)


def ex_openai(node, items, ctx):
    params = node.get("parameters") or {}
    cred = cred_from_ctx(ctx, params.get("credentials") or (node.get("credentials") or {}).get("id"))
    api_key = cred.get("apiKey") or cred.get("token") or params.get("apiKey")
    if not api_key:
        return fail("OpenAI: missing API key", items)
    base = (cred.get("baseUrl") or "https://api.openai.com/v1").rstrip("/")
    out = []
    for i, item in enumerate(items or [{"json": {}}]):
        p = resolve_params(params, item, ctx, i)
        prompt = p.get("prompt") or json.dumps(item.get("json"), ensure_ascii=False)
        model = p.get("model") or "gpt-4o-mini"
        try:
            resp = requests.post(
                f"{base}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": str(prompt)}],
                    "temperature": float(p.get("temperature") or 0.3),
                },
                timeout=45,
            )
            body = resp.json()
        except Exception as exc:
            return fail(f"OpenAI failed: {exc}", items)
        text = ""
        try:
            text = body["choices"][0]["message"]["content"]
        except Exception:
            text = json.dumps(body, ensure_ascii=False)
        data = copy.deepcopy(item.get("json") or {})
        data["ai"] = text
        data["model"] = model
        out.append({"json": data})
    return ok(out)


def ex_respond(node, items, ctx):
    params = node.get("parameters") or {}
    body = params.get("response")
    if items:
        body = interpolate(body if body not in (None, "") else "{{ $json }}", {**ctx, "item": items[0], "itemIndex": 0})
    ctx["webhook_response"] = body if body is not None else first_json(items)
    return ok(items or [{"json": {"responded": True}}])


# ---------------------------------------------------------------------------
# catalogue
# ---------------------------------------------------------------------------

Field = dict[str, Any]


def F(name: str, ftype: str, **kw) -> Field:
    d = {"name": name, "type": ftype}
    d.update(kw)
    return d


SPECS: dict[str, dict[str, Any]] = {}


def spec(
    type_id: str,
    *,
    label: str,
    label_fa: str,
    icon: str,
    color: str,
    group: str,
    execute: Executor,
    fields: list[Field] | None = None,
    outputs: int = 1,
    is_trigger: bool = False,
    description: str = "",
    description_fa: str = "",
    output_labels: list[str] | None = None,
) -> None:
    SPECS[type_id] = {
        "type": type_id,
        "label": label,
        "label_fa": label_fa,
        "icon": icon,
        "color": color,
        "group": group,
        "execute": execute,
        "fields": fields or [],
        "outputs": outputs,
        "is_trigger": is_trigger,
        "description": description,
        "description_fa": description_fa,
        "output_labels": output_labels or ["main"],
    }


spec(
    "n8n-nodes-base.manualTrigger",
    label="Manual Trigger",
    label_fa="تریگر دستی",
    icon="▶️",
    color="#29A366",
    group="trigger",
    execute=ex_trigger,
    is_trigger=True,
    description="Start the workflow from the editor.",
    description_fa="اجرای دستی از ویرایشگر.",
)
spec(
    "n8n-nodes-base.webhook",
    label="Webhook",
    label_fa="وب‌هوک",
    icon="🪝",
    color="#29A366",
    group="trigger",
    execute=ex_webhook,
    is_trigger=True,
    fields=[
        F("path", "string", default="", placeholder="auto"),
        F("method", "select", options=["GET", "POST", "ANY"], default="ANY"),
        F("responseMode", "select", options=["lastNode", "responseNode"], default="lastNode"),
    ],
    description="Run when the public Streamlit URL is opened with the token.",
    description_fa="با باز شدن آدرس عمومی اپ به‌همراه توکن اجرا می‌شود.",
)
spec(
    "n8n-nodes-base.scheduleTrigger",
    label="Schedule",
    label_fa="زمان‌بندی",
    icon="⏰",
    color="#29A366",
    group="trigger",
    execute=ex_schedule,
    is_trigger=True,
    fields=[
        F("cron", "string", default="*/15 * * * *", placeholder="*/15 * * * *"),
    ],
    description="Runs when the app is awake and the cron expression is due.",
    description_fa="وقتی اپ بیدار است و cron سررسید شده اجرا می‌شود.",
)
spec(
    "n8n-nodes-base.httpRequest",
    label="HTTP Request",
    label_fa="درخواست HTTP",
    icon="🌐",
    color="#FF6D5A",
    group="input",
    execute=ex_http,
    fields=[
        F("method", "select", options=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"], default="GET"),
        F("url", "string", default="https://jsonplaceholder.typicode.com/todos/1"),
        F("auth", "select", options=["none", "bearer", "basic", "header"], default="none"),
        F("credentials", "credentials", cred_types=["httpHeaderAuth", "httpBasicAuth", "generic"]),
        F("headers", "json", default="{}"),
        F("query", "json", default="{}"),
        F("bodyType", "select", options=["none", "json", "raw", "form"], default="none"),
        F("body", "text", default=""),
        F("timeout", "number", default=20),
        F("fullResponse", "bool", default=False),
        F("continueOnFail", "bool", default=False),
    ],
    description="Call any HTTP API.",
    description_fa="صدای هر API اچ‌تی‌تی‌پی.",
)
spec(
    "n8n-nodes-base.set",
    label="Set / Edit Fields",
    label_fa="تنظیم فیلد",
    icon="📝",
    color="#30167D",
    group="transform",
    execute=ex_set,
    fields=[
        F("assignments", "text", default="message=سلام دنیا\nsource=n8n Flow"),
        F("includeOtherFields", "bool", default=True),
    ],
)
spec(
    "n8n-nodes-base.if",
    label="IF",
    label_fa="شرط IF",
    icon="⑂",
    color="#506000",
    group="logic",
    execute=ex_if,
    outputs=2,
    output_labels=["true", "false"],
    fields=[
        F("left", "string", default="{{ $json.statusCode }}"),
        F(
            "operator",
            "select",
            options=[
                "equals",
                "notEquals",
                "contains",
                "notContains",
                "gt",
                "lt",
                "gte",
                "lte",
                "exists",
                "isEmpty",
                "regex",
                "startsWith",
                "endsWith",
            ],
            default="equals",
        ),
        F("right", "string", default="200"),
    ],
)
spec(
    "n8n-nodes-base.switch",
    label="Switch",
    label_fa="سوییچ",
    icon="🔀",
    color="#506000",
    group="logic",
    execute=ex_switch,
    outputs=4,
    output_labels=["0", "1", "2", "fallback"],
    fields=[
        F("value", "string", default="{{ $json.type }}"),
        F("rules", "text", default="email\ntelegram\nhttp"),
    ],
)
spec(
    "n8n-nodes-base.filter",
    label="Filter",
    label_fa="فیلتر",
    icon="🔍",
    color="#30167D",
    group="transform",
    execute=ex_filter,
    fields=[
        F("left", "string", default="{{ $json.title }}"),
        F("operator", "select", options=["exists", "isEmpty", "contains", "equals", "gt", "lt"], default="exists"),
        F("right", "string", default=""),
    ],
)
spec(
    "n8n-nodes-base.code",
    label="Code (Python)",
    label_fa="کد پایتون",
    icon="💻",
    color="#FF6D5A",
    group="transform",
    execute=ex_code,
    fields=[
        F("mode", "select", options=["all", "each"], default="all"),
        F(
            "code",
            "code",
            default="result = [{'json': {**item['json'], 'processed': True}} for item in items]",
        ),
    ],
)
spec(
    "n8n-nodes-base.json",
    label="JSON",
    label_fa="JSON",
    icon="🧩",
    color="#30167D",
    group="transform",
    execute=ex_json,
    fields=[
        F("mode", "select", options=["parse", "stringify"], default="parse"),
        F("field", "string", default="data"),
        F("value", "string", default="{{ $json.data }}"),
    ],
)
spec(
    "n8n-nodes-base.dateTime",
    label="Date & Time",
    label_fa="تاریخ و زمان",
    icon="📅",
    color="#30167D",
    group="transform",
    execute=ex_datetime,
    fields=[
        F("field", "string", default="datetime"),
        F("format", "string", default="%Y-%m-%d %H:%M"),
        F("amount", "number", default=0),
        F("unit", "select", options=["seconds", "minutes", "hours", "days"], default="minutes"),
    ],
)
spec(
    "n8n-nodes-base.crypto",
    label="Crypto",
    label_fa="هش / رمز",
    icon="🔒",
    color="#30167D",
    group="transform",
    execute=ex_crypto,
    fields=[
        F("algorithm", "select", options=["sha256", "sha1", "md5", "base64", "hmac-sha256"], default="sha256"),
        F("value", "string", default="{{ $json }}"),
        F("secret", "string", default=""),
        F("field", "string", default="hash"),
    ],
)
spec(
    "n8n-nodes-base.merge",
    label="Merge",
    label_fa="ادغام",
    icon="➕",
    color="#909298",
    group="logic",
    execute=ex_merge,
)
spec(
    "n8n-nodes-base.splitInBatches",
    label="Split In Batches",
    label_fa="تقسیم دسته‌ای",
    icon="📦",
    color="#909298",
    group="logic",
    execute=ex_split,
    fields=[F("batchSize", "number", default=1)],
)
spec(
    "n8n-nodes-base.noOp",
    label="No Operation",
    label_fa="بدون عمل",
    icon="⭕",
    color="#909298",
    group="logic",
    execute=ex_noop,
)
spec(
    "n8n-nodes-base.stickyNote",
    label="Sticky Note",
    label_fa="یادداشت",
    icon="📌",
    color="#FFC043",
    group="logic",
    execute=ex_sticky,
    fields=[F("note", "text", default="یادداشت روی بوم")],
)
spec(
    "n8n-nodes-base.wait",
    label="Wait",
    label_fa="انتظار",
    icon="⏳",
    color="#909298",
    group="logic",
    execute=ex_wait,
    fields=[F("seconds", "number", default=1)],
)
spec(
    "n8n-nodes-base.rssFeedRead",
    label="RSS Feed Read",
    label_fa="خواندن RSS",
    icon="📰",
    color="#FF6D5A",
    group="input",
    execute=ex_rss,
    fields=[F("url", "string", default="https://hnrss.org/frontpage")],
)
spec(
    "n8n-nodes-base.telegram",
    label="Telegram",
    label_fa="تلگرام",
    icon="✈️",
    color="#1F61DB",
    group="output",
    execute=ex_telegram,
    fields=[
        F("credentials", "credentials", cred_types=["telegramApi"]),
        F("chatId", "string", default=""),
        F("text", "text", default="{{ $json.message }}"),
        F("parseMode", "select", options=["", "HTML", "Markdown"], default=""),
    ],
)
spec(
    "n8n-nodes-base.discord",
    label="Discord",
    label_fa="دیسکورد",
    icon="💬",
    color="#1F61DB",
    group="output",
    execute=ex_discord,
    fields=[
        F("credentials", "credentials", cred_types=["discordWebhook"]),
        F("url", "string", default=""),
        F("text", "text", default="{{ $json.message }}"),
    ],
)
spec(
    "n8n-nodes-base.emailSend",
    label="Send Email",
    label_fa="ایمیل",
    icon="✉️",
    color="#1F61DB",
    group="output",
    execute=ex_email,
    fields=[
        F("credentials", "credentials", cred_types=["smtp"]),
        F("to", "string", default=""),
        F("subject", "string", default="n8n Flow"),
        F("text", "text", default="{{ $json }}"),
    ],
)
spec(
    "n8n-nodes-base.openAi",
    label="OpenAI",
    label_fa="OpenAI",
    icon="✨",
    color="#7C3AED",
    group="ai",
    execute=ex_openai,
    fields=[
        F("credentials", "credentials", cred_types=["openAiApi"]),
        F("model", "string", default="gpt-4o-mini"),
        F("prompt", "text", default="Summarize this JSON:\n{{ $json }}"),
        F("temperature", "number", default=0.3),
    ],
)
spec(
    "n8n-nodes-base.respondToWebhook",
    label="Respond to Webhook",
    label_fa="پاسخ وب‌هوک",
    icon="↩️",
    color="#29A366",
    group="output",
    execute=ex_respond,
    fields=[F("response", "text", default="{{ $json }}")],
)

GROUPS = [
    ("trigger", "group_trigger"),
    ("input", "group_input"),
    ("transform", "group_transform"),
    ("logic", "group_logic"),
    ("output", "group_output"),
    ("ai", "group_ai"),
]

# n8n aliases
SPECS["n8n-nodes-base.cron"] = SPECS["n8n-nodes-base.scheduleTrigger"]
SPECS["n8n-nodes-base.function"] = SPECS["n8n-nodes-base.code"]
SPECS["n8n-nodes-base.functionItem"] = SPECS["n8n-nodes-base.code"]
SPECS["n8n-nodes-base.respondToWebhook"] = SPECS["n8n-nodes-base.respondToWebhook"]


def get_spec(type_id: str) -> dict[str, Any]:
    return SPECS.get(type_id) or SPECS["n8n-nodes-base.noOp"]


def is_trigger(type_id: str) -> bool:
    return bool(get_spec(type_id).get("is_trigger"))


def label_for(type_id: str, lang: str = "fa") -> str:
    s = get_spec(type_id)
    return s["label_fa"] if lang == "fa" else s["label"]


CREDENTIAL_TYPES = [
    ("telegramApi", "Telegram Bot", "تلگرام"),
    ("openAiApi", "OpenAI / compatible", "OpenAI"),
    ("smtp", "SMTP Email", "ایمیل SMTP"),
    ("discordWebhook", "Discord Webhook", "دیسکورد"),
    ("httpHeaderAuth", "Header Auth", "هدر HTTP"),
    ("httpBasicAuth", "Basic Auth", "Basic Auth"),
    ("generic", "Generic Secret", "کلید عمومی"),
]
