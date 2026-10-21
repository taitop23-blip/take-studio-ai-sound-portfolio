$ErrorActionPreference = 'Stop'
$studioRoot = $PSScriptRoot
$studioPython = Join-Path $studioRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $studioPython)) {
    throw 'Take Studio 실행 환경이 없습니다. README의 설치 안내를 확인해 주세요.'
}
$studioReady = $false
try {
    $studioStatus = Invoke-RestMethod 'http://127.0.0.1:38765/api/status' -TimeoutSec 2
    $studioReady = $null -ne $studioStatus.models
} catch { }
if (-not $studioReady) {
    $studioLogDir = Join-Path $studioRoot 'logs'
    New-Item -ItemType Directory -Force -Path $studioLogDir | Out-Null
    $studioProcess = Start-Process -FilePath $studioPython -ArgumentList @('-u', 'app.py') -WorkingDirectory $studioRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $studioLogDir 'server.log') -RedirectStandardError (Join-Path $studioLogDir 'server-error.log')
    $studioProcess.Id | Set-Content -LiteralPath (Join-Path $studioRoot 'server.pid')
    for ($studioAttempt = 0; $studioAttempt -lt 40; $studioAttempt++) {
        Start-Sleep -Milliseconds 500
        try {
            $studioStatus = Invoke-RestMethod 'http://127.0.0.1:38765/api/status' -TimeoutSec 2
            if ($null -ne $studioStatus.models) { $studioReady = $true; break }
        } catch { }
    }
}
if (-not $studioReady) { throw '앱을 시작하지 못했습니다. logs 폴더의 server-error.log를 확인해 주세요.' }
Start-Process 'http://127.0.0.1:38765'
