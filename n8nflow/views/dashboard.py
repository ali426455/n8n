from __future__ import annotations

import streamlit as st

from n8nflow import db
from n8nflow.engine import run_due_schedules
from n8nflow.i18n import t
from n8nflow.navutil import open_editor
from n8nflow.seed import seed_examples
from n8nflow.theme import badge, hero, status_badge, time_ago


def page() -> None:
    hero()
    stats = db.execution_stats()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(t("metric_workflows"), stats["workflows"])
    c2.metric(t("metric_active"), stats["active"])
    c3.metric(t("metric_exec_today"), stats["today"])
    c4.metric(t("metric_success"), f"{stats['success_rate']}%")

    st.markdown("")
    a, b, c = st.columns([1, 1, 1])
    with a:
        if st.button(t("new_workflow"), type="primary", use_container_width=True):
            from n8nflow.engine import empty_workflow

            wf = db.save_workflow(empty_workflow(t("new_workflow")))
            open_editor(wf["id"])
    with b:
        if st.button(t("load_examples"), use_container_width=True):
            n = seed_examples()
            st.success(t("examples_loaded") + f" ({n})")
            st.rerun()
    with c:
        if st.button(t("run_due"), use_container_width=True):
            ran = run_due_schedules()
            st.info(t("due_ran") + f" ({len(ran)})")

    st.markdown("### " + t("quick_start"))
    wfs = db.list_workflows()
    if not wfs:
        st.markdown(
            f'<div class="n8n-card"><p class="n8n-muted">{t("no_workflows")}</p></div>',
            unsafe_allow_html=True,
        )
    else:
        cols = st.columns(min(3, len(wfs)))
        for i, wf in enumerate(wfs[:6]):
            with cols[i % len(cols)]:
                st.markdown(
                    f"""
                    <div class="n8n-wf">
                      <div class="title">{wf['name']}</div>
                      {badge(wf['active'])}
                      <p class="n8n-muted">{len(wf.get('nodes') or [])} {t("nodes")} · {t("last_run")}: {time_ago(wf.get("last_run_at"))}</p>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                b1, b2 = st.columns(2)
                if b1.button(t("open"), key=f"dash_open_{wf['id']}", use_container_width=True):
                    open_editor(wf["id"])
                if b2.button(t("execute"), key=f"dash_run_{wf['id']}", use_container_width=True):
                    from n8nflow.engine import execute_workflow

                    res = execute_workflow(wf, mode="manual")
                    if res["status"] == "success":
                        st.success(t("success"))
                    else:
                        st.error(res.get("error") or t("error"))

    st.markdown("### " + t("recent_executions"))
    exs = db.list_executions(8)
    if not exs:
        st.caption(t("no_executions"))
        return
    for ex in exs:
        st.markdown(
            f"""
            <div class="n8n-card" style="padding:10px 14px">
              {status_badge(ex.get("status"))}
              <b style="margin:0 8px">{ex.get("workflow_name") or "—"}</b>
              <span class="n8n-muted">{ex.get("mode")} · {time_ago(ex.get("started_at"))}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
