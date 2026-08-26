from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

PLACEHOLDER_PROFESSIONAL = "profissional"


@dataclass(frozen=True, slots=True)
class DiscardSummary:
    discarded_rows: int = 0
    placeholder_professionals: int = 0
    test_professionals: int = 0
    test_patients: int = 0

    def __add__(self, other: DiscardSummary) -> DiscardSummary:
        return DiscardSummary(
            discarded_rows=self.discarded_rows + other.discarded_rows,
            placeholder_professionals=(
                self.placeholder_professionals + other.placeholder_professionals
            ),
            test_professionals=self.test_professionals + other.test_professionals,
            test_patients=self.test_patients + other.test_patients,
        )


def discard_placeholder_professionals(
    dataframe: pd.DataFrame,
    column: str = "Profissional Solicitante",
) -> tuple[pd.DataFrame, int]:
    """Remove linhas cujo profissional seja apenas o marcador `Profissional`."""
    normalized = dataframe[column].astype("string").str.strip().str.casefold()
    discard_mask = normalized.eq(PLACEHOLDER_PROFESSIONAL).fillna(False)
    return dataframe.loc[~discard_mask].copy(), int(discard_mask.sum())


def filter_dashboard_records(
    dataframe: pd.DataFrame,
    professional_column: str,
    patient_column: str | None = None,
) -> tuple[pd.DataFrame, DiscardSummary]:
    """Preserva a origem e retorna apenas linhas válidas para dados tratados."""
    professionals = dataframe[professional_column].astype("string").str.strip()
    placeholder = professionals.str.casefold().eq(PLACEHOLDER_PROFESSIONAL).fillna(False)
    professional_test = professionals.str.contains("TESTE", case=False, na=False)
    patient_test = pd.Series(False, index=dataframe.index)
    if patient_column and patient_column in dataframe.columns:
        patient_test = (
            dataframe[patient_column].astype("string").str.contains("TESTE", case=False, na=False)
        )
    discard = placeholder | professional_test | patient_test
    return dataframe.loc[~discard].copy(), DiscardSummary(
        discarded_rows=int(discard.sum()),
        placeholder_professionals=int(placeholder.sum()),
        test_professionals=int(professional_test.sum()),
        test_patients=int(patient_test.sum()),
    )


def historical_professional_keep_mask(
    dataframe: pd.DataFrame,
    professional_column: str,
) -> tuple[pd.Series, DiscardSummary]:
    """Remove do tratado histórico somente marcadores diretamente identificáveis."""
    cleaned, summary = filter_dashboard_records(dataframe, professional_column)
    return pd.Series(dataframe.index.isin(cleaned.index), index=dataframe.index), summary
