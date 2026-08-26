from __future__ import annotations

import pandas as pd
import pytest

from atualizador_paineis.core.errors import ValidationError
from atualizador_paineis.paineis.cx3.module import (
    DETAIL_COLUMNS,
    SUMMARY_COLUMNS,
    period_keep_mask,
    process_csv,
)


def report_frame(serviced: int = 3) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Queue": "8019 SOLB CALLCENTER",
                "Extension": None,
                "Queue Received Calls": 5,
                "Queue Serviced Calls": serviced,
                "Extension Serviced Calls": 0,
                "Talk Time": "00:00:00",
                "Average Talk Time": "00:00:00",
            },
            {
                "Queue": "8019 SOLB CALLCENTER",
                "Extension": "2220 Maria Silva",
                "Queue Received Calls": 0,
                "Queue Serviced Calls": 0,
                "Extension Serviced Calls": 2,
                "Talk Time": "01:30:00",
                "Average Talk Time": "00:45:00",
            },
            {
                "Queue": "8019 SOLB CALLCENTER",
                "Extension": "2221 João Souza",
                "Queue Received Calls": 0,
                "Queue Serviced Calls": 0,
                "Extension Serviced Calls": 1,
                "Talk Time": "00:10:30",
                "Average Talk Time": "00:10:30",
            },
            {
                "Queue": "8019 SOLB CALLCENTER",
                "Extension": "0000 Suporte",
                "Queue Received Calls": 0,
                "Queue Serviced Calls": 0,
                "Extension Serviced Calls": 0,
                "Talk Time": "00:00:00",
                "Average Talk Time": "00:00:00",
            },
        ]
    )


def test_processes_summary_agents_and_times() -> None:
    summary, detail = process_csv(report_frame(), pd.Period("2026-06", freq="M"))

    assert summary.columns.tolist() == SUMMARY_COLUMNS
    assert summary.iloc[0].tolist() == [2026, "JUNHO", 5, 3, 2]
    assert detail.columns.tolist() == DETAIL_COLUMNS
    assert detail["NOME"].tolist() == ["JOÃO SOUZA", "MARIA SILVA"]
    assert detail["ATENDIMENTOS"].sum() == 3
    assert detail.loc[detail["NOME"].eq("MARIA SILVA"), "TTA"].item() == 90.0


def test_rejects_difference_between_queue_and_agents() -> None:
    with pytest.raises(ValidationError, match="não corresponde"):
        process_csv(report_frame(serviced=4), pd.Period("2026-06", freq="M"))


def test_rejects_missing_summary_row() -> None:
    dataframe = report_frame().iloc[1:].copy()

    with pytest.raises(ValidationError, match="uma linha-resumo"):
        process_csv(dataframe, pd.Period("2026-06", freq="M"))


def test_period_replacement_recognizes_marco_with_or_without_accent() -> None:
    dataframe = pd.DataFrame(
        {
            "ANO": [2026, 2026, 2026],
            "MÊS": ["MARCO", "MARÇO", "ABRIL"],
        }
    )

    keep = period_keep_mask(dataframe, pd.Period("2026-03", freq="M"))

    assert keep.tolist() == [False, False, True]
