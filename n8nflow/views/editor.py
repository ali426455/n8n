from __future__ import annotations

import copy
import json

import streamlit as st

from n8nflow import db
from n8nflow.engine import (
    auto_layout,
    connect_nodes,
    disconnect_node,
    empty_workflow,
    execute_workflow,
    unique_node_name,
    webhook_token,
)
from n8nflow.i18n import get_lang, t
from n8nflow.nodes import GROUPS, SPECS, get_spec
from n8nflow.theme import canvas_html, public_base_url


def _ensure_wf() -> dict | None:
    wf_id = st.session_state.get("current_workflow_id")
    qp = st.query_params.get("wf")
    if qp and qp != wf_id:
        wf_id = qp
        st.session_state.current_workflow_id = wf_id
    if not wf_id:
        return None
    if st.session_state.get("editor_cache_id") == wf_id and "editor_wf" in st.session_state:
        return st.session_state.editor_wf
    wf = db.get_workflow(wf_id)
    if not wf:
        return None
    st.session_state.editor_wf = wf
    st.session_state.editor_cache_id = wf_id
    st.session_state.selected_node_id = (wf["nodes"][0]["id"] if wf.get("nodes") else None)
    return wf


def _dirty_save(wf: dict) -> None:
    saved = db.save_workflow(wf)
    st.session_state.editor_wf = saved
    st.session_state.editor_cache_id = saved["id"]


def _selected(wf: dict) -> dict | None:
    sid = st.session_state.get("selected_node_id")
    for n in wf.get("nodes") or []:
        if n.get("id") == sid:
            return n
    return None


def _add_node(wf: dict, type_id: str) -> None:
    spec = get_spec(type_id)
    lang = get_lang()
    base = spec["label_fa"] if lang == "fa" else spec["label"]
    name = unique_node_name(wf["nodes"], base)
    sel = _selected(wf)
    if sel:
        x = int((sel.get("position") or [180, 200])[0]) + 230
        y = int((sel.get("position") or [180, 200])[1])
    else:
        x, y = 180 + 230 * len(wf["nodes"]), 200
    params = {}
    for f in spec.get("fields") or []:
        if "default" in f:
            params[f["name"]] = f["default"]
    node = {
        "id": db.new_id(),
        "name": name,
        "type": type_id,
        "typeVersion": 1,
        "position": [x, y],
        "parameters": params,
    }
    wf["nodes"].append(node)
    if sel and not spec.get("is_trigger"):
        connect_nodes(wf, sel["name"], name, 0)
    st.session_state.selected_node_id = node["id"]
    _dirty_save(wf)


def _sync_widgets(wf: dict) -> None:
    """Pull current widget values into the in-memory workflow before Execute."""
    for n in wf.get("nodes") or []:
        spec = get_spec(n.get("type") or "")
        params = n.setdefault("parameters", {})
        for field in spec.get("fields") or []:
            key = f"f_{n['id']}_{field['name']}"
            if key in st.session_state:
                val = st.session_state[key]
                if field["type"] == "credentials":
                    continue
                params[field["name"]] = val
        dis_key = f"dis_{n['id']}"
        if dis_key in st.session_state:
            n["disabled"] = bool(st.session_state[dis_key])


def _render_field(node: dict, field: dict) -> None:
    params = node.setdefault("parameters", {})
    name = field["name"]
    ftype = field["type"]
    key = f"f_{node['id']}_{name}"
    label_key = f"field_{name}"
    label = t(label_key) if t(label_key) != label_key else name
    current = params.get(name, field.get("default"))

    if ftype == "select":
        opts = field.get("options") or []
        idx = opts.index(current) if current in opts else 0
        val = st.selectbox(label, opts, index=idx, key=key)
    elif ftype == "bool":
        val = st.checkbox(label, value=bool(current), key=key)
    elif ftype == "number":
        val = st.number_input(label, value=float(current or 0), key=key)
        if isinstance(val, float) and float(val).is_integer() and not isinstance(field.get("default"), float):
            val = int(val)
    elif ftype == "text":
        val = st.text_area(label, value=str(current or ""), height=110, key=key)
    elif ftype == "code":
        val = st.text_area(label, value=str(current or ""), height=180, key=key)
    elif ftype == "json":
        val = st.text_area(label, value=str(current or "{}"), height=80, key=key)
    elif ftype == "credentials":
        allowed = set(field.get("cred_types") or [])
        creds = [c for c in db.list_credentials() if not allowed or c["type"] in allowed]
        options = [t("none")] + [f"{c['name']} ({c['type']})" for c in creds]
        ids = [None] + [c["id"] for c in creds]
        current_id = current or (node.get("credentials") or {}).get("id")
        index = ids.index(current_id) if current_id in ids else 0
        choice = st.selectbox(t("use_credential"), options, index=index, key=key)
        val = ids[options.index(choice)] if choice in options else None
        if val:
            node["credentials"] = {"id": val}
        else:
            node.pop("credentials", None)
            val = None
    else:
        val = st.text_input(label, value="" if current is None else str(current), key=key)

    params[name] = val
    for n in st.session_state.editor_wf.get("nodes") or []:
        if n.get("id") == node["id"]:
            n.setdefault("parameters", {})[name] = val
            if node.get("credentials"):
                n["credentials"] = node["credentials"]
            break


