from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from atualizador_paineis.excel.automation import read_table_dataframe
from atualizador_paineis.paineis.cx3.module import _read_csv, process_csv

ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "dados" / "entrada" / "3cx" / "queue_performance.csv"
PANEL_DIRECTORY = ROOT / "atualizados"


def test_current_3cx_files_match_june_2026() -> None:
    panels = list(PANEL_DIRECTORY.glob("PAINEL LIGAÇÕES (3CX) - SOLB*.xlsx"))
    if not INPUT.exists() or len(panels) != 1:
        pytest.skip("Arquivos operacionais da 3CX não disponíveis neste ambiente")

    summary, detail = process_csv(_read_csv(INPUT), pd.Period("2026-06", freq="M"))
    historical_summary = read_table_dataframe(panels[0], "CONFIG - 2025", "Tabela1")
    historical_detail = read_table_dataframe(panels[0], "CONFIG - 2025", "Tabela2")

    assert summary.loc[0, ["Recebidas", "Atendidas", "Não atendidas"]].tolist() == [
        4_112,
        3_747,
        365,
    ]
    assert detail["ATENDIMENTOS"].sum() == 3_747
    assert len(detail) == 4
    june_summary = historical_summary.loc[
        historical_summary["ANO"].eq(2026) & historical_summary["Mês"].eq("JUNHO")
    ]
    june_detail = historical_detail.loc[
        historical_detail["ANO"].eq(2026) & historical_detail["MÊS"].eq("JUNHO")
    ]
    assert len(june_summary) == 1
    assert june_summary[["Recebidas", "Atendidas", "Não atendidas"]].iloc[0].tolist() == [
        4_112,
        3_747,
        365,
    ]
    assert june_detail["ATENDIMENTOS"].sum() == 3_747
