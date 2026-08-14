[CmdletBinding()]
param(
    [string]$BaseUrl = "http://127.0.0.1:5000"
)

$ErrorActionPreference = "Stop"
$serverProcess = $null

try {
    $k6 = Get-Command k6 -ErrorAction Stop
    $python = Get-Command py -ErrorAction SilentlyContinue
    if ($python) {
        $pythonArgs = @("-3.14", "-c")
    }
    else {
        $python = Get-Command python -ErrorAction Stop
        $pythonArgs = @("-c")
    }

    $stub = @'
from flask import Flask, jsonify
app = Flask(__name__)
app.add_url_rule("/health", endpoint="health", view_func=lambda: jsonify(status="ok"))
app.add_url_rule("/login", endpoint="login", view_func=lambda: '<form><input name="email"></form>')
app.run(host="127.0.0.1", port=5000, use_reloader=False)
'@
    $encodedStub = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($stub))
    $pythonCode = "exec(__import__('base64').b64decode('$encodedStub'))"

    $serverProcess = Start-Process `
        -FilePath $python.Source `
        -ArgumentList ($pythonArgs + $pythonCode) `
        -PassThru `
        -NoNewWindow

    $ready = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        try {
            $response = Invoke-WebRequest "$BaseUrl/health" -UseBasicParsing -TimeoutSec 1
            if ($response.StatusCode -eq 200) {
                $ready = $true
                break
            }
        }
        catch {
            Start-Sleep -Milliseconds 500
        }
    }

    if (-not $ready) {
        throw "Stub Flask não respondeu em $BaseUrl/health."
    }

    & $k6.Source run `
        -e "BASE_URL=$BaseUrl" `
        (Join-Path $PSScriptRoot "smoke.js")
    if ($LASTEXITCODE -ne 0) {
        throw "k6 smoke falhou com código $LASTEXITCODE."
    }
}
finally {
    if ($serverProcess -and -not $serverProcess.HasExited) {
        Stop-Process -Id $serverProcess.Id -Force
        $serverProcess.WaitForExit()
    }
}
