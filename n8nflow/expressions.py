"""n8n-style expression resolver: {{ $json.user.name }} and ={{ ... }}."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

EXPR_RE = re.compile(r"\{\{\s*(.+?)\s*\}\}", re.DOTALL)
PATH_TOKEN = re.compile(r"\.([A-Za-z_][\w]*)|\[(\d+)\]|\[['\"]([^'\"]+)['\"]\]")


def get_path(obj: Any, path: str) -> Any:
    """Resolve a.b[0]['c'] against obj."""
    path = path.strip()
    if not path:
        return obj
    # allow leading identifier
    m = re.match(r"^([A-Za-z_][\w]*)(.*)$", path)
    if not m:
        return None
    cur: Any = None
    if isinstance(obj, dict) and m.group(1) in obj:
        cur = obj[m.group(1)]
    else:
        return None
    rest = m.group(2)
    for token in PATH_TOKEN.finditer(rest):
        key, idx, quoted = token.group(1), token.group(2), token.group(3)
        try:
            if idx is not None:
                cur = cur[int(idx)]
            else:
                cur = cur[key or quoted]
        except Exception:
            return None
    # leftover junk?
    consumed = PATH_TOKEN.sub("", rest)
    if consumed.strip():
        return None
    return cur


def _lookup_dollar(expr: str, ctx: dict[str, Any]) -> Any:
    expr = expr.strip()
    item = ctx.get("item") or {}
    json_data = item.get("json") if isinstance(item, dict) else {}
    if json_data is None:
        json_data = {}

    mapping = {
        "$json": json_data,
        "$itemIndex": ctx.get("itemIndex", 0),
        "$runIndex": ctx.get("runIndex", 0),
        "$now": ctx.get("now") or datetime.now(timezone.utc).isoformat(),
        "$today": (ctx.get("now_dt") or datetime.now(timezone.utc)).date().isoformat(),
        "$workflow": ctx.get("workflow") or {},
        "$execution": ctx.get("execution") or {},
        "$webhook": ctx.get("webhook") or {},
        "$env": ctx.get("env") or {},
    }

    # $node["Name"].json.path  or  $node['Name'].json
    node_m = re.match(r'^\$node\[[\'"](.+?)[\'"]\](.*)$', expr)
    if node_m:
        name, rest = node_m.group(1), node_m.group(2)
        nodes_out = ctx.get("nodes_out") or {}
        payload = nodes_out.get(name)
        if payload is None:
            return None
        rest = rest.lstrip(".")
        if rest.startswith("json"):
            items = payload.get("items") or []
            first = items[0]["json"] if items else {}
            more = rest[len("json") :].lstrip(".")
            return get_path({"_": first}, "_." + more) if more else first
        if rest.startswith("items"):
            return payload.get("items")
        return payload

    for prefix, value in mapping.items():
        if expr == prefix:
            return value
        if expr.startswith(prefix + ".") or expr.startswith(prefix + "["):
            tail = expr[len(prefix) :]
            if tail.startswith("."):
                tail = tail[1:]
                wrapped = {"root": value}
                return get_path(wrapped, "root." + tail) if tail else value
            if tail.startswith("["):
                wrapped = {"root": value}
                return get_path(wrapped, "root" + tail)
    return None


def eval_expression(expr: str, ctx: dict[str, Any]) -> Any:
    expr = expr.strip()
    # string literals
    if (expr.startswith('"') and expr.endswith('"')) or (expr.startswith("'") and expr.endswith("'")):
        return expr[1:-1]
    if re.fullmatch(r"-?\d+", expr):
        return int(expr)
    if re.fullmatch(r"-?\d+\.\d+", expr):
        return float(expr)
    if expr in ("true", "True"):
        return True
    if expr in ("false", "False"):
        return False
    if expr in ("null", "None", "nil"):
        return None
    if expr.startswith("$"):
        return _lookup_dollar(expr, ctx)
    # bare json path convenience: json.foo
    if expr.startswith("json.") or expr == "json":
        return _lookup_dollar("$" + expr if not expr.startswith("$") else expr, ctx)
    return _lookup_dollar(expr, ctx) if expr.startswith("$") else expr


def interpolate(value: Any, ctx: dict[str, Any]) -> Any:
    if not isinstance(value, str):
        if isinstance(value, dict):
            return {k: interpolate(v, ctx) for k, v in value.items()}
        if isinstance(value, list):
            return [interpolate(v, ctx) for v in value]
        return value
    s = value
    if s.startswith("=") and not s.startswith("=="):
        s = s[1:]
    matches = list(EXPR_RE.finditer(s))
    if not matches:
        return s
    if len(matches) == 1 and matches[0].span() == (0, len(s.strip()) if s == s.strip() else len(s)) or (
        len(matches) == 1 and matches[0].group(0) == s.strip()
    ):
        return eval_expression(matches[0].group(1), ctx)
    def repl(m: re.Match) -> str:
        val = eval_expression(m.group(1), ctx)
        if val is None:
            return ""
        if isinstance(val, (dict, list)):
            return json.dumps(val, ensure_ascii=False)
        return str(val)

    return EXPR_RE.sub(repl, s)


def as_bool(val: Any) -> bool:
    if isinstance(val, bool):
        return val
    if val is None:
        return False
    if isinstance(val, (int, float)):
        return val != 0
    if isinstance(val, (list, dict)):
        return len(val) > 0
    s = str(val).strip().lower()
    if s in {"", "0", "false", "no", "off", "null", "none"}:
        return False
    return True


def compare(left: Any, op: str, right: Any) -> bool:
    op = (op or "equals").lower()
    if op in {"exists", "isnotempty"}:
        return left not in (None, "", [], {})
    if op in {"notexists", "isempty"}:
        return left in (None, "", [], {})
    if op == "equals":
        return str(left) == str(right) if not (isinstance(left, (int, float)) and isinstance(right, (int, float))) else left == _coerce(right, left)
    if op == "notequals":
        return not compare(left, "equals", right)
    if op == "contains":
        return str(right) in str(left if left is not None else "")
    if op == "notcontains":
        return str(right) not in str(left if left is not None else "")
    if op == "startswith":
        return str(left).startswith(str(right))
    if op == "endswith":
        return str(left).endswith(str(right))
    if op == "regex":
        try:
            return re.search(str(right), str(left) if left is not None else "") is not None
        except re.error:
            return False
    if op in {"gt", "greaterthan"}:
        try:
            return float(left) > float(right)
        except Exception:
            return str(left) > str(right)
    if op in {"lt", "lessthan"}:
        try:
            return float(left) < float(right)
        except Exception:
            return str(left) < str(right)
    if op in {"gte"}:
        try:
            return float(left) >= float(right)
        except Exception:
            return str(left) >= str(right)
    if op in {"lte"}:
        try:
            return float(left) <= float(right)
        except Exception:
            return str(left) <= str(right)
    return False


def _coerce(value: Any, like: Any) -> Any:
    if isinstance(like, bool):
        return as_bool(value)
    if isinstance(like, int) and not isinstance(like, bool):
        try:
            return int(value)
        except Exception:
            return value
    if isinstance(like, float):
        try:
            return float(value)
        except Exception:
            return value
    return value


def parse_json_maybe(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    s = value.strip()
    if not s:
        return {}
    if s[0] in "{[":
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            return value
    return value
