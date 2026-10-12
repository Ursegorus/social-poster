# Deploys the Telegram webhook Worker, uploads secrets from local files, enables the webhook.
# Secrets are never printed. Run from PowerShell:  .\setup.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$root = Split-Path $PSScriptRoot

function Get-EnvValue($name) {
    $line = Get-Content "$root\.env" | Where-Object { $_ -like "$name=*" } | Select-Object -First 1
    return ($line -replace "^$name=", "").Trim().Trim('"').Trim("'")
}

$tg    = Get-EnvValue "TG_BOT_TOKEN"
$owner = Get-EnvValue "TG_OWNER_CHAT"
$wh    = (Get-Content "$root\.webhook_secret" -Raw).Trim()
$gh    = (Get-Content "$PSScriptRoot\.github_token" -Raw).Trim()
if (-not ($tg -and $owner -and $wh -and $gh)) { throw "One of the secrets is empty" }

Write-Host "1/4 deploying Worker..."
$out = (npx --yes wrangler deploy 2>&1 | Out-String)
$m = [regex]::Match($out, "https://[A-Za-z0-9.-]+\.workers\.dev")
if (-not $m.Success) { Write-Host $out; throw "Could not find Worker URL in deploy output" }
$url = $m.Value
Write-Host "    Worker URL: $url"

Write-Host "2/4 uploading secrets to Cloudflare..."
$tg    | npx --yes wrangler secret put TG_BOT_TOKEN   | Out-Null
$owner | npx --yes wrangler secret put OWNER_ID       | Out-Null
$wh    | npx --yes wrangler secret put WEBHOOK_SECRET | Out-Null
$gh    | npx --yes wrangler secret put GITHUB_TOKEN   | Out-Null

Write-Host "3/4 enabling Telegram webhook..."
$body = @{ url = $url; secret_token = $wh; allowed_updates = '["callback_query"]'; drop_pending_updates = "false" }
$r = Invoke-RestMethod -Method Post -Uri "https://api.telegram.org/bot$tg/setWebhook" -Body $body
Write-Host "    setWebhook ok: $($r.ok)"

Write-Host "4/4 removing local GitHub token file..."
Remove-Item "$PSScriptRoot\.github_token" -Force
Write-Host "Done. Tell Claude: setup finished."
