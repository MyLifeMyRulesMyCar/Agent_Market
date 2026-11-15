# Agent_Market — running locally

Cloned from `git@github.com:MyLifeMyRulesMyCar/Agent_Market.git` into `D:\Agent_Market`.

## What runs

| Service | URL | Started by |
|---|---|---|
| Social Content Generator (Flask, interactive) | http://localhost:5050 | `start_app_hidden.vbs` |
| Command Centre + pipeline + weekly brief (static) | http://127.0.0.1:5070 | `start_dash_hidden.vbs` |

Port 5060 is blocked by Chrome as an unsafe port, hence 5070 for the dashboards.

Logs: `D:\Agent_Market\logs\app.log`.

## Environment

Python 3.12 venv at `D:\Agent_Market\.venv`. Installed: flask, flask-cors, groq,
python-dotenv, pyyaml, beautifulsoup4, openpyxl, schedule, requests, feedparser,
praw, tavily-python, pdfplumber, python-docx.

`load_keys.ps1` copies every key in the OpenBot vault into the session environment and
sets the Clash proxy. `run_app.ps1` does the same for the web app. No key is written to disk
in this repo.

**Proxy is required.** `api.groq.com` returns 403 on the direct path from this machine and 200
through Clash (`127.0.0.1:7890`), so every launcher sets `HTTP_PROXY`/`HTTPS_PROXY`.

## Keys in use (OpenBot vault)

| Key | Used by |
|---|---|
| `GROQ_API_KEY` | every agent, the web app, brief/writer/quality gate |
| `SERPAPI_KEY` | `Serpi_feeder` (Google Trends), 250 searches/month |
| `TAVILY_API_KEY` | `tavily_feeder`, `trend_analyser` links |
| `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` | `reddit_watcher`, `customer_behaviour` |

## Groq models (change here, one line)

Model names are no longer hardcoded. Every call site reads environment variables:

| Variable | Used for | Default |
|---|---|---|
| `GROQ_MODEL` | briefs, articles, YouTube script, blog, quality gate | `openai/gpt-oss-120b` |
| `GROQ_MODEL_SHORT` | X, Facebook, LinkedIn | `openai/gpt-oss-20b` |
| `GROQ_MODEL_GATE` | quality gate only (optional override) | falls back to `GROQ_MODEL` |

Set them in `run_app.ps1` (the app) or export them before running an agent by hand.
Models available on this key, measured 15 Nov 2026 on the brief prompt:

| Model | Time | Tokens | JSON |
|---|---|---|---|
| `openai/gpt-oss-120b` | 2.3 s | 954 | valid |
| `qwen/qwen3.8-27b` | 1.0 s | 563 | valid |
| `openai/gpt-oss-20b` | 2.5 s | 1136 | valid |

Switching is verified end to end: with `GROQ_MODEL=qwen/qwen3.8-27b`,
`shared/platform_content_latest.json` records `model_routing: {linkedin: qwen/qwen3.8-27b}`.

## Fixes made for this machine


1. **Groq models.** The repo asks for `llama-3.3-70b-versatile` and `llama-3.1-8b-instant`;
   Groq has retired both. Mapped to `openai/gpt-oss-120b` (long-form) and
   `openai/gpt-oss-20b` (short-form) in 10 files.
2. **`orchestrator.py` `run_step`.** It imported each step's `main()` without clearing
   `sys.argv`, so `platform_writer`'s own argparse rejected the orchestrator's `--force`
   and killed the run. `sys.argv` is now reset for each step and `SystemExit` is reported
   as a step failure.
3. Stale `__pycache__` removed after the model edit (it caused one misleading `400`).

## Pipeline order that works

```
RSS_Feeder/main.py            # no key
Serpi_feeder/main.py          # SERPAPI_KEY
tavily_feeder/main.py         # TAVILY_API_KEY
reddit_watcher/main.py        # Reddit pair -> output/reddit_raw.json
customer_behaviour/main.py    # -> customer_behaviour/output/latest.json
trend_analyser/main.py        # -> trend_analyser/output/latest.json
seo_agent/main.py             # -> seo_agent/output/latest.json
orchestrator.py --force       # six steps, writes shared/platform_content_latest.json
```

`orchestrator.py --force` alone re-uses whatever the analysers last wrote.

## Known gaps

- `vector_db/db` does not exist, so the competitor RAG step reports 0 chunks. Building it
  needs `chromadb` + `sentence-transformers` (about 2 GB with torch).
- Performance bias in the web app stays inactive until posts are logged in the tracker.
- The `Mammalia Core Carrier` product in the configs and UI is the repo author's product, not an
  Elephantronics SKU.
- Nothing is scheduled. `scheduler.py --schedule` would run the feeders on a timetable and
  spend SerpAPI credits.
