from __future__ import annotations

import pandas as pd

from atualizador_paineis.paineis.comparativo.module import (
    OUTPUT_COLUMNS,
    build_comparison,
    merge_period,
)


def appointment_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Tipo": [
                "CONSULTA",
                "RETORNO",
                "PEQUENO ATENDIMENTO",
                "CONSULTA",
                "CONSULTA",
            ],
            "Médico": ["Médico A", "Médico A", "Médico A", "Médico Teste", "Médico A"],
            "Paciente": ["A", "B", "C", "D", "PACIENTE TESTE"],
            "Data": pd.to_datetime(
                ["2026-06-01", "2026-06-02", "2026-06-03", "2026-06-04", "2026-06-05"]
            ),
        }
    )


def exam_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Tipo de Exame": ["RM DE JOELHO", "RX DE JOELHO", "RM DE OMBRO"],
            "QTD": [2, 10, 5],
            "Profissional Solicitante": ["Médico A", "Médico A", "Médico A"],
            "Data de Solicitação": pd.to_datetime(["2026-06-05", "2026-06-06", "2026-06-07"]),
            "Paciente": ["A", "B", "PACIENTE TESTE"],
            "Tipo": ["Imagem", "Imagem", "Imagem"],
        }
    )


def surgery_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Profissional Solicitante": ["Médico A", "Médico B", "Médico B"],
            "Data de Solicitação": pd.to_datetime(["2026-06-07", "2026-06-08", "2026-06-09"]),
            "Paciente": ["A", "B", "PACIENTE TESTE"],
        }
    )


def test_build_comparison_applies_each_metric_rule() -> None:
    result, discards = build_comparison(appointment_frame(), exam_frame(), surgery_frame())

    assert result.columns.tolist() == OUTPUT_COLUMNS
    assert discards.discarded_rows == 4
    doctor_a = result.loc[result["Profissional"] == "MÉDICO A"].iloc[0]
    assert doctor_a["Consultas"] == 2
    assert doctor_a["Exames"] == 2
    assert doctor_a["Cirurgias"] == 1
    doctor_b = result.loc[result["Profissional"] == "MÉDICO B"].iloc[0]
    assert doctor_b["Consultas"] == 0
    assert doctor_b["Exames"] == 0
    assert doctor_b["Cirurgias"] == 1


def test_reprocessing_period_replaces_existing_summary() -> None:
    june, _ = build_comparison(appointment_frame(), exam_frame(), surgery_frame())
    may = june.copy()
    may["Mês"] = "MAIO"
    existing = pd.concat([may, june], ignore_index=True)
    corrected = june.copy()
    corrected["Consultas"] = corrected["Consultas"] + 1

    merged, _, _ = merge_period(existing, corrected, pd.Period("2026-06", freq="M"))
    merged_again, _, _ = merge_period(merged, corrected, pd.Period("2026-06", freq="M"))

    assert len(merged) == len(merged_again) == len(may) + len(corrected)
    june_result = merged.loc[merged["Mês"] == "JUNHO"]
    assert june_result["Consultas"].tolist() == corrected["Consultas"].tolist()
