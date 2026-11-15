# Launches the Marketing Agents web app (Flask, port 5050).
# Keys come from the OpenBot vault at runtime; nothing secret is stored in this repo.
$ErrorActionPreference = 'Continue'

$vault = Join-Path $env:APPDATA 'OpenBot\agent-api-keys\.vault'
if (Test-Path $vault) {
    Get-ChildItem $vault -File | ForEach-Object {
        if ($_.Name -match '^[A-Z0-9_]+$') {
            Set-Item -Path "env:$($_.Name)" -Value ((Get-Content $_.FullName -Raw).Trim())
        }
    }
}

# Groq is blocked on the direct path from this machine; outbound API calls go through Clash.
$env:HTTP_PROXY  = 'http://127.0.0.1:7890'
$env:HTTPS_PROXY = 'http://127.0.0.1:7890'
$env:NO_PROXY    = 'localhost,127.0.0.1'
$env:PYTHONIOENCODING = 'utf-8'

# Groq model routing. Change these two lines to switch models everywhere.
# Available on this key: openai/gpt-oss-120b, openai/gpt-oss-20b, qwen/qwen3.8-27b, allam-2-7b
$env:GROQ_MODEL       = 'openai/gpt-oss-120b'   # long-form: briefs, articles, YouTube, blog, gate
$env:GROQ_MODEL_SHORT = 'openai/gpt-oss-20b'    # short-form: X, Facebook, LinkedIn

$logDir = 'D:\Agent_Market\logs'
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }

Set-Location 'D:\Agent_Market\social_media_generator'
& 'D:\Agent_Market\.venv\Scripts\python.exe' server.py *>> (Join-Path $logDir 'app.log')
