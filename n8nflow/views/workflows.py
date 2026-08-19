from __future__ import annotations

import json

import streamlit as st

from n8nflow import db
from n8nflow.engine import empty_workflow, execute_workflow, import_n8n_workflow
from n8nflow.i18n import t
from n8nflow.navutil import open_editor
from n8nflow.seed import seed_examples
from n8nflow.theme import badge, time_ago


def page() -> None:
    st.markdown(f"## {t('nav_workflows')}")
    top = st.columns([2, 1, 1, 1])
    q = top[0].text_input(t("search"), label_visibility="collapsed", placeholder=t("search"))
    only_active = top[1].toggle(t("filter_active"), value=False)
    if top[2].button(t("new_workflow"), type="primary", use_container_width=True):
        wf = db.save_workflow(empty_workflow(t("new_workflow")))
        open_editor(wf["id"])
    if top[3].button(t("load_examples"), use_container_width=True):
        seed_examples()
        st.success(t("examples_loaded"))
        st.rerun()

    uploaded = st.file_uploader(t("import_n8n"), type=["json"])
    if uploaded is not None:
        try:
            payload = json.loads(uploaded.getvalue().decode("utf-8"))
            if payload.get("format") == "n8nflow-backup":
                db.import_backup(payload)
                st.success(t("restored"))
            else:
                wf = import_n8n_workflow(payload)
                extra = ""
                if wf.get("_unknown"):
                    extra = " — " + t("unknown_nodes") + ": " + ", ".join(wf["_unknown"][:6])
                st.success(t("imported") + extra)
            st.rerun()
        except Exception as exc:
            st.error(f"{t('import_error')}: {exc}")

    wfs = db.list_workflows()
    if q:
        ql = q.lower()
        wfs = [w for w in wfs if ql in (w.get("name") or "").lower()]
    if only_active:
        wfs = [w for w in wfs if w.get("active")]
    if not wfs:
        st.info(t("no_workflows"))
        return

    for wf in wfs:
        with st.container(border=True):
            c1, c2, c3, c4, c5, c6 = st.columns([3, 1.2, 1.2, 1, 1, 1])
            c1.markdown(f"**{wf['name']}**  \n:gray[{len(wf.get('nodes') or [])} {t('nodes')} · {t('last_run')}: {time_ago(wf.get('last_run_at'))}]")
            c2.markdown(badge(wf.get("active")), unsafe_allow_html=True)
            new_state = c2.toggle(t("active"), value=bool(wf.get("active")), key=f"act_{wf['id']}", label_visibility="collapsed")
            if bool(new_state) != bool(wf.get("active")):
                db.set_workflow_active(wf["id"], bool(new_state))
                st.rerun()
            if c3.button(t("open"), key=f"op_{wf['id']}", use_container_width=True):
                st.session_state.current_workflow_id = wf["id"]
                st.switch_page("editor")
            if c4.button("▶", key=f"rn_{wf['id']}", use_container_width=True, help=t("execute")):
                res = execute_workflow(wf, mode="manual")
                if res["status"] == "success":
                    st.toast(t("success"))
                else:
                    st.error(res.get("error") or t("error"))
            if c5.button("⧉", key=f"dp_{wf['id']}", use_container_width=True, help=t("duplicate")):
                db.duplicate_workflow(wf["id"])
                st.rerun()
            if c6.button("🗑", key=f"dl_{wf['id']}", use_container_width=True, help=t("delete")):
                st.session_state[f"confirm_{wf['id']}"] = True
            if st.session_state.get(f"confirm_{wf['id']}"):
                st.warning(t("confirm_delete"))
                d1, d2 = st.columns(2)
                if d1.button(t("yes_delete"), key=f"yes_{wf['id']}"):
                    db.delete_workflow(wf["id"])
                    st.session_state.pop(f"confirm_{wf['id']}", None)
                    st.rerun()
                if d2.button(t("cancel"), key=f"no_{wf['id']}"):
                    st.session_state.pop(f"confirm_{wf['id']}", None)
                    st.rerun()
