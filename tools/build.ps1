param(
    [string]$Name = "CompProgGame"
)

$ErrorActionPreference = "Stop"

$projectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    throw "Virtual environment not found at .venv. Create it and install the dev dependencies first."
}

Push-Location $projectRoot
try {
    & $python -m PyInstaller `
        --noconfirm `
        --clean `
        --onefile `
        --windowed `
        --name $Name `
        --icon assets/icon.ico `
        --add-data "assets;assets" `
        src/compprog_pygame/__main__.py
}
finally {
    Pop-Location
}