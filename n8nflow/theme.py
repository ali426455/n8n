"""n8n-inspired dark theme + canvas HTML."""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any

from .i18n import is_rtl, t
from .nodes import get_spec

ASSETS = Path(__file__).resolve().parent.parent / "assets"

CSS = r"""
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=Vazirmatn:wght@400;500;600;700&display=swap');

html, body, [data-testid="stAppViewContainer"], .stApp {
  background: #101014 !important;
  color: #E8E8ED;
  font-family: 'Vazirmatn', 'IBM Plex Sans', sans-serif;
}
[data-testid="stHeader"] { background: rgba(16,16,20,.72); backdrop-filter: blur(12px); }
[data-testid="stToolbar"] { visibility: hidden; height: 0; }
#MainMenu { visibility: hidden; }
footer { visibility: hidden; }
[data-testid="stDecoration"] { display: none; }
.block-container { padding-top: 1.1rem; max-width: 1280px; }

[data-testid="stSidebar"] {
  background: #14141A !important;
  border-inline-end: 1px solid #2A2A33;
}
[data-testid="stSidebar"] * { font-family: 'Vazirmatn', 'IBM Plex Sans', sans-serif; }

.n8n-brand { display:flex; align-items:center; gap:10px; padding: 4px 4px 14px; }
.n8n-brand img { width:40px; height:40px; border-radius:12px; }
.n8n-brand h1 { font-size:1.05rem; margin:0; letter-spacing:-.02em; }
.n8n-brand p { margin:0; color:#9A9AA8; font-size:.75rem; }

.n8n-chip {
  display:inline-flex; align-items:center; gap:6px;
  background:#1E2A22; color:#3DDC84; border:1px solid #2A4A34;
  font-size:11px; font-weight:600; padding:3px 9px; border-radius:999px;
}
.n8n-chip.dot::before {
  content:""; width:7px; height:7px; border-radius:50%; background:#3DDC84;
  box-shadow:0 0 8px #3DDC84;
}

.n8n-hero {
  position:relative; overflow:hidden; border-radius:20px;
  border:1px solid #2A2A33; background:
    radial-gradient(800px 240px at 0% 0%, rgba(234,75,113,.22), transparent 55%),
    linear-gradient(180deg, #18181F 0%, #121218 100%);
  padding: 22px 24px 20px;
  margin-bottom: 18px;
}
.n8n-hero h2 { margin: 8px 0 6px; font-size:1.55rem; letter-spacing:-.03em; }
.n8n-hero p { color:#B4B4C0; margin:0 0 8px; line-height:1.65; max-width: 62ch; }
.n8n-hero img.banner {
  position:absolute; inset-inline-end:-20px; top:-30px; width:420px; opacity:.55;
  mask-image: linear-gradient(90deg, transparent, #000 30%);
  pointer-events:none;
}

.n8n-card {
  background:#18181F; border:1px solid #2A2A33; border-radius:16px;
  padding:14px 16px; margin-bottom:12px;
}
.n8n-card h3 { margin:0 0 8px; font-size:1rem; }
.n8n-muted { color:#9A9AA8; font-size:.85rem; }

.n8n-wf {
  background:#18181F; border:1px solid #2A2A33; border-radius:16px;
  padding:14px; transition: border-color .15s, transform .15s;
  height: 100%;
}
.n8n-wf:hover { border-color:#EA4B71; transform: translateY(-1px); }
.n8n-wf .title { font-weight:650; font-size:1.02rem; margin:0 0 4px; }
.n8n-badge {
  font-size:11px; font-weight:650; padding:2px 8px; border-radius:999px;
  display:inline-block;
}
.n8n-badge.on { background:#1E2A22; color:#3DDC84; }
.n8n-badge.off { background:#2A2A33; color:#9A9AA8; }
.n8n-badge.ok { background:#1E2A22; color:#3DDC84; }
.n8n-badge.err { background:#3A1A22; color:#FF6D85; }
.n8n-badge.run { background:#2A2438; color:#C4B5FD; }

.n8n-canvas-wrap {
  background:
    radial-gradient(circle at 1px 1px, #2A2A33 1px, transparent 0) 0 0 / 18px 18px,
    #121218;
  border:1px solid #2A2A33; border-radius:16px; overflow:auto;
  min-height: 360px; position:relative;
}
.n8n-node {
  position:absolute; width:168px; min-height:72px;
  background:#1C1C24; border:1px solid #34343F; border-radius:12px;
  box-shadow: 0 8px 24px rgba(0,0,0,.28);
  padding:10px 12px 10px;
}
.n8n-node.sel { border-color:#EA4B71; box-shadow:0 0 0 3px rgba(234,75,113,.25); }
.n8n-node .bar {
  height:4px; border-radius:4px; margin:-10px -12px 8px; background:#EA4B71;
}
.n8n-node .nm { font-weight:650; font-size:13px; line-height:1.25; }
.n8n-node .tp { color:#9A9AA8; font-size:11px; margin-top:2px; }
.n8n-node .ic { font-size:16px; margin-bottom:2px; }
.n8n-port {
  position:absolute; width:10px; height:10px; border-radius:50%;
  background:#9A9AA8; border:2px solid #1C1C24; top:50%;
}
.n8n-port.in { inset-inline-start:-6px; }
.n8n-port.out { inset-inline-end:-6px; }

.n8n-kicker { font-size:12px; letter-spacing:.08em; text-transform:uppercase; color:#EA4B71; font-weight:700; }

div[data-testid="stMetric"] {
  background:#18181F; border:1px solid #2A2A33; border-radius:14px; padding:8px 10px;
}

.stButton>button {
  border-radius:10px; font-weight:600; border:1px solid #34343F;
}
.stButton>button[kind="primary"] {
  background: linear-gradient(180deg,#F0628A,#EA4B71); border:none; color:white;
}
.stButton>button[kind="primary"]:hover { filter: brightness(1.06); }

[data-testid="stSidebarNav"] { display:none; }

.n8n-note {
  background:#1A1820; border:1px dashed #3A3348; color:#C4B5FD;
  border-radius:12px; padding:10px 12px; font-size:.88rem;
}

hr { border-color:#2A2A33; }
"""


