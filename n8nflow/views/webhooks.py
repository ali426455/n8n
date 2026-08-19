from __future__ import annotations

import json

import streamlit as st

from n8nflow import db
from n8nflow.engine import execute_workflow, webhook_token
from n8nflow.i18n import t
from n8nflow.theme import public_base_url, time_ago


def page() -> None:
    st.markdown(f"## {t('nav_webhooks')}")
    st.caption(t("webhook_help"))
    base = public_base_url()
    ping = f"{base}/?ping=1" if base else "?ping=1"
    st.markdown(f'<div class="n8n-note">{t("keep_alive")}<br/><code>{ping}</code></div>', unsafe_allow_html=True)

    wfs = [w for w in db.list_workflows() if webhook_token(w)]
    if not wfs:
        st.info(t("no_workflows"))
    for wf in wfs:
        token = webhook_token(wf)
        url = f"{base}/?hook={token}" if base else f"?hook={token}"
        with st.container(border=True):
            st.markdown(f"**{wf['name']}** {'🟢' if wf.get('active') else '⚪️'}")
            st.code(url, language="text")
            payload = st.text_area(t("payload"), value='{"hello":"world"}', key=f"pl_{wf['id']}", height=80)
            if st.button(t("simulate"), key=f"sim_{wf['id']}"):
                if not wf.get("active"):
                    st.warning(t("webhook_inactive"))
                else:
                    try:
                        body = json.loads(payload) if payload.strip() else {}
                    except json.JSONDecodeError:
                        body = {"raw": payload}
                    db.log_webhook(token or "", wf["id"], body, {"source": "simulator"})
                    res = execute_workflow(wf, mode="webhook", trigger_data=body)
                    if res["status"] == "success":
                        st.success(t("webhook_fired"))
                        st.json(res.get("webhook_response"))
                    else:
                        st.error(res.get("error"))

    st.markdown(f"### {t('inbox')}")
    inbox = db.list_webhook_inbox(40)
    if not inbox:
        st.caption(t("empty_inbox"))
        return
    for row in inbox:
        with st.expander(f"{row.get('token')} · {time_ago(row.get('received_at'))}"):
            st.json(row.get("payload"))
