from __future__ import annotations

import os
import shutil
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

APP_DATA_DIRECTORY = Path("SOLB") / "Atualizador SOLB"
PANEL_KEYS = ("agenda", "exames", "cirurgias", "atendimentos", "comparativo", "3cx")


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
        local_app_data = Path.home() / "AppData" / "Local"
        if sys.platform == "win32":
            local_app_data = Path(os.environ.get("LOCALAPPDATA", local_app_data))
        return local_app_data / APP_DATA_DIRECTORY
    return project_root()


def initialize_workspace(root: Path | None = None) -> Path:
    """Cria as pastas graváveis necessárias para uma execução instalada ou local."""
    workspace = root or workspace_root()
    for key in PANEL_KEYS:
        config = load_panel_config(key)
        for directory in (
            config.panel_directory,
            config.input_directory,
            config.output_directory,
        ):
            (workspace / directory).mkdir(parents=True, exist_ok=True)
    seed_directory = project_root() / "seed" / "atualizados"
    panel_directory = workspace / "atualizados"
    if seed_directory.exists() and seed_directory.resolve() != panel_directory.resolve():
        for source in seed_directory.glob("*.xlsx"):
            destination = panel_directory / source.name
            if not destination.exists():
                shutil.copy2(source, destination)
    return workspace


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
