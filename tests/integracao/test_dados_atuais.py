from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from atualizador_paineis.paineis.exames.module import (
    CATEGORIES,
    RAW_COLUMNS,
    TREATED_COLUMNS,
    _read_input,
    _transform,
)

ROOT = Path(__file__).resolve().parents[2]
INPUT_DIRECTORY = ROOT / "dados" / "entrada" / "exames"


@pytest.mark.parametrize("key", ["imagem", "laboratorio", "terapia", "outros"])
def test_current_input_files_have_valid_schema_and_single_period(key: str) -> None:
    path = INPUT_DIRECTORY / f"{key}.xlsx"
    if not path.exists():
        pytest.skip("Arquivo operacional não disponível neste ambiente")

    dataframe = _read_input(path, CATEGORIES[key])
    dates = pd.to_datetime(dataframe["Data de Solicitação"], dayfirst=True, errors="coerce")

    assert dataframe.columns.tolist() == RAW_COLUMNS
    assert not dates.isna().any()
    assert dates.dt.to_period("M").nunique() == 1
    assert str(dates.dt.to_period("M").iloc[0]) == "2026-07"


def test_current_inputs_generate_10346_treated_rows() -> None:
    paths = {key: INPUT_DIRECTORY / f"{key}.xlsx" for key in CATEGORIES}
    if not all(path.exists() for path in paths.values()):
        pytest.skip("Arquivos operacionais não disponíveis neste ambiente")

    raw = pd.concat(
        [_read_input(path, CATEGORIES[key]) for key, path in paths.items()],
        ignore_index=True,
    )
    treated = _transform(raw)

    assert len(raw) == 10_346
    assert len(treated) == 10_346
    assert treated.columns.tolist() == TREATED_COLUMNS
