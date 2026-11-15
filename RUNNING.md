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
4. **The web app ignored the typed topic.** `/generate` called `generate_platform_content()`,
   which always loaded `shared/enriched_brief_latest.json`, so the operator's topic was only
   echoed back in the title while the post came from this week's brief. Now
   `shared/brief_generator.brief_for_topic()` writes a brief from the typed topic (plus the
   optional notes field) and `generate_platform_content(platforms, brief=...)` uses it. The
   brief is grounded in `vector_db/knowledge_base/my_products/mammalia-product-line.md`, so
   the model cannot invent memory sizes or port counts. `run_gate_on_platform_content(brief=...)`
   checks against the same brief, and the web path now saves `platform_content_latest.json`
   before running the gate (it used to grade the previous run's file).
5. **Empty content from `gpt-oss`.** Those models spend part of `max_tokens` on reasoning, so
   X came back as `[""]` and the brief call returned `json_validate_failed`. Both now send
   `reasoning_effort: low` and have larger budgets (`shared/brief_generator.py`,
   `shared/platform_writer.py`, `shared/quality_gate.py`).

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

- `vector_db/db` was missing, so the competitor RAG step reported 0 chunks. `chromadb` is now
  installed; `sentence-transformers` is optional and the builder falls back to ChromaDB's
  built-in all-MiniLM-L6-v2 embeddings.
- Product names now come from our own brief: **Mammalia Core Carrier** (RK3568 / RK3576 /
  RK3588 / Raspberry Pi 4 CM) and the **Dolphin edge controller**. The USD prices in
  `competitors.yaml` (145 / 259) are placeholders, not confirmed prices.
- `docs.elephantronics.com/purple-pi-oh2` returns 404, so those five URLs were dropped from
  `vector_db/config.yaml`; our own material is indexed from `vector_db/knowledge_base/my_products/`.
- Rockchip has no RK3578 part; the nearest chip is RK3576, which is what the configs use.
- Nothing is scheduled. `scheduler.py --schedule` would run the feeders on a timetable and
  spend SerpAPI credits.
