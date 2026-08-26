import pandas as pd

from atualizador_paineis.core.data_cleaning import (
    discard_placeholder_professionals,
    filter_dashboard_records,
)


def test_discards_placeholder_professional_ignoring_case_and_spaces() -> None:
    dataframe = pd.DataFrame(
        {
            "Profissional Solicitante": [
                "MÉDICO REAL",
                "Profissional",
                "  PROFISSIONAL  ",
                "Profissional Assistente",
                None,
            ],
            "QTD": [1, 1, 1, 1, 1],
        }
    )

    result, discarded = discard_placeholder_professionals(dataframe)

    assert discarded == 2
    assert result["Profissional Solicitante"].tolist()[:2] == [
        "MÉDICO REAL",
        "Profissional Assistente",
    ]
    assert pd.isna(result["Profissional Solicitante"].iloc[2])


def test_dashboard_filter_preserves_raw_and_discards_all_invalid_markers() -> None:
    raw = pd.DataFrame(
        {
            "Profissional": ["MÉDICO REAL", "Profissional", "MÉDICO TESTE", "MÉDICO REAL"],
            "Paciente": ["PACIENTE", "PACIENTE", "PACIENTE", "PACIENTE TESTE"],
        }
    )

    treated, summary = filter_dashboard_records(raw, "Profissional", "Paciente")

    assert len(raw) == 4
    assert treated["Profissional"].tolist() == ["MÉDICO REAL"]
    assert summary.discarded_rows == 3
    assert summary.placeholder_professionals == 1
    assert summary.test_professionals == 1
    assert summary.test_patients == 1
