# AGENTS.md

## Cursor Cloud specific instructions

Two products live in this repo. The one to run for UI work is the Flask web app.

### Web app (`app.py`)

- Dependencies refresh on startup via `pip install -r requirements.txt`.
- Start with `python3 app.py`. It binds `0.0.0.0` on **port 5001** (`PORT` env overrides). Do not use 5000.
- Open `http://localhost:5001`, search a ticker (`PLTR`, `NVDA`, `005930`, or a Korean name like `삼성전자`). Analysis hits `/api/analyze` and needs outbound HTTPS to Yahoo Finance (and Google News / Translate for KR search).
- First `yfinance` fetch is often 10–30s; the UI shows a spinner until then.
- Charts use Chart.js from jsDelivr. The page HTML/CSS/JS lives inside a Python triple-quoted string in `app.py` — keep quotes compatible with that.
- Startup tries `webbrowser.open`; it is harmless if that fails in this environment.
- There is no lint or test suite. Syntax check: `python3 -m py_compile app.py scripts/*.py`.

### Daily report (optional)

`scripts/stock_news.py` is the GitHub Actions email/Issue job. It is not required to exercise the web UI. SMTP (`EMAIL_TO` / `EMAIL_FROM` / `EMAIL_PASSWORD`) and `GH_TOKEN` are only needed for that path.

### Production

Render uses `gunicorn app:app --bind 0.0.0.0:$PORT` (`render.yaml`).
