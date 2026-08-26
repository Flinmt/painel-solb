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
from atualizador_paineis.core.shared_artifacts import publish_exams_artifact
from atualizador_paineis.excel.automation import (
    ColumnUpdate,
    TableUpdate,
    ensure_panel_is_closed,
    publish_panel,
)

LOGGER = logging.getLogger(__name__)

RAW_COLUMNS = [
    "Tipo de Exame",
    "QTD",
    "Profissional Solicitante",
    "Data de Solicitação",
    "Paciente",
    "CPF",
    "Telefone",
    "Celular",
    "Convenio",
    "Unidade",
    "Tipo",
]
TREATED_COLUMNS = [
    "Tipo de Exame",
    "QTD",
    "Profissional Solicitante",
    "Mês",
    "Unidade",
    "Convenio",
    "Tipo",
    "Ano",
]
MONTHS = MONTH_NAMES_PT_BR
CATEGORIES = {
    "imagem": "Imagem",
    "laboratorio": "Laboratorio",
    "terapia": "Terapia",
    "outros": "Outro",
}


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


def _read_input(path: Path, category: str) -> pd.DataFrame:
    if not path.exists():
        raise ValidationError(f"O arquivo selecionado não existe: {path}")
    try:
        dataframe = _normalize_headers(pd.read_excel(path, engine="openpyxl"))
    except Exception as exc:
        raise ValidationError(f"Não foi possível ler '{path.name}': {exc}") from exc
    _validate_columns(dataframe, RAW_COLUMNS[:-1], path.name)
    dataframe = dataframe[RAW_COLUMNS[:-1]].copy()
    dataframe["Tipo"] = category
    return dataframe[RAW_COLUMNS]


def _parse_dates(dataframe: pd.DataFrame, source: str) -> pd.Series:
    original = dataframe["Data de Solicitação"]
    parsed = pd.to_datetime(original, dayfirst=True, errors="coerce")
    invalid = original.notna() & parsed.isna()
    if invalid.any():
        raise ValidationError(
            f"'{source}' possui {int(invalid.sum())} data(s) de solicitação inválida(s)."
        )
    return parsed


def _validate_quantity(dataframe: pd.DataFrame, source: str) -> None:
    numeric = pd.to_numeric(dataframe["QTD"], errors="coerce")
    invalid = dataframe["QTD"].notna() & numeric.isna()
    if invalid.any():
        raise ValidationError(f"'{source}' possui valores não numéricos na coluna QTD.")


def _transform(raw_data: pd.DataFrame) -> pd.DataFrame:
    dates = pd.to_datetime(raw_data["Data de Solicitação"], dayfirst=True, errors="coerce")
    treated = raw_data[
        [
            "Tipo de Exame",
            "QTD",
            "Profissional Solicitante",
            "Unidade",
            "Convenio",
            "Tipo",
        ]
    ].copy()
    treated.insert(3, "Mês", dates.dt.month.map(MONTHS))
    treated["Ano"] = dates.dt.year.astype("Int64")
    return treated[TREATED_COLUMNS]


def _normalize_categories(series: pd.Series) -> pd.Series:
    mapping = {value.casefold(): value for value in CATEGORIES.values()}
    mapping["outros"] = "Outro"
    return series.map(
        lambda value: (
            mapping.get(str(value).strip().casefold(), value) if pd.notna(value) else value
        )
    )


def merge_period(
    existing_raw: pd.DataFrame,
    existing_treated: pd.DataFrame,
    raw_input: pd.DataFrame,
    treated_input: pd.DataFrame,
    period: pd.Period,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series, DiscardSummary]:
    """Substitui uma competência e preserva todo o restante do histórico."""
    historical_dates = pd.to_datetime(
        existing_raw["Data de Solicitação"], dayfirst=True, errors="coerce"
    )
    raw_keep = historical_dates.dt.to_period("M") != period
    month_name = MONTHS[period.month]
    treated_year = pd.to_numeric(existing_treated["Ano"], errors="coerce")
    treated_month = existing_treated["Mês"].astype("string").str.strip().str.upper()
    period_keep = ~((treated_year == period.year) & (treated_month == month_name))
    historical_keep, historical_discards = historical_professional_keep_mask(
        existing_treated,
        "Profissional Solicitante",
    )
    treated_keep = period_keep & historical_keep

    raw_history = existing_raw.loc[raw_keep].copy()
    raw_history["Tipo"] = _normalize_categories(raw_history["Tipo"])
    treated_history = existing_treated.loc[treated_keep].copy()
    treated_history["Tipo"] = _normalize_categories(treated_history["Tipo"])
    merged_raw = pd.concat([raw_history, raw_input], ignore_index=True)[RAW_COLUMNS]
    merged_treated = pd.concat([treated_history, treated_input], ignore_index=True)[TREATED_COLUMNS]
    return merged_raw, merged_treated, raw_keep, treated_keep, historical_discards


