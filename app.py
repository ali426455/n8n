#!/usr/bin/env python3
"""n8n Flow — always-on workflow automation for Streamlit Community Cloud."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

from n8nflow import __version__, db
from n8nflow.engine import execute_workflow, run_due_schedules, webhook_token
from n8nflow.i18n import get_lang, set_lang, t
from n8nflow.seed import seed_if_empty
from n8nflow.theme import inject, brand_sidebar, public_base_url
from n8nflow.views import credentials, dashboard, docs, editor, executions, settings, webhooks, workflows

ROOT = Path(__file__).resolve().parent
LOGO = ROOT / "assets" / "logo.png"

st.set_page_config(
    page_title="n8n Flow",
    page_icon=str(LOGO) if LOGO.exists() else "🔀",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "Get help": "https://share.streamlit.io",
        "About": f"n8n Flow v{__version__} — Streamlit automation inspired by n8n",
    },
)


def bootstrap() -> None:
    db.init_db()
    if "lang" not in st.session_state:
        set_lang(db.get_setting("lang") or "fa")
    if "bootstrapped" not in st.session_state:
        seed_if_empty()
        st.session_state.bootstrapped = True
    inject()


def handle_special_routes() -> bool:
    """Webhook + keep-alive endpoints. Return True if the request was fully handled."""
    params = st.query_params
    hook = params.get("hook") or params.get("webhook")
    if hook:
        _render_hook(str(hook))
        return True
    if params.get("ping") is not None:
        ran = run_due_schedules()
        st.json(
            {
                "ok": True,
                "app": "n8n Flow",
                "version": __version__,
                "ts": datetime.now(timezone.utc).isoformat(),
                "schedules_ran": len(ran),
            }
        )
        return True
    return False


def _render_hook(token: str) -> None:
    st.markdown(f"### {t('webhook')}")
    match = None
    for wf in db.list_workflows():
        if webhook_token(wf) == token:
            match = wf
            break
    if not match:
        st.error(t("webhook_missing"))
        return
    if not match.get("active"):
        st.warning(t("webhook_inactive") + f" — {match.get('name')}")
        return
    payload: dict = {}
    # leftover query keys become the payload
    for k, v in st.query_params.items():
        if k in {"hook", "webhook", "ping"}:
            continue
        payload[k] = v
    if "payload" in payload:
        try:
            payload = json.loads(str(payload["payload"]))
        except Exception:
            pass
    db.log_webhook(token, match["id"], payload, {"source": "http"})
    with st.spinner(t("running")):
        res = execute_workflow(match, mode="webhook", trigger_data=payload or {"ok": True})
    if res.get("status") == "success":
        st.success(t("webhook_fired") + f" · {match.get('name')}")
    else:
        st.error(res.get("error") or t("error"))
    st.json(res.get("webhook_response"))
    with st.expander(t("raw_json")):
        st.json({"id": res.get("id"), "status": res.get("status"), "items": res.get("items"), "duration_ms": res.get("duration_ms")})


def maybe_run_schedules() -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")
    if st.session_state.get("_sched_stamp") == stamp:
        return
    st.session_state._sched_stamp = stamp
    try:
        run_due_schedules()
    except Exception:
        pass


def main() -> None:
    bootstrap()
    if handle_special_routes():
        return
    maybe_run_schedules()

    with st.sidebar:
        brand_sidebar()
        st.markdown("")
        lang = get_lang()
        cols = st.columns(2)
        if cols[0].button("FA", use_container_width=True, type="primary" if lang == "fa" else "secondary"):
            set_lang("fa")
            db.set_setting("lang", "fa")
            st.rerun()
        if cols[1].button("EN", use_container_width=True, type="primary" if lang == "en" else "secondary"):
            set_lang("en")
            db.set_setting("lang", "en")
            st.rerun()
        st.caption(t("made_for"))
        base = public_base_url()
        if base:
            st.caption(base)

    dash = st.Page(dashboard.page, title=t("nav_dashboard"), icon="🏠", url_path="home", default=True)
    wfs = st.Page(workflows.page, title=t("nav_workflows"), icon="📂", url_path="workflows")
    ed = st.Page(editor.page, title=t("nav_editor"), icon="🔀", url_path="editor")
    ex = st.Page(executions.page, title=t("nav_executions"), icon="📜", url_path="executions")
    cred = st.Page(credentials.page, title=t("nav_credentials"), icon="🔑", url_path="credentials")
    hooks = st.Page(webhooks.page, title=t("nav_webhooks"), icon="🪝", url_path="webhooks")
    sett = st.Page(settings.page, title=t("nav_settings"), icon="⚙️", url_path="settings")
    guide = st.Page(docs.page, title=t("nav_docs"), icon="🚀", url_path="deploy")

    nav = st.navigation(
        {
            t("app_name"): [dash, wfs, ed],
            "I/O": [ex, cred, hooks],
            "Meta": [sett, guide],
        }
    )
    goto = st.session_state.pop("_goto", None)
    if goto == "editor":
        st.switch_page(ed)
    nav.run()


if __name__ == "__main__":
    main()
else:
    main()