def page() -> None:
    wf = _ensure_wf()
    if not wf:
        st.info(t("no_wf_editor"))
        if st.button(t("create_first"), type="primary"):
            created = db.save_workflow(empty_workflow(t("new_workflow")))
            st.session_state.current_workflow_id = created["id"]
            st.session_state.pop("editor_wf", None)
            st.rerun()
        wfs = db.list_workflows()
        if wfs:
            names = {w["name"]: w["id"] for w in wfs}
            pick = st.selectbox(t("select_workflow"), list(names))
            if st.button(t("open")):
                st.session_state.current_workflow_id = names[pick]
                st.session_state.pop("editor_wf", None)
                st.rerun()
        return

    st.query_params["wf"] = wf["id"]
    _sync_widgets(wf)

    top = st.columns([3, 1, 1, 1, 1, 1])
    new_name = top[0].text_input(t("workflow_name"), value=wf.get("name") or "", label_visibility="collapsed")
    if new_name and new_name != wf.get("name"):
        wf["name"] = new_name
        _dirty_save(wf)
    active = top[1].toggle(t("active"), value=bool(wf.get("active")))
    if bool(active) != bool(wf.get("active")):
        wf["active"] = bool(active)
        _dirty_save(wf)
    if top[2].button(t("save"), use_container_width=True):
        _dirty_save(wf)
        st.toast(t("saved"))
    if top[3].button(t("execute"), type="primary", use_container_width=True):
        with st.spinner(t("running")):
            res = execute_workflow(wf, mode="manual")
        st.session_state.last_exec = res
    if top[4].button(t("auto_layout"), use_container_width=True):
        auto_layout(wf)
        _dirty_save(wf)
        st.rerun()
    export = {
        "name": wf.get("name"),
        "nodes": wf.get("nodes"),
        "connections": wf.get("connections"),
        "settings": wf.get("settings") or {},
        "active": False,
    }
    top[5].download_button(
        t("export"),
        data=json.dumps(export, ensure_ascii=False, indent=2),
        file_name=f"{(wf.get('name') or 'workflow').replace(' ', '_')}.json",
        mime="application/json",
        use_container_width=True,
    )

    token = webhook_token(wf)
    if token:
        base = public_base_url()
        url = f"{base}/?hook={token}" if base else f"?hook={token}"
        st.caption(f"{t('webhook_url')}: `{url}`")

    left, mid, right = st.columns([1.15, 2.4, 1.35])

    with left:
        st.markdown(f"**{t('palette')}**")
        lang = get_lang()
        for group, gkey in GROUPS:
            with st.expander(t(gkey), expanded=(group == "trigger")):
                for type_id, spec in SPECS.items():
                    if spec.get("type") != type_id:
                        continue  # skip aliases
                    if spec["group"] != group:
                        continue
                    lab = spec["label_fa"] if lang == "fa" else spec["label"]
                    if st.button(f"{spec['icon']}  {lab}", key=f"add_{type_id}", use_container_width=True):
                        _add_node(wf, type_id)
                        st.rerun()

    with mid:
        st.markdown(f"**{t('canvas')}**")
        st.markdown(canvas_html(wf, st.session_state.get("selected_node_id")), unsafe_allow_html=True)
        names = [n.get("name") for n in wf.get("nodes") or []]
        ids = [n.get("id") for n in wf.get("nodes") or []]
        if ids:
            try:
                current = ids.index(st.session_state.get("selected_node_id")) if st.session_state.get("selected_node_id") in ids else 0
            except Exception:
                current = 0
            picked = st.radio(
                t("selected_node"),
                options=list(range(len(ids))),
                format_func=lambda i: f"{get_spec(wf['nodes'][i].get('type')).get('icon','')}  {wf['nodes'][i].get('name')}",
                index=current,
                horizontal=True,
                label_visibility="collapsed",
            )
            st.session_state.selected_node_id = ids[picked]
        st.caption(t("hint_expr"))

    with right:
        node = _selected(wf)
        st.markdown(f"**{t('selected_node')}**")
        if not node:
            st.caption(t("no_node_selected"))
        else:
            spec = get_spec(node.get("type") or "")
            st.markdown(f"{spec.get('icon')} **{node.get('name')}**")
            desc = spec.get("description_fa") if get_lang() == "fa" else spec.get("description")
            if desc:
                st.caption(desc)
            new_n = st.text_input(t("node_name"), value=node.get("name") or "", key=f"nm_{node['id']}")
            if new_n and new_n != node["name"]:
                old = node["name"]
                # rewrite connections
                conns = wf.get("connections") or {}
                if old in conns:
                    conns[new_n] = conns.pop(old)
                for src, bundle in conns.items():
                    for dests in bundle.get("main") or []:
                        for d in dests or []:
                            if d.get("node") == old:
                                d["node"] = new_n
                node["name"] = new_n
                _dirty_save(wf)
                st.rerun()
            disabled = st.checkbox(t("disabled_node"), value=bool(node.get("disabled")), key=f"dis_{node['id']}")
            node["disabled"] = disabled
            for field in spec.get("fields") or []:
                _render_field(node, field)

            st.markdown(f"**{t('connections')}**")
            others = [n["name"] for n in wf["nodes"] if n["id"] != node["id"]]
            if others:
                labels = spec.get("output_labels") or ["main"]
                branch = 0
                if len(labels) > 1:
                    branch = st.selectbox(
                        t("branch"),
                        list(range(len(labels))),
                        format_func=lambda i: labels[i] if i < len(labels) else str(i),
                        key=f"br_{node['id']}",
                    )
                target = st.selectbox(t("connect_to"), others, key=f"tg_{node['id']}")
                if st.button(t("connect"), key=f"cn_{node['id']}", use_container_width=True):
                    connect_nodes(wf, node["name"], target, int(branch))
                    _dirty_save(wf)
                    st.rerun()
            if st.button(t("clear_connections"), key=f"cc_{node['id']}", use_container_width=True):
                disconnect_node(wf, node["name"])
                _dirty_save(wf)
                st.rerun()
            if st.button(t("remove_node"), key=f"rm_{node['id']}", use_container_width=True):
                triggers = [n for n in wf["nodes"] if get_spec(n.get("type")).get("is_trigger")]
                if get_spec(node.get("type")).get("is_trigger") and len(triggers) <= 1:
                    st.error(t("cannot_delete_last_trigger"))
                else:
                    disconnect_node(wf, node["name"])
                    wf["nodes"] = [n for n in wf["nodes"] if n["id"] != node["id"]]
                    st.session_state.selected_node_id = wf["nodes"][0]["id"] if wf["nodes"] else None
                    _dirty_save(wf)
                    st.rerun()
            if st.button(t("save"), key=f"svnode_{node['id']}", type="primary", use_container_width=True):
                _dirty_save(wf)
                st.toast(t("saved"))

    res = st.session_state.get("last_exec")
    if res and res.get("workflow_id") == wf.get("id"):
        st.markdown("---")
        st.markdown(f"### {t('execution_result')}")
        if res.get("status") == "success":
            st.success(f"{t('success')} · {res.get('duration_ms')} ms")
        else:
            st.error(res.get("error") or t("error"))
        tabs = st.tabs([t("items_count"), t("node_output"), t("raw_json")])
        with tabs[0]:
            st.json(res.get("items") or [])
        with tabs[1]:
            for name, nr in (res.get("node_results") or {}).items():
                with st.expander(f"{'✅' if nr.get('ok') else '❌'} {name}", expanded=not nr.get("ok")):
                    if nr.get("error"):
                        st.error(nr["error"])
                    st.json(nr.get("outputs") or nr.get("items"))
        with tabs[2]:
            st.json({k: v for k, v in res.items() if k != "node_results"} | {"nodes": list((res.get("node_results") or {}).keys())})