class ExamsModule:
    key = "exames"
    name = "Exames"
    description = "Atualização incremental, backup e auditoria do painel de Exames."
    input_specs = (
        InputSpec("imagem", "Imagem", "imagem.xlsx"),
        InputSpec("laboratorio", "Laboratório", "laboratorio.xlsx"),
        InputSpec("terapia", "Terapia", "terapia.xlsx"),
        InputSpec("outros", "Outros", "outros.xlsx"),
    )

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
        missing_inputs = [spec.label for spec in self.input_specs if spec.key not in request.inputs]
        if missing_inputs:
            raise ValidationError("Selecione os quatro arquivos: " + ", ".join(missing_inputs))
        if not request.panel_path.exists():
            raise ValidationError(f"O painel selecionado não existe: {request.panel_path}")
        ensure_panel_is_closed(request.panel_path)

        _progress(progress, "Lendo e validando arquivos", 10)
        input_frames: list[pd.DataFrame] = []
        periods: set[pd.Period] = set()
        for spec in self.input_specs:
            frame = _read_input(request.inputs[spec.key], CATEGORIES[spec.key])
            _validate_quantity(frame, request.inputs[spec.key].name)
            parsed_dates = _parse_dates(frame, request.inputs[spec.key].name)
            frame["Data de Solicitação"] = parsed_dates
            if not frame.empty:
                periods.update(parsed_dates.dropna().dt.to_period("M").unique().tolist())
            input_frames.append(frame)

        if not periods:
            raise ValidationError(
                "Os quatro arquivos estão vazios; não há competência para processar."
            )
        if len(periods) != 1:
            formatted = ", ".join(sorted(str(period) for period in periods))
            raise ValidationError(f"Os arquivos contêm mais de uma competência: {formatted}.")
        period = periods.pop()
        raw_input = pd.concat(input_frames, ignore_index=True)[RAW_COLUMNS]
        treated_source, discards = filter_dashboard_records(
            raw_input,
            professional_column="Profissional Solicitante",
            patient_column="Paciente",
        )
        if treated_source.empty:
            raise ValidationError(
                "Os arquivos de Exames não possuem registros válidos para o dashboard."
            )
        treated_input = _transform(treated_source)

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
        month_name = MONTHS[period.month]
        (
            merged_raw,
            merged_treated,
            raw_keep,
            treated_keep,
            historical_discards,
        ) = merge_period(
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
                column_updates=(
                    ColumnUpdate(
                        "Tipo",
                        tuple(_normalize_categories(existing_raw.loc[raw_keep, "Tipo"]).tolist()),
                    ),
                ),
            ),
            TableUpdate(
                sheet_name=self.config.treated_sheet,
                table_name=self.config.treated_table,
                rows_to_delete=tuple(
                    index for index, keep in enumerate(treated_keep.tolist()) if not keep
                ),
                remaining_row_count=int(treated_keep.sum()),
                appended_data=treated_input,
                column_updates=(
                    ColumnUpdate(
                        "Tipo",
                        tuple(
                            _normalize_categories(
                                existing_treated.loc[treated_keep, "Tipo"]
                            ).tolist()
                        ),
                    ),
                ),
            ),
        )

        output_name = self.config.output_name.format(mes=month_name, ano=period.year)
        output_path = request.panel_path.with_name(output_name)
        runtime = request.workspace / self.config.output_directory

        _progress(progress, "Arquivando a execução", 50)
        archive_path = archive_run(
            runtime / "processados" / self.key,
            period,
            {
                "exames.xlsx": raw_input,
                "exames-tratados.xlsx": treated_input,
            },
            request.inputs,
        )
        _progress(progress, "Atualizando tabelas e dashboard no Excel", 60)
        backup_path = publish_panel(
            original_path=request.panel_path,
            output_path=output_path,
            backup_dir=runtime / "backups" / self.key,
            staging_dir=runtime / ".staging",
            config=self.config,
            updates=updates,
            expected_raw_rows=len(merged_raw),
            expected_treated_rows=len(merged_treated),
        )
        _progress(progress, "Publicando consolidado para o Comparativo", 90)
        publish_exams_artifact(
            request.workspace,
            raw_input,
            period,
            request.inputs,
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
