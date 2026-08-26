from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from atualizador_paineis.core.audit import archive_run
from atualizador_paineis.core.config import PanelConfig, load_panel_config
from atualizador_paineis.core.data_cleaning import (
    DiscardSummary,
    filter_dashboard_records,
    historical_professional_keep_mask,
)
from atualizador_paineis.core.dates import MONTH_NAMES_PT_BR
from atualizador_paineis.core.errors import ValidationError
from atualizador_paineis.core.models import (
    InputSpec,
    ProgressCallback,
    RunRequest,
    RunResult,
)
from atualizador_paineis.excel.automation import (
    TableUpdate,
    ensure_panel_is_closed,
    publish_panel,
)

LOGGER = logging.getLogger(__name__)

RAW_COLUMNS = [
    "Convênio",
    "Código",
    "Tipo",
    "Médico",
    "Paciente",
    "CPF",
    "Total",
    "Data",
    "Unidade",
]
TREATED_COLUMNS = [
    "Convênio",
    "Tipo",
    "Médico",
    "Unidade",
    "Mês",
    "Ano",
    "Quantidade",
]


def _progress(callback: ProgressCallback | None, message: str, percent: int) -> None:
    LOGGER.info("%s (%s%%)", message, percent)
    if callback:
        callback(message, percent)


def _normalize_headers(dataframe: pd.DataFrame) -> pd.DataFrame:
    canonical = {
        "convenio": "Convênio",
        "codigo": "Código",
        "medico": "Médico",
        "mes": "Mês",
    }
    rename: dict[object, str] = {}
    for column in dataframe.columns:
        stripped = str(column).strip()
        normalized = stripped.casefold().replace("ê", "e").replace("é", "e").replace("ó", "o")
        rename[column] = canonical.get(normalized, stripped)
    return dataframe.rename(columns=rename)


def _validate_columns(dataframe: pd.DataFrame, expected: list[str], source: str) -> None:
    missing = [column for column in expected if column not in dataframe.columns]
    if missing:
        raise ValidationError(f"O arquivo '{source}' não possui as colunas: {', '.join(missing)}.")


def _parse_dates(values: pd.Series, source: str, allow_invalid: bool = False) -> pd.Series:
    parsed = pd.to_datetime(values, dayfirst=True, errors="coerce", format="mixed")
    invalid = values.notna() & parsed.isna()
    if invalid.any() and not allow_invalid:
        raise ValidationError(f"'{source}' possui {int(invalid.sum())} data(s) inválida(s).")
    if parsed.isna().any() and not allow_invalid:
        raise ValidationError(f"'{source}' possui data(s) vazia(s).")
    return parsed


