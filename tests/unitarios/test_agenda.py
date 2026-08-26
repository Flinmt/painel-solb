from __future__ import annotations

import pandas as pd
import pytest

from atualizador_paineis.core.data_cleaning import filter_dashboard_records
from atualizador_paineis.core.errors import ValidationError
from atualizador_paineis.paineis.agenda.module import (
    OUTPUT_COLUMNS,
    period_keep_mask,
    read_input,
    transform,
)


def agenda_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Usuario": ["WEB", "MARIA"],
            "Quantidade": [75, 25],
            "%": ["75,00", "25,00"],
        }
    )


def write_agenda(tmp_path, dataframe: pd.DataFrame):
    path = tmp_path / "agenda.xlsx"
    dataframe.to_excel(path, index=False)
    return path


def test_reads_and_transforms_agenda(tmp_path) -> None:
    source = read_input(write_agenda(tmp_path, agenda_frame()))

    result = transform(source, pd.Period("2026-07", freq="M"))

    assert result.columns.tolist() == OUTPUT_COLUMNS
    assert result["category"].tolist() == ["WEB", "MARIA"]
    assert result["Titulo"].tolist() == [75, 25]
    assert result["Mês"].tolist() == ["JULHO", "JULHO"]
    assert result["Ano"].tolist() == [2026, 2026]


def test_accepts_percentages_stored_as_decimal_fraction(tmp_path) -> None:
    dataframe = agenda_frame()
    dataframe["%"] = [0.75, 0.25]

    result = read_input(write_agenda(tmp_path, dataframe))

    assert result["%"].tolist() == [75.0, 25.0]


def test_rejects_duplicate_users_ignoring_case_and_spaces(tmp_path) -> None:
    dataframe = pd.DataFrame(
        {
            "Usuario": ["Maria", " maria "],
            "Quantidade": [50, 50],
            "%": [50, 50],
        }
    )

    with pytest.raises(ValidationError, match="duplicados"):
        read_input(write_agenda(tmp_path, dataframe))


def test_rejects_percentage_inconsistent_with_quantity(tmp_path) -> None:
    dataframe = agenda_frame()
    dataframe["%"] = [60, 40]

    with pytest.raises(ValidationError, match="não correspondem"):
        read_input(write_agenda(tmp_path, dataframe))


def test_discards_test_and_profissional_markers() -> None:
    dataframe = pd.DataFrame(
        {
            "Usuario": ["WEB", "USUÁRIO TESTE", " Profissional "],
            "Quantidade": [80, 10, 10],
            "%": [80, 10, 10],
        }
    )

    result, discards = filter_dashboard_records(dataframe, "Usuario")

    assert result["Usuario"].tolist() == ["WEB"]
    assert discards.discarded_rows == 2


def test_reprocessing_period_replaces_only_selected_month() -> None:
    historical = pd.DataFrame(
        {
            "category": ["MAIO", "JUNHO", "JULHO"],
            "Titulo": [1, 2, 3],
            "Mês": ["MAIO", "JUNHO", "JULHO"],
            "Ano": [2026, 2026, 2026],
        }
    )

    keep = period_keep_mask(historical, pd.Period("2026-06", freq="M"))

    assert keep.tolist() == [True, False, True]
