# Loads OpenBot vault keys into this PowerShell session's environment (values never printed),
# plus the Clash proxy that outbound API calls need from this machine.
$vault = Join-Path $env:APPDATA 'OpenBot\agent-api-keys\.vault'
if (Test-Path $vault) {
    Get-ChildItem $vault -File | ForEach-Object {
        $name = $_.Name
        if ($name -match '^[A-Z0-9_]+$') {
            Set-Item -Path "env:$name" -Value ((Get-Content $_.FullName -Raw).Trim())
        }
    }
}
$env:HTTP_PROXY  = 'http://127.0.0.1:7890'
$env:HTTPS_PROXY = 'http://127.0.0.1:7890'
$env:NO_PROXY    = 'localhost,127.0.0.1'
$env:PYTHONIOENCODING = 'utf-8'
