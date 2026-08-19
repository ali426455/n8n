# n8n Flow

اتوماسیون ورک‌فلو، الهام‌گرفته از [n8n](https://n8n.io)، نوشته‌شده با **Streamlit** تا بتوانید آن را از روی **GitHub** روی **[streamlit.app](https://streamlit.app)** دیپلوی کنید و آدرسش همیشه در دسترس بماند.

> **نکته مهم:** موتور رسمی n8n یک اپ Node.js است و روی Streamlit Community Cloud اجرا نمی‌شود. این ریپو یک سرور اتوماسیون سازگار با همان ایده (نود، اتصال، وب‌هوک، cron، HTTP، تلگرام، OpenAI، …) است که *می‌تواند* روی `*.streamlit.app` بالا بماند. اگر بعداً Docker/VPS داشتید، `deploy/docker-compose.yml` موتور رسمی را هم بالا می‌آورد.

---

## English

n8n-inspired workflow automation as a Streamlit app. Push this GitHub repo to [Streamlit Community Cloud](https://share.streamlit.io) and you get an always-reachable `*.streamlit.app` URL.

Official n8n cannot run on Streamlit Cloud. This app is the path that *does*.

### Deploy on streamlit.app (always on)

1. Push this repository to GitHub (the branch you want to serve).
2. Open [https://share.streamlit.io](https://share.streamlit.io) and sign in with GitHub.
3. **New app** → select this repo → main file `app.py`.
4. Deploy. Your server URL looks like `https://xxxxx.streamlit.app`.
5. In **App settings → Secrets** add:

```toml
encryption_key = "a-long-random-passphrase"
public_url = "https://xxxxx.streamlit.app"
```

6. Keep the free instance awake with a 5-minute cron ping:

```
https://xxxxx.streamlit.app/?ping=1
```

Use [cron-job.org](https://cron-job.org) or GitHub Actions. Without a ping, Community Cloud sleeps after idle time; the URL still works, it just cold-starts.

### Local run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py --server.address 0.0.0.0
```

Open `http://localhost:8501`.

### What you get

| Feature | Notes |
| --- | --- |
| Visual canvas | n8n-like nodes & bezier links |
| Triggers | Manual, Webhook (`/?hook=TOKEN`), Cron |
| Nodes | HTTP, Set, IF, Switch, Filter, Code (sandboxed Python), JSON, DateTime, Crypto, Merge, Wait, RSS, Telegram, Discord, SMTP, OpenAI, Respond |
| Expressions | `{{ $json.field }}`, `$now`, `$node["Name"].json` |
| Credentials | Encrypted at rest |
| Import | n8n-style workflow JSON |
| Backup | Full JSON export/restore |

### Webhook

Activate a workflow that starts with a **Webhook** node, then call:

```
https://YOUR-APP.streamlit.app/?hook=TOKEN&hello=world
```

### Official n8n (optional, not Streamlit)

```bash
docker compose -f deploy/docker-compose.yml up -d
```

---

## فارسی — دیپلوی همیشه‌آنلاین

1. همین ریپو را روی GitHub داشته باشید.
2. بروید [share.streamlit.io](https://share.streamlit.io) و با گیت‌هاب وارد شوید.
3. **New app** → این ریپو → فایل `app.py`.
4. Deploy. آدرس می‌شود `https://xxxxx.streamlit.app`.
5. در Secrets مقدار `encryption_key` و `public_url` را بگذارید.
6. هر ۵ دقیقه `/?ping=1` را پینگ کنید تا اپ رایگان نخوابد.

### اجرای محلی

```bash
pip install -r requirements.txt
streamlit run app.py --server.address 0.0.0.0
```

### محدودیت‌ها نسبت به n8n اصلی

- وب‌هوک یعنی باز شدن URL همین اپ (نه سرور HTTP خام با JSON خالص).
- زمان‌بندی فقط وقتی اپ بیدار است کار می‌کند.
- دیسک Streamlit Cloud بعد از خواب/ریست پاک می‌شود؛ Secrets و پشتیبان ضروری است.
- نود Code بدون شبکه و فایل اجرا می‌شود.

### عبارات

```
{{ $json.title }}
{{ $json.user.id }}
{{ $now }}
{{ $node["HTTP Request"].json }}
```
