# Agent Instructions

## Runtime

- Windows-only Python `>=3.12` application; Microsoft Excel is required for real workbook publishing.
- Install with `python -m pip install -e ".[dev]"`; because this is a `src` layout, run the app as `python -m atualizador_paineis`.
- `Abrir Atualizador de Paineis.cmd` is hard-coded to `C:\Python314\pythonw.exe`; use the module command when that interpreter is unavailable.

## Structure

- `src/atualizador_paineis/paineis/` owns the six panel modules; register any new module in `paineis/registry.py` to create its GUI tab.
- `config/paineis.toml` is the source of truth for panel globs, input/output directories, worksheet names, and table names; update it with module changes.
- Shared cleaning, auditing, logging, artifacts, and Excel operations are in `src/atualizador_paineis/core/` and `src/atualizador_paineis/excel/`.
- `atualizados/` holds the live workbooks. Operational inputs and generated outputs under `dados/` are ignored and may be unavailable in a fresh checkout.
- Comparativo requires Exames to run first in the same competence; it consumes `dados/saida/compartilhados/exames/exames-consolidado.xlsx` and validates its manifest/hash.

## Verification

- Run checks in this order: `python -m pytest`, then `python -m ruff check src tests`.
- Focus a test with `python -m pytest tests/unitarios/test_exames.py -q`; integration tests skip when required operational files are absent.
- Build only through `.\build.ps1` in PowerShell; it installs dev dependencies, runs both checks, and invokes PyInstaller for `dist\Atualizador Exames`.
- Close the target workbook in Excel before manually updating a panel; publishing rejects Excel lock files and refreshes pivots through COM.

## Style

- Ruff targets Python 3.12, 100-character lines, and rules `E`, `F`, `I`, `UP`, and `B`.
