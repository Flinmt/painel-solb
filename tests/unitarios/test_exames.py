from __future__ import annotations

import pandas as pd

from atualizador_paineis.paineis.exames.module import (
    MONTHS,
    RAW_COLUMNS,
    TREATED_COLUMNS,
    _normalize_categories,
    _normalize_headers,
    _transform,
    merge_period,
)


def raw_frame(date: str, category: str = "Imagem", exam: str = "EXAME") -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Tipo de Exame": exam,
                "QTD": 1,
                "Profissional Solicitante": "MÉDICO",
                "Data de Solicitação": pd.Timestamp(date),
                "Paciente": "PACIENTE",
                "CPF": "000",
                "Telefone": None,
                "Celular": None,
                "Convenio": "CONVENIO",
                "Unidade": "UNIDADE",
                "Tipo": category,
            }
        ],
        columns=RAW_COLUMNS,
    )


def test_transform_generates_expected_schema_and_period() -> None:
    result = _transform(raw_frame("2026-07-10 12:30:00"))

    assert result.columns.tolist() == TREATED_COLUMNS
    assert result.loc[0, "Mês"] == "JULHO"
    assert result.loc[0, "Ano"] == 2026


def test_normalizes_legacy_headers_and_categories() -> None:
    headers = _normalize_headers(pd.DataFrame(columns=["Data de Solicitação", "Męs"]))
    categories = _normalize_categories(
        pd.Series(["imagem", "LABORATORIO", "terapia", "outros", "Outro"])
    )

    assert headers.columns.tolist() == ["Data de Solicitação", "Mês"]
    assert categories.tolist() == ["Imagem", "Laboratorio", "Terapia", "Outro", "Outro"]


def test_reprocessing_same_period_is_idempotent() -> None:
    june = raw_frame("2026-06-10", exam="JUNHO")
    old_july = raw_frame("2026-07-10", category="imagem", exam="JULHO ANTIGO")
    existing_raw = pd.concat([june, old_july], ignore_index=True)
    existing_treated = _transform(existing_raw)
    new_july = raw_frame("2026-07-15", exam="JULHO CORRIGIDO")

    merged_raw, merged_treated, _, _, _ = merge_period(
        existing_raw,
        existing_treated,
        new_july,
        _transform(new_july),
        pd.Period("2026-07", freq="M"),
    )
    second_raw, second_treated, _, _, _ = merge_period(
        merged_raw,
        merged_treated,
        new_july,
        _transform(new_july),
        pd.Period("2026-07", freq="M"),
    )

    assert merged_raw["Tipo de Exame"].tolist() == ["JUNHO", "JULHO CORRIGIDO"]
    assert len(second_raw) == len(merged_raw) == 2
    assert len(second_treated) == len(merged_treated) == 2
    assert set(second_treated["Mês"]) == {MONTHS[6], MONTHS[7]}
    assert set(second_treated["Tipo"]) == {"Imagem"}
