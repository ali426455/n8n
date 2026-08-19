from __future__ import annotations

import streamlit as st

from n8nflow import db
from n8nflow.i18n import t
from n8nflow.theme import status_badge, time_ago


def page() -> None:
    st.markdown(f"## {t('nav_executions')}")
    wfs = db.list_workflows()
    names = {t("filter_all"): None} | {w["name"]: w["id"] for w in wfs}
    pick = st.selectbox(t("workflow"), list(names.keys()))
    wf_id = names[pick]
    exs = db.list_executions(100, workflow_id=wf_id)
    if not exs:
        st.info(t("no_executions"))
        return
    for ex in exs:
        with st.expander(
            f"{ex.get('workflow_name') or '—'} · {ex.get('status')} · {time_ago(ex.get('started_at'))}",
            expanded=False,
        ):
            st.markdown(status_badge(ex.get("status") or ""), unsafe_allow_html=True)
            c1, c2, c3 = st.columns(3)
            c1.write(f"**{t('mode')}:** {ex.get('mode')}")
            c2.write(f"**{t('started')}:** {str(ex.get('started_at') or '')[:19]}")
            c3.write(f"**{t('finished')}:** {str(ex.get('finished_at') or '')[:19]}")
            if ex.get("error"):
                st.error(ex["error"])
            data = ex.get("data") or {}
            if isinstance(data, dict):
                st.caption(f"{t('duration')}: {data.get('duration_ms', '—')} ms")
                st.json(data.get("items") or data)
                if data.get("node_results"):
                    st.markdown(f"**{t('node_output')}**")
                    st.json(data["node_results"])
            else:
                st.write(data)
