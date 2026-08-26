from __future__ import annotations

import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class PanelConfig:
    name: str
    panel_glob: str
    output_name: str
    panel_directory: Path
    input_directory: Path
    output_directory: Path
    raw_sheet: str
    treated_sheet: str
    raw_table: str
    treated_table: str
    auxiliary_sheet: str | None = None
    auxiliary_table: str | None = None
    auxiliary_month_column: str | None = None
    auxiliary_quantity_column: str | None = None


def project_root() -> Path:
    if getattr(sys, "frozen", False):
        bundle_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        if (bundle_root / "config" / "paineis.toml").exists():
            return bundle_root
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "config" / "paineis.toml").exists():
            return parent
    return Path.cwd()


def workspace_root() -> Path:
    if getattr(sys, "frozen", False):
        executable_dir = Path(sys.executable).resolve().parent
        if executable_dir.name == "Atualizador Exames":
            return executable_dir.parent
        return executable_dir
    return project_root()


def load_panel_config(key: str, root: Path | None = None) -> PanelConfig:
    base = root or project_root()
    with (base / "config" / "paineis.toml").open("rb") as config_file:
        values = tomllib.load(config_file)[key]
    return PanelConfig(
        name=values["nome"],
        panel_glob=values["painel_glob"],
        output_name=values["nome_saida"],
        panel_directory=Path(values["pasta_painel"]),
        input_directory=Path(values["pasta_entrada"]),
        output_directory=Path(values["pasta_saida"]),
        raw_sheet=values["aba_brutos"],
        treated_sheet=values["aba_tratados"],
        raw_table=values["tabela_brutos"],
        treated_table=values["tabela_tratados"],
        auxiliary_sheet=values.get("aba_auxiliar"),
        auxiliary_table=values.get("tabela_auxiliar"),
        auxiliary_month_column=values.get("coluna_mes_auxiliar"),
        auxiliary_quantity_column=values.get("coluna_quantidade_auxiliar"),
    )
