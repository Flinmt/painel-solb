from __future__ import annotations

import pandas as pd

from atualizador_paineis.paineis.atendimentos.module import (
    RAW_COLUMNS,
    TREATED_COLUMNS,
    discard_test_records,
    merge_period,
    transform,
)


def raw_frame(
    date: str,
    doctor: str = "MÉDICO REAL",
    patient: str = "PACIENTE REAL",
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Convênio": "CONVÊNIO",
                "Código": "001",
                "Tipo": "CONSULTA",
                "Médico": doctor,
                "Paciente": patient,
                "CPF": "000",
                "Total": 1,
                "Data": pd.Timestamp(date),
                "Unidade": "UNIDADE",
            }
        ],
        columns=RAW_COLUMNS,
    )


def test_transform_adds_month_year_and_quantity() -> None:
    result = transform(raw_frame("2026-06-10 12:30:00"))

    assert result.columns.tolist() == TREATED_COLUMNS
    assert result.loc[0, "Mês"] == "JUNHO"
    assert result.loc[0, "Ano"] == 2026
    assert result.loc[0, "Quantidade"] == 1


def test_discards_test_doctors_and_patients() -> None:
    dataframe = pd.concat(
        [
            raw_frame("2026-06-10"),
            raw_frame("2026-06-11", doctor="MÉDICO TESTE"),
            raw_frame("2026-06-12", patient="PACIENTE TESTE"),
        ],
        ignore_index=True,
    )

    result, discarded = discard_test_records(dataframe)

    assert discarded == 2
    assert result["Médico"].tolist() == ["MÉDICO REAL"]


def test_reprocessing_period_replaces_existing_rows() -> None:
    may = raw_frame("2026-05-10", doctor="MAIO")
    old_june = raw_frame("2026-06-10", doctor="JUNHO ANTIGO")
    existing_raw = pd.concat([may, old_june], ignore_index=True)
    existing_treated = transform(existing_raw)
    corrected_june = raw_frame("2026-06-15", doctor="JUNHO CORRIGIDO")

    merged_raw, merged_treated, _, _, _ = merge_period(
        existing_raw,
        existing_treated,
        corrected_june,
        transform(corrected_june),
        pd.Period("2026-06", freq="M"),
    )

    assert merged_raw["Médico"].tolist() == ["MAIO", "JUNHO CORRIGIDO"]
    assert len(merged_treated) == 2
    assert set(merged_treated["Mês"]) == {"MAIO", "JUNHO"}


def test_raw_keeps_test_records_while_treated_excludes_them() -> None:
    raw_input = pd.concat(
        [
            raw_frame("2026-06-10"),
            raw_frame("2026-06-11", doctor="MÉDICO TESTE"),
        ],
        ignore_index=True,
    )
    treated_source, _ = discard_test_records(raw_input)

    merged_raw, merged_treated, _, _, _ = merge_period(
        raw_frame("2026-05-10"),
        transform(raw_frame("2026-05-10")),
        raw_input,
        transform(treated_source),
        pd.Period("2026-06", freq="M"),
    )

    assert len(merged_raw) == 3
    assert len(merged_treated) == 2
