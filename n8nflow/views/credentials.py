from __future__ import annotations

import streamlit as st

from n8nflow import db
from n8nflow.crypto import key_source
from n8nflow.i18n import get_lang, t
from n8nflow.nodes import CREDENTIAL_TYPES


def page() -> None:
    st.markdown(f"## {t('nav_credentials')}")
    src = key_source()
    if src != "secrets":
        st.markdown(f'<div class="n8n-note">{t("encryption_hint")}</div>', unsafe_allow_html=True)
    st.caption(f"key source: `{src}`")

    types = CREDENTIAL_TYPES
    lang = get_lang()
    type_labels = [f"{fa if lang == 'fa' else en}" for key, en, fa in types]
    type_keys = [k for k, _, _ in types]

    with st.form("new_cred"):
        name = st.text_input(t("cred_name"))
        tlabel = st.selectbox(t("cred_type"), type_labels)
        tkey = type_keys[type_labels.index(tlabel)]
        data: dict = {"_type": tkey}
        if tkey == "telegramApi":
            data["token"] = st.text_input(t("bot_token"), type="password")
            data["chatId"] = st.text_input(t("field_chat_id"))
        elif tkey == "openAiApi":
            data["apiKey"] = st.text_input(t("api_key"), type="password")
            data["baseUrl"] = st.text_input(t("base_url"), value="https://api.openai.com/v1")
        elif tkey == "smtp":
            data["host"] = st.text_input(t("smtp_host"), value="smtp.gmail.com")
            data["port"] = st.number_input(t("smtp_port"), value=587)
            data["username"] = st.text_input(t("smtp_user"))
            data["password"] = st.text_input(t("smtp_pass"), type="password")
            data["tls"] = st.checkbox(t("smtp_tls"), value=True)
        elif tkey == "discordWebhook":
            data["url"] = st.text_input(t("discord_url"), type="password")
        elif tkey == "httpHeaderAuth":
            data["headerName"] = st.text_input(t("header_name"), value="Authorization")
            data["headerValue"] = st.text_input(t("header_value"), type="password")
        elif tkey == "httpBasicAuth":
            data["username"] = st.text_input(t("username"))
            data["password"] = st.text_input(t("password"), type="password")
        else:
            data["token"] = st.text_input(t("secret_value"), type="password")
        submitted = st.form_submit_button(t("add_credential"), type="primary")
        if submitted:
            if not name:
                st.error(t("need_name"))
            else:
                db.save_credential(name, tkey, data)
                st.success(t("cred_saved"))
                st.rerun()

    creds = db.list_credentials()
    if not creds:
        st.info(t("no_credentials"))
        return
    for c in creds:
        cols = st.columns([3, 2, 1])
        cols[0].markdown(f"**{c['name']}**")
        cols[1].caption(c["type"])
        if cols[2].button("🗑", key=f"cd_{c['id']}"):
            db.delete_credential(c["id"])
            st.rerun()
