from __future__ import annotations

import streamlit as st

from n8nflow.i18n import get_lang, t
from n8nflow.nodes import GROUPS, SPECS
from n8nflow.theme import public_base_url


def page() -> None:
    st.markdown(f"## {t('nav_docs')}")
    st.write(t("docs_intro"))

    base = public_base_url()
    ping = f"{base}/?ping=1" if base else "https://YOUR-APP.streamlit.app/?ping=1"
    st.markdown(f"**{t('keep_alive_url')}**")
    st.code(ping)

    st.markdown(f"### {t('step_by_step')}")
    if get_lang() == "fa":
        st.markdown(
            """
1. این ریپو روی **GitHub** است (شاخه فعلی را پوش کنید).
2. بروید به [share.streamlit.io](https://share.streamlit.io) و با گیت‌هاب وارد شوید.
3. **New app** → ریپوی `n8n` را انتخاب کنید.
4. Branch را همین شاخه بگذارید، فایل اصلی: `app.py`.
5. Deploy. آدرس شما شبیه `https://xxxxx.streamlit.app` می‌شود.
6. در **Secrets** این را بگذارید:
```toml
encryption_key = "یک-عبارت-بلند-تصادفی"
public_url = "https://xxxxx.streamlit.app"
```
7. برای بیدار ماندن اپ رایگان، در [cron-job.org](https://cron-job.org) هر ۵ دقیقه `/?ping=1` را صدا بزنید.
            """
        )
    else:
        st.markdown(
            """
1. This repo lives on **GitHub** (push the current branch).
2. Open [share.streamlit.io](https://share.streamlit.io) and sign in with GitHub.
3. **New app** → pick the `n8n` repository.
4. Set the branch, main file `app.py`.
5. Deploy. Your URL looks like `https://xxxxx.streamlit.app`.
6. In **Secrets** add:
```toml
encryption_key = "a-long-random-passphrase"
public_url = "https://xxxxx.streamlit.app"
```
7. To keep the free app awake, ping `/?ping=1` every 5 minutes via [cron-job.org](https://cron-job.org).
            """
        )

    st.markdown(f"### {t('limitations')}")
    if get_lang() == "fa":
        st.markdown(
            """
- n8n اصلی (Node.js + دیتابیس پایدار) روی **Streamlit Community Cloud اجرا نمی‌شود**.
- وب‌هوک یعنی باز شدن URL همین اپ، نه یک سرور HTTP خام با وضعیت JSON خالص.
- زمان‌بندی فقط وقتی کار می‌کند که اپ بیدار باشد (پینگ کرون).
- فایل‌سیستم Cloud بعد از خواب/ریست پاک می‌شود؛ پس Secrets + دانلود پشتیبان ضروری است.
- نود Code بدون شبکه و فایل، محدود است.
            """
        )
    else:
        st.markdown(
            """
- Official n8n (Node.js + durable DB) **cannot run** on Streamlit Community Cloud.
- A webhook here means hitting this app's URL, not a raw HTTP JSON server.
- Schedules only fire while the app is awake (use a cron ping).
- Cloud filesystem is wiped on sleep/restart — use Secrets + backups.
- The Code node is sandboxed (no network, no files).
            """
        )

    st.markdown(f"### {t('expressions_title')}")
    st.code(
        """{{ $json.title }}
{{ $json.user.id }}
{{ $now }}
{{ $today }}
{{ $workflow.name }}
{{ $node["HTTP Request"].json }}
{{ $itemIndex }}""",
        language="text",
    )

    st.markdown(f"### {t('nodes_ref')}")
    lang = get_lang()
    for group, gkey in GROUPS:
        st.markdown(f"**{t(gkey)}**")
        rows = []
        for type_id, spec in SPECS.items():
            if spec.get("type") != type_id or spec["group"] != group:
                continue
            rows.append(
                {
                    " ": spec["icon"],
                    t("name"): spec["label_fa"] if lang == "fa" else spec["label"],
                    "type": type_id,
                }
            )
        if rows:
            st.dataframe(rows, hide_index=True, use_container_width=True)

    st.markdown(f"### {t('official_n8n')}")
    st.write(t("official_n8n_body"))
    st.code("docker compose -f deploy/docker-compose.yml up -d", language="bash")
    st.caption(t("sec_code"))
    st.link_button("Streamlit Community Cloud", "https://share.streamlit.io", use_container_width=True)
