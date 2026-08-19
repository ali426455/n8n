from __future__ import annotations

import json

import streamlit as st

from n8nflow import __version__, db
from n8nflow.crypto import key_source
from n8nflow.i18n import get_lang, set_lang, t
from n8nflow.theme import public_base_url


def page() -> None:
    st.markdown(f"## {t('nav_settings')}")

    lang = get_lang()
    choice = st.radio(t("lang"), ["fa", "en"], index=0 if lang == "fa" else 1, format_func=lambda x: t("persian") if x == "fa" else t("english"), horizontal=True)
    if choice != lang:
        set_lang(choice)
        db.set_setting("lang", choice)
        st.rerun()

    name = st.text_input(t("instance_name"), value=db.get_setting("instance_name") or "n8n Flow")
    public = st.text_input(t("public_url"), value=db.get_setting("public_url") or public_base_url(), help=t("public_url_help"))
    tz = st.text_input(t("timezone"), value=db.get_setting("timezone") or "UTC")
    if st.button(t("save"), type="primary"):
        db.set_setting("instance_name", name)
        db.set_setting("public_url", public.strip())
        db.set_setting("timezone", tz)
        st.success(t("settings_saved"))

    st.caption(f"{t('host_detected')}: {public_base_url() or '—'} · {t('version')} {__version__} · key={key_source()}")

    st.markdown(f"### {t('backup')}")
    backup = db.export_backup()
    st.download_button(
        t("download_backup"),
        data=json.dumps(backup, ensure_ascii=False, indent=2),
        file_name="n8nflow-backup.json",
        mime="application/json",
    )
    up = st.file_uploader(t("restore_backup"), type=["json"])
    if up is not None:
        try:
            payload = json.loads(up.getvalue().decode("utf-8"))
            counts = db.import_backup(payload)
            st.success(t("backup_restored_n", w=counts["workflows"], c=counts["credentials"]))
        except Exception as exc:
            st.error(str(exc))

    st.markdown(f"### {t('about')}")
    st.write(t("about_body"))

    with st.expander(t("danger_zone")):
        st.caption(t("danger_reset_help"))
        if st.button(t("reset_data")):
            db.reset_all()
            st.session_state.clear()
            st.success(t("reset_done"))
            st.rerun()
