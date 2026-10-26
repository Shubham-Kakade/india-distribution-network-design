# Local setup for Windows (D-047): a virtual environment OUTSIDE OneDrive by default, the
# requirements, and a .env copied from .env.example with LLM_API_KEY left empty. An existing
# .env is never overwritten.
#
# Usage, from the repo root:
#   powershell -ExecutionPolicy Bypass -File scripts\setup_local.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\setup_local.ps1 -VenvPath D:\venvs\scnd -PythonVersion 3.12
param(
    [string]$VenvPath = "C:\venvs\scnd",   # keep it out of OneDrive (CLAUDE.md)
    [string]$PythonVersion = "3.11"        # passed to the py launcher as -3.11
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot

function Invoke-Checked([string]$Exe, [string[]]$Arguments) {
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Exe $($Arguments -join ' ') failed (exit $LASTEXITCODE)" }
}

if ($VenvPath -match "OneDrive") {
    Write-Warning "$VenvPath is inside OneDrive; OneDrive will try to sync thousands of files."
}
$VenvPython = Join-Path $VenvPath "Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    Invoke-Checked "py" @("-$PythonVersion", "-m", "venv", $VenvPath)
}
Invoke-Checked $VenvPython @("-m", "pip", "install", "--quiet", "--upgrade", "pip")
Invoke-Checked $VenvPython @("-m", "pip", "install", "--quiet", "-r", (Join-Path $Root "requirements.txt"))
Invoke-Checked $VenvPython @("-c", "import pulp; assert 'PULP_CBC_CMD' in pulp.listSolvers(onlyAvailable=True)")

$EnvFile = Join-Path $Root ".env"
if (Test-Path $EnvFile) {
    Write-Host ".env already exists: left unchanged"
} else {
    Copy-Item (Join-Path $Root ".env.example") $EnvFile
    Write-Host "Created .env from .env.example (LLM_API_KEY is empty, so the agent runs offline)"
}

Write-Host "Done. Next:"
Write-Host "  $VenvPath\Scripts\activate"
Write-Host "  pytest -q; streamlit run app/streamlit_app.py"
