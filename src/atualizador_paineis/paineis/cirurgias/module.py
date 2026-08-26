from __future__ import annotations

import logging
import unicodedata
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
    CellUpdate,
    TableUpdate,
    ensure_panel_is_closed,
    publish_panel,
    read_table_dataframe,
)

LOGGER = logging.getLogger(__name__)

RAW_COLUMNS = [
    "Profissional Solicitante",
    "Data de Solicitação",
    "Paciente",
    "CPF",
    "Telefone",
    "Celular",
    "Convenio",
    "Unidade",
]
TREATED_COLUMNS = [
    "Profissional Solicitante",
    "Unidade",
    "Convenio",
    "Mês",
    "Ano",
    "QTD",
]


def _progress(callback: ProgressCallback | None, message: str, percent: int) -> None:
    LOGGER.info("%s (%s%%)", message, percent)
    if callback:
        callback(message, percent)


def _normalize_headers(dataframe: pd.DataFrame) -> pd.DataFrame:
    rename: dict[object, str] = {}
    for column in dataframe.columns:
        normalized = str(column).strip()
        if normalized.startswith("Data de Solicita"):
            rename[column] = "Data de Solicitação"
        elif normalized in {"Męs", "MÃªs"}:
            rename[column] = "Mês"
    return dataframe.rename(columns=rename)


def _validate_columns(dataframe: pd.DataFrame, expected: list[str], source: str) -> None:
    missing = [column for column in expected if column not in dataframe.columns]
    if missing:
        raise ValidationError(f"O arquivo '{source}' não possui as colunas: {', '.join(missing)}.")


def _parse_dates(dataframe: pd.DataFrame, source: str) -> pd.Series:
    original = dataframe["Data de Solicitação"]
    parsed = pd.to_datetime(original, dayfirst=True, errors="coerce")
    invalid = original.notna() & parsed.isna()
    if invalid.any():
        raise ValidationError(
            f"'{source}' possui {int(invalid.sum())} data(s) de solicitação inválida(s)."
        )
    if parsed.isna().any():
        raise ValidationError(f"'{source}' possui datas de solicitação vazias.")
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
    dataframe["Data de Solicitação"] = _parse_dates(dataframe, path.name)
    return dataframe


def transform(raw_data: pd.DataFrame) -> pd.DataFrame:
    dates = pd.to_datetime(raw_data["Data de Solicitação"], dayfirst=True, errors="coerce")
    treated = raw_data[["Profissional Solicitante", "Unidade", "Convenio"]].copy()
    treated["Mês"] = dates.dt.month.map(MONTH_NAMES_PT_BR)
    treated["Ano"] = dates.dt.year.astype("Int64")
    treated["QTD"] = 1
    return treated[TREATED_COLUMNS]


def merge_period(
    existing_raw: pd.DataFrame,
    existing_treated: pd.DataFrame,
    raw_input: pd.DataFrame,
    treated_input: pd.DataFrame,
    period: pd.Period,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series, DiscardSummary]:
    raw_dates = pd.to_datetime(existing_raw["Data de Solicitação"], dayfirst=True, errors="coerce")
    raw_keep = raw_dates.dt.to_period("M") != period
    treated_year = pd.to_numeric(existing_treated["Ano"], errors="coerce")
    treated_month = existing_treated["Mês"].astype("string").str.strip().str.upper()
    period_keep = ~(
        (treated_year == period.year) & (treated_month == MONTH_NAMES_PT_BR[period.month])
    )
    historical_keep, historical_discards = historical_professional_keep_mask(
        existing_treated,
        "Profissional Solicitante",
    )
    treated_keep = period_keep & historical_keep
    merged_raw = pd.concat([existing_raw.loc[raw_keep], raw_input], ignore_index=True)[RAW_COLUMNS]
    merged_treated = pd.concat(
        [existing_treated.loc[treated_keep], treated_input], ignore_index=True
    )[TREATED_COLUMNS]
    return merged_raw, merged_treated, raw_keep, treated_keep, historical_discards


def auxiliary_quantity_update(
    panel_path: Path,
    config: PanelConfig,
    period: pd.Period,
    quantity: int,
) -> CellUpdate:
    settings = (
        config.auxiliary_sheet,
        config.auxiliary_table,
        config.auxiliary_month_column,
        config.auxiliary_quantity_column,
    )
    if any(value is None for value in settings):
        raise ValidationError("A tabela auxiliar de Cirurgias não está configurada.")
    auxiliary_sheet, auxiliary_table, month_column, quantity_column = settings
    auxiliary = read_table_dataframe(panel_path, auxiliary_sheet, auxiliary_table)
    normalized_columns = {
        _normalize_auxiliary_text(column): column for column in auxiliary.columns
    }
    normalized_month_column = normalized_columns.get(_normalize_auxiliary_text(month_column))
    normalized_quantity_column = normalized_columns.get(
        _normalize_auxiliary_text(quantity_column)
    )
    if normalized_month_column is None or normalized_quantity_column is None:
        raise ValidationError(
            f"A tabela auxiliar '{auxiliary_table}' não possui as colunas esperadas."
        )
    month_name = MONTH_NAMES_PT_BR[period.month]
    matches = auxiliary[normalized_month_column].map(_normalize_auxiliary_text).eq(
        _normalize_auxiliary_text(month_name)
    )
    if int(matches.sum()) != 1:
        raise ValidationError(
            f"O mês '{month_name}' não foi localizado uma única vez na tabela auxiliar."
        )
    return CellUpdate(
        sheet_name=auxiliary_sheet,
        table_name=auxiliary_table,
        row_index=int(matches.idxmax()),
        column_name=normalized_quantity_column,
        value=quantity,
    )


def _normalize_auxiliary_text(value: object) -> str:
    normalized = unicodedata.normalize("NFKD", str(value).strip())
    return "".join(character for character in normalized if not unicodedata.combining(character))


class SurgeriesModule:
    key = "cirurgias"
    name = "Cirurgias"
    description = "Atualização incremental, backup e auditoria do painel de Cirurgias."
    input_specs = (InputSpec("cirurgias", "Cirurgias", "cirurgias.xlsx"),)

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
        if "cirurgias" not in request.inputs:
            raise ValidationError("Selecione o arquivo de Cirurgias.")
        if not request.panel_path.exists():
            raise ValidationError(f"O painel selecionado não existe: {request.panel_path}")
        ensure_panel_is_closed(request.panel_path)

        _progress(progress, "Lendo e validando o arquivo", 10)
        raw_input = read_input(request.inputs["cirurgias"])
        if raw_input.empty:
            raise ValidationError("O arquivo de Cirurgias está vazio.")
        periods = raw_input["Data de Solicitação"].dt.to_period("M").unique().tolist()
        if len(periods) != 1:
            formatted = ", ".join(sorted(str(period) for period in periods))
            raise ValidationError(f"O arquivo contém mais de uma competência: {formatted}.")
        period = periods[0]
        treated_source, discards = filter_dashboard_records(
            raw_input,
            professional_column="Profissional Solicitante",
            patient_column="Paciente",
        )
        if treated_source.empty:
            raise ValidationError(
                "O arquivo de Cirurgias não possui registros válidos para o dashboard."
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
                "cirurgias.xlsx": raw_input,
                "cirurgias-tratado.xlsx": treated_input,
            },
            request.inputs,
        )
        auxiliary_update = auxiliary_quantity_update(
            request.panel_path,
            self.config,
            period,
            int(treated_input["QTD"].sum()),
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
            cell_updates=(auxiliary_update,),
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
