param(
    [switch]$Installer
)

$ErrorActionPreference = "Stop"

python -m pip install -e ".[dev]"
python -m pytest
python -m ruff check src tests
python -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --onedir `
    --name "Atualizador SOLB" `
    --add-data "config;config" `
    --add-data "atualizados;seed/atualizados" `
    --hidden-import "win32timezone" `
    src/atualizador_paineis/app.py

Write-Output "Aplicativo criado em dist\Atualizador SOLB"

if ($Installer) {
    $iscc = (Get-Command "ISCC.exe" -ErrorAction SilentlyContinue).Source
    if (-not $iscc) {
        $candidatePaths = @(
            "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
            "${env:ProgramFiles}\Inno Setup 6\ISCC.exe"
        )
        foreach ($candidate in $candidatePaths) {
            if (Test-Path -LiteralPath $candidate) {
                $iscc = $candidate
                break
            }
        }
    }
    if (-not $iscc) {
        throw "Inno Setup não encontrado. Instale o Inno Setup 6 ou adicione ISCC.exe ao PATH."
    }
    & $iscc "installer\AtualizadorSOLB.iss"
    Write-Output "Instalador criado em installer\output\Atualizador-SOLB-Setup.exe"
}