def inject(lang: str | None = None) -> None:
    import streamlit as st

    rtl = is_rtl()
    direction = "rtl" if rtl else "ltr"
    extra = f"""
    <style>
    {CSS}
    .stApp, .block-container {{ direction: {direction}; }}
    [data-testid="stSidebar"] {{ direction: {direction}; }}
    .n8n-canvas-wrap {{ direction: ltr; }}
    </style>
    """
    st.markdown(extra, unsafe_allow_html=True)


def brand_sidebar() -> None:
    import streamlit as st

    logo = ASSETS / "logo.png"
    logo_html = ""
    if logo.exists():
        import base64

        b64 = base64.b64encode(logo.read_bytes()).decode("ascii")
        logo_html = f'<img src="data:image/png;base64,{b64}" alt="logo"/>'
    st.markdown(
        f"""
        <div class="n8n-brand">
          {logo_html}
          <div>
            <h1>{t("app_name")}</h1>
            <p>{t("sidebar_caption")}</p>
          </div>
        </div>
        <div class="n8n-chip dot">{t("online")}</div>
        """,
        unsafe_allow_html=True,
    )


def hero() -> None:
    import streamlit as st
    import base64

    banner = ASSETS / "banner.png"
    img = ""
    if banner.exists():
        b64 = base64.b64encode(banner.read_bytes()).decode("ascii")
        img = f'<img class="banner" src="data:image/png;base64,{b64}" alt=""/>'
    st.markdown(
        f"""
        <div class="n8n-hero">
          {img}
          <div class="n8n-kicker">GITHUB · STREAMLIT.APP</div>
          <h2>{t("hero_title")}</h2>
          <p>{t("hero_sub")}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def badge(active: bool) -> str:
    if active:
        return f'<span class="n8n-badge on">{t("active")}</span>'
    return f'<span class="n8n-badge off">{t("inactive")}</span>'


def status_badge(status: str) -> str:
    mapping = {"success": "ok", "error": "err", "running": "run"}
    cls = mapping.get(status or "", "off")
    label = t(status) if status in ("success", "error", "running") else (status or "—")
    return f'<span class="n8n-badge {cls}">{html.escape(str(label))}</span>'


def canvas_html(wf: dict, selected_id: str | None = None, height: int = 420) -> str:
    nodes = wf.get("nodes") or []
    conns = wf.get("connections") or {}
    if not nodes:
        return f'<div class="n8n-canvas-wrap" style="height:{height}px;display:flex;align-items:center;justify-content:center;color:#9A9AA8">{t("empty_canvas")}</div>'

    # bounds
    max_x, max_y = 700, height
    for n in nodes:
        pos = n.get("position") or [0, 0]
        max_x = max(max_x, int(pos[0]) + 220)
        max_y = max(max_y, int(pos[1]) + 140)
    w, h = max_x + 40, max(height, max_y)

    def center_of(node: dict, side: str) -> tuple[int, int]:
        x, y = (node.get("position") or [0, 0])
        if side == "out":
            return int(x) + 168, int(y) + 36
        return int(x), int(y) + 36

    by_name = {n.get("name"): n for n in nodes}
    paths = []
    for src_name, bundle in conns.items():
        src = by_name.get(src_name)
        if not src:
            continue
        mains = bundle.get("main") or []
        for dests in mains:
            for d in dests or []:
                tgt = by_name.get(d.get("node"))
                if not tgt:
                    continue
                x1, y1 = center_of(src, "out")
                x2, y2 = center_of(tgt, "in")
                mid = (x1 + x2) / 2
                paths.append(
                    f'<path d="M{x1},{y1} C{mid},{y1} {mid},{y2} {x2},{y2}" fill="none" stroke="#EA4B71" stroke-width="2" opacity=".85"/>'
                )

    cards = []
    for n in nodes:
        spec = get_spec(n.get("type") or "")
        x, y = (n.get("position") or [0, 0])
        sel = " sel" if selected_id and n.get("id") == selected_id else ""
        color = spec.get("color") or "#EA4B71"
        name = html.escape(str(n.get("name") or ""))
        lab = html.escape(str(spec.get("label") or n.get("type") or ""))
        icon = spec.get("icon") or "●"
        disabled = "opacity:.45;" if n.get("disabled") else ""
        cards.append(
            f"""
            <div class="n8n-node{sel}" style="left:{int(x)}px;top:{int(y)}px;{disabled}">
              <div class="bar" style="background:{color}"></div>
              <div class="ic">{icon}</div>
              <div class="nm">{name}</div>
              <div class="tp">{lab}</div>
              <span class="n8n-port in"></span>
              <span class="n8n-port out"></span>
            </div>
            """
        )
    return f"""
    <div class="n8n-canvas-wrap" style="height:{h}px">
      <svg width="{w}" height="{h}" style="position:absolute;inset:0">{''.join(paths)}</svg>
      {''.join(cards)}
    </div>
    """


def time_ago(iso: str | None) -> str:
    if not iso:
        return t("never")
    try:
        from datetime import datetime, timezone

        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        sec = int((datetime.now(timezone.utc) - dt).total_seconds())
        if sec < 45:
            return t("just_now")
        if sec < 3600:
            return t("minutes_ago", n=max(1, sec // 60))
        if sec < 86400:
            return t("hours_ago", n=sec // 3600)
        return t("days_ago", n=sec // 86400)
    except Exception:
        return iso[:16]


def public_base_url() -> str:
    from .db import get_setting

    saved = get_setting("public_url") or ""
    if saved:
        return saved.rstrip("/")
    try:
        import streamlit as st

        secrets_url = None
        try:
            secrets_url = st.secrets.get("public_url")
        except Exception:
            secrets_url = None
        if secrets_url:
            return str(secrets_url).rstrip("/")
        headers = getattr(st.context, "headers", None)
        if headers:
            host = headers.get("X-Forwarded-Host") or headers.get("Host") or headers.get("host")
            proto = headers.get("X-Forwarded-Proto") or "https"
            if host:
                return f"{proto}://{host}"
    except Exception:
        pass
    return ""
