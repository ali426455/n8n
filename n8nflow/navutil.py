from __future__ import annotations


def open_editor(wf_id: str) -> None:
    import streamlit as st

    st.session_state.current_workflow_id = wf_id
    st.session_state.pop("editor_wf", None)
    st.session_state.pop("editor_cache_id", None)
    st.session_state._goto = "editor"
    st.rerun()
