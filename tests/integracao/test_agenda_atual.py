from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from atualizador_paineis.excel.automation import read_table_dataframe
from atualizador_paineis.paineis.agenda.module import read_input, transform

ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "dados" / "entrada" / "agenda" / "agenda.xlsx"
PANEL_DIRECTORY = ROOT / "atualizados"


def test_current_agenda_files_are_valid() -> None:
    panels = list(PANEL_DIRECTORY.glob("PAINEL DE AGENDAMENTOS (BOIODATA) - SOLB*.xlsx"))
    if not INPUT.exists() or len(panels) != 1:
        pytest.skip("Arquivos operacionais da Agenda não disponíveis neste ambiente")

    raw = read_input(INPUT)
    treated = transform(raw, pd.Period("2026-07", freq="M"))
    historical = read_table_dataframe(panels[0], "INPUT", "_9aacsokpj")

    assert len(raw) == 26
    assert raw["Quantidade"].sum() == 7_213
    assert round(raw["%"].sum(), 2) == 100
    assert treated["Titulo"].sum() == 7_213
    assert treated["Mês"].unique().tolist() == ["JULHO"]
    assert len(historical) == 458