def read_input(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise ValidationError(f"O arquivo selecionado não existe: {path}")
    try:
        dataframe = _normalize_headers(pd.read_excel(path, engine="openpyxl"))
    except Exception as exc:
        raise ValidationError(f"Não foi possível ler '{path.name}': {exc}") from exc
    _validate_columns(dataframe, RAW_COLUMNS, path.name)
    dataframe = dataframe[RAW_COLUMNS].copy()
    dataframe["Data"] = _parse_dates(dataframe["Data"], path.name)
    return dataframe


def discard_test_records(dataframe: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    doctors = dataframe["Médico"].astype("string")
    patients = dataframe["Paciente"].astype("string")
    discard_mask = doctors.str.contains("TESTE", case=False, na=False) | patients.str.contains(
        "TESTE", case=False, na=False
    )
    return dataframe.loc[~discard_mask].copy(), int(discard_mask.sum())


def transform(raw_data: pd.DataFrame) -> pd.DataFrame:
    dates = pd.to_datetime(raw_data["Data"], dayfirst=True, errors="coerce", format="mixed")
    treated = raw_data[["Convênio", "Tipo", "Médico", "Unidade"]].copy()
    treated["Mês"] = dates.dt.month.map(MONTH_NAMES_PT_BR)
    treated["Ano"] = dates.dt.year.astype("Int64")
    treated["Quantidade"] = 1
    return treated[TREATED_COLUMNS]


def merge_period(
    existing_raw: pd.DataFrame,
    existing_treated: pd.DataFrame,
    raw_input: pd.DataFrame,
    treated_input: pd.DataFrame,
    period: pd.Period,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series, DiscardSummary]:
    historical_dates = _parse_dates(
        existing_raw["Data"],
        "histórico de DADOS BRUTOS",
        allow_invalid=True,
    )
    raw_keep = historical_dates.dt.to_period("M") != period
    treated_year = pd.to_numeric(existing_treated["Ano"], errors="coerce")
    treated_month = existing_treated["Mês"].astype("string").str.strip().str.upper()
    period_keep = ~(
        (treated_year == period.year) & (treated_month == MONTH_NAMES_PT_BR[period.month])
    )
    historical_keep, historical_discards = historical_professional_keep_mask(
        existing_treated,
        "Médico",
    )
    treated_keep = period_keep & historical_keep
    merged_raw = pd.concat([existing_raw.loc[raw_keep], raw_input], ignore_index=True)[RAW_COLUMNS]
    merged_treated = pd.concat(
        [existing_treated.loc[treated_keep], treated_input],
        ignore_index=True,
    )[TREATED_COLUMNS]
    return merged_raw, merged_treated, raw_keep, treated_keep, historical_discards


class AppointmentsModule:
    key = "atendimentos"
    name = "Atendimentos"
    description = "Atualização incremental, backup e auditoria do painel de Atendimentos."
    input_specs = (InputSpec("atendimentos", "Atendimentos", "atendimentos.xlsx"),)

    def __init__(self, config: PanelConfig | None = None) -> None:
        self.config = config or load_panel_config(self.key)
        self.panel_directory = self.config.panel_directory
        self.input_directory = self.config.input_directory
        self.panel_glob = self.config.panel_glob

    def run(
        self,
        request: RunRequest,
        progress: ProgressCallback | None = None,
    ) -> RunResult:
        if "atendimentos" not in request.inputs:
            raise ValidationError("Selecione o arquivo de Atendimentos.")
        if not request.panel_path.exists():
            raise ValidationError(f"O painel selecionado não existe: {request.panel_path}")
        ensure_panel_is_closed(request.panel_path)

        _progress(progress, "Lendo e validando o arquivo", 10)
        raw_input = read_input(request.inputs["atendimentos"])
        if raw_input.empty:
            raise ValidationError("O arquivo de Atendimentos está vazio.")
        periods = raw_input["Data"].dt.to_period("M").unique().tolist()
        if len(periods) != 1:
            formatted = ", ".join(sorted(str(period) for period in periods))
            raise ValidationError(f"O arquivo contém mais de uma competência: {formatted}.")
        period = periods[0]
        treated_source, discards = filter_dashboard_records(
            raw_input,
            professional_column="Médico",
            patient_column="Paciente",
        )
        if treated_source.empty:
            raise ValidationError(
                "O arquivo de Atendimentos não possui registros válidos para o dashboard."
            )
        treated_input = transform(treated_source)

        _progress(progress, "Lendo o histórico do painel", 25)
        try:
            existing_raw = _normalize_headers(
                pd.read_excel(
                    request.panel_path,
                    sheet_name=self.config.raw_sheet,
                    engine="openpyxl",
                )
            )
            existing_treated = _normalize_headers(
                pd.read_excel(
                    request.panel_path,
                    sheet_name=self.config.treated_sheet,
                    engine="openpyxl",
                )
            )
        except Exception as exc:
            raise ValidationError(f"Não foi possível ler o histórico do painel: {exc}") from exc
        _validate_columns(existing_raw, RAW_COLUMNS, self.config.raw_sheet)
        _validate_columns(existing_treated, TREATED_COLUMNS, self.config.treated_sheet)
        existing_raw = existing_raw[RAW_COLUMNS].copy()
        existing_treated = existing_treated[TREATED_COLUMNS].copy()

        _progress(progress, "Substituindo a competência no histórico", 40)
        merged_raw, merged_treated, raw_keep, treated_keep, historical_discards = merge_period(
            existing_raw,
            existing_treated,
            raw_input,
            treated_input,
            period,
        )
        updates = (
            TableUpdate(
                sheet_name=self.config.raw_sheet,
                table_name=self.config.raw_table,
                rows_to_delete=tuple(
                    index for index, keep in enumerate(raw_keep.tolist()) if not keep
                ),
                remaining_row_count=int(raw_keep.sum()),
                appended_data=raw_input,
            ),
            TableUpdate(
                sheet_name=self.config.treated_sheet,
                table_name=self.config.treated_table,
                rows_to_delete=tuple(
                    index for index, keep in enumerate(treated_keep.tolist()) if not keep
                ),
                remaining_row_count=int(treated_keep.sum()),
                appended_data=treated_input,
            ),
        )

        month_name = MONTH_NAMES_PT_BR[period.month]
        output_path = request.panel_path.with_name(
            self.config.output_name.format(mes=month_name, ano=period.year)
        )
        output_root = request.workspace / self.config.output_directory

        _progress(progress, "Arquivando a execução", 50)
        archive_path = archive_run(
            output_root / "processados" / self.key,
            period,
            {
                "atendimentos.xlsx": raw_input,
                "atendimentos-tratado.xlsx": treated_input,
            },
            request.inputs,
        )
        _progress(progress, "Atualizando tabelas e dashboard no Excel", 60)
        backup_path = publish_panel(
            original_path=request.panel_path,
            output_path=output_path,
            backup_dir=output_root / "backups" / self.key,
            staging_dir=output_root / ".staging",
            config=self.config,
            updates=updates,
            expected_raw_rows=len(merged_raw),
            expected_treated_rows=len(merged_treated),
        )
        _progress(progress, "Atualização concluída", 100)

        warnings: list[str] = []
        if discards.discarded_rows:
            warnings.append(
                f"{discards.discarded_rows} registro(s) inválido(s) foram mantidos em "
                "DADOS BRUTOS e desconsiderados em DADOS TRATADOS."
            )
        if historical_discards.discarded_rows:
            warnings.append(
                f"{historical_discards.discarded_rows} registro(s) históricos de profissional "
                "de teste ou marcador foram removidos de DADOS TRATADOS."
            )
        return RunResult(
            panel_path=output_path,
            backup_path=backup_path,
            archive_path=archive_path,
            period_label=f"{month_name}/{period.year}",
            raw_rows=len(merged_raw),
            treated_rows=len(merged_treated),
            inserted_rows=len(raw_input),
            warnings=tuple(warnings),
        )
