from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from atualizador_paineis.paineis.cirurgias.module import (
    RAW_COLUMNS,
    TREATED_COLUMNS,
    read_input,
    transform,
)

ROOT = Path(__file__).resolve().parents[2]
INPUT_FILE = ROOT / "dados" / "entrada" / "cirurgias" / "cirurgias.xlsx"


def test_current_surgeries_input_is_june_2026() -> None:
    if not INPUT_FILE.exists():
        pytest.skip("Arquivo operacional não disponível neste ambiente")

    raw = read_input(INPUT_FILE)
    treated = transform(raw)

    assert len(raw) == 218
    assert raw.columns.tolist() == RAW_COLUMNS
    assert treated.columns.tolist() == TREATED_COLUMNS
    assert raw["Data de Solicitação"].dt.to_period("M").nunique() == 1
    assert raw["Data de Solicitação"].dt.to_period("M").iloc[0] == pd.Period("2026-06", freq="M")
    assert set(treated["QTD"]) == {1}
