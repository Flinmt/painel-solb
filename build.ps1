$ErrorActionPreference = "Stop"

python -m pip install -e ".[dev]"
python -m pytest
python -m ruff check src tests
python -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --onedir `
    --name "Atualizador Exames" `
    --add-data "config;config" `
    --hidden-import "win32timezone" `
    src/atualizador_paineis/app.py

Write-Output "Aplicativo criado em dist\Atualizador Exames"
