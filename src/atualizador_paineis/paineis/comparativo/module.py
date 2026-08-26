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
from atualizador_paineis.core.shared_artifacts import (
    EXAMS_SHARED_RELATIVE_PATH,
    validate_exams_artifact,
)
from atualizador_paineis.excel.automation import (
    TableUpdate,
    ensure_panel_is_closed,
    publish_panel,
)

LOGGER = logging.getLogger(__name__)

OUTPUT_COLUMNS = ["Profissional", "Mês", "Consultas", "Exames", "Cirurgias", "Ano"]
APPOINTMENT_COLUMNS = ["Tipo", "Médico", "Paciente", "Data"]
EXAM_COLUMNS = [
    "Tipo de Exame",
    "QTD",
    "Profissional Solicitante",
    "Data de Solicitação",
    "Paciente",
    "Tipo",
]
SURGERY_COLUMNS = ["Profissional Solicitante", "Data de Solicitação", "Paciente"]


def _progress(callback: ProgressCallback | None, message: str, percent: int) -> None:
    LOGGER.info("%s (%s%%)", message, percent)
    if callback:
        callback(message, percent)


def _header_key(value: object) -> str:
    normalized = unicodedata.normalize("NFKD", str(value).strip())
    return "".join(
        character for character in normalized if not unicodedata.combining(character)
    ).casefold()


def _normalize_headers(dataframe: pd.DataFrame) -> pd.DataFrame:
    canonical = {
        "tipo": "Tipo",
        "medico": "Médico",
        "data": "Data",
        "tipo de exame": "Tipo de Exame",
        "qtd": "QTD",
        "profissional solicitante": "Profissional Solicitante",
        "data de solicitacao": "Data de Solicitação",
        "profissional": "Profissional",
        "mes": "Mês",
        "consultas": "Consultas",
        "exames": "Exames",
        "cirurgias": "Cirurgias",
        "ano": "Ano",
    }
    return dataframe.rename(
        columns={
            column: canonical.get(_header_key(column), str(column).strip()) for column in dataframe
        }
    )


def _validate_columns(dataframe: pd.DataFrame, expected: list[str], source: str) -> None:
    missing = [column for column in expected if column not in dataframe.columns]
    if missing:
        raise ValidationError(f"O arquivo '{source}' não possui as colunas: {', '.join(missing)}.")


def _read_input(path: Path, expected: list[str]) -> pd.DataFrame:
    if not path.exists():
        raise ValidationError(f"O arquivo selecionado não existe: {path}")
    try:
        dataframe = _normalize_headers(pd.read_excel(path, engine="openpyxl"))
    except Exception as exc:
        raise ValidationError(f"Não foi possível ler '{path.name}': {exc}") from exc
    _validate_columns(dataframe, expected, path.name)
    return dataframe.copy()


def _parse_dates(values: pd.Series, source: str) -> pd.Series:
    parsed = pd.to_datetime(values, dayfirst=True, errors="coerce", format="mixed")
    invalid = values.notna() & parsed.isna()
    if invalid.any():
        raise ValidationError(f"'{source}' possui {int(invalid.sum())} data(s) inválida(s).")
    if parsed.isna().any():
        raise ValidationError(f"'{source}' possui data(s) vazia(s).")
    return parsed


def _professional_values(values: pd.Series) -> pd.Series:
    return values.astype("string").str.strip().str.upper()


def transform_appointments(dataframe: pd.DataFrame) -> pd.DataFrame:
    dates = _parse_dates(dataframe["Data"], "Atendimentos")
    professionals = _professional_values(dataframe["Médico"])
    types = dataframe["Tipo"].astype("string").str.upper()
    appointment_mask = types.str.contains("CONSULTA", na=False) | types.str.contains(
        "RETORNO", na=False
    )
    selected = pd.DataFrame(
        {
            "Profissional": professionals,
            "Mês": dates.dt.month.map(MONTH_NAMES_PT_BR),
            "Ano": dates.dt.year.astype("Int64"),
        }
    ).loc[appointment_mask]
    grouped = (
        selected.dropna(subset=["Profissional"])
        .groupby(["Profissional", "Mês", "Ano"], as_index=False)
        .size()
        .rename(columns={"size": "Consultas"})
    )
    return grouped


def transform_exams(dataframe: pd.DataFrame) -> pd.DataFrame:
    dates = _parse_dates(dataframe["Data de Solicitação"], "Exames")
    quantity = pd.to_numeric(dataframe["QTD"], errors="coerce")
    invalid_quantity = dataframe["QTD"].notna() & quantity.isna()
    if invalid_quantity.any():
        raise ValidationError("O arquivo de Exames possui valores não numéricos na coluna QTD.")
    rm_mask = dataframe["Tipo de Exame"].astype("string").str.upper().str.startswith("RM", na=False)
    selected = pd.DataFrame(
        {
            "Profissional": _professional_values(dataframe["Profissional Solicitante"]),
            "Mês": dates.dt.month.map(MONTH_NAMES_PT_BR),
            "Ano": dates.dt.year.astype("Int64"),
            "Exames": quantity.fillna(0),
        }
    ).loc[rm_mask]
    return (
        selected.dropna(subset=["Profissional"])
        .groupby(["Profissional", "Mês", "Ano"], as_index=False)["Exames"]
        .sum()
    )


def transform_surgeries(dataframe: pd.DataFrame) -> pd.DataFrame:
    dates = _parse_dates(dataframe["Data de Solicitação"], "Cirurgias")
    selected = pd.DataFrame(
        {
            "Profissional": _professional_values(dataframe["Profissional Solicitante"]),
            "Mês": dates.dt.month.map(MONTH_NAMES_PT_BR),
            "Ano": dates.dt.year.astype("Int64"),
        }
    )
    return (
        selected.dropna(subset=["Profissional"])
        .groupby(["Profissional", "Mês", "Ano"], as_index=False)
        .size()
        .rename(columns={"size": "Cirurgias"})
    )


def build_comparison(
    appointments: pd.DataFrame,
    exams: pd.DataFrame,
    surgeries: pd.DataFrame,
) -> tuple[pd.DataFrame, DiscardSummary]:
    appointments, appointment_discards = filter_dashboard_records(
        appointments,
        professional_column="Médico",
        patient_column="Paciente",
    )
    exams, exam_discards = filter_dashboard_records(
        exams,
        professional_column="Profissional Solicitante",
        patient_column="Paciente",
    )
    surgeries, surgery_discards = filter_dashboard_records(
        surgeries,
        professional_column="Profissional Solicitante",
        patient_column="Paciente",
    )
    appointment_data = transform_appointments(appointments)
    exam_data = transform_exams(exams)
    surgery_data = transform_surgeries(surgeries)
    keys = ["Profissional", "Mês", "Ano"]
    merged = appointment_data.merge(surgery_data, on=keys, how="outer")
    merged = merged.merge(exam_data, on=keys, how="outer")
    for column in ["Consultas", "Exames", "Cirurgias"]:
        merged[column] = pd.to_numeric(merged[column], errors="coerce").fillna(0).astype(int)
    return (
        merged[OUTPUT_COLUMNS],
        appointment_discards + exam_discards + surgery_discards,
    )


def merge_period(
    existing: pd.DataFrame,
    comparison_input: pd.DataFrame,
    period: pd.Period,
) -> tuple[pd.DataFrame, pd.Series, DiscardSummary]:
    years = pd.to_numeric(existing["Ano"], errors="coerce")
    months = existing["Mês"].astype("string").str.strip().str.upper()
    period_keep = ~((years == period.year) & (months == MONTH_NAMES_PT_BR[period.month]))
    historical_keep, historical_discards = historical_professional_keep_mask(
        existing,
        "Profissional",
    )
    keep = period_keep & historical_keep
    merged = pd.concat([existing.loc[keep], comparison_input], ignore_index=True)[OUTPUT_COLUMNS]
    return merged, keep, historical_discards


class ComparisonModule:
    key = "comparativo"
    name = "Comparativo"
    description = "Consolida consultas, ressonâncias e cirurgias no Painel Comparativo."
    input_specs = (
        InputSpec("atendimentos", "Atendimentos", "atendimentos.xlsx"),
        InputSpec(
            "exames",
            "Exames consolidados",
            default_relative_path=EXAMS_SHARED_RELATIVE_PATH,
        ),
        InputSpec("cirurgias", "Cirurgias", "cirurgias.xlsx"),
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
        missing = [spec.label for spec in self.input_specs if spec.key not in request.inputs]
        if missing:
            raise ValidationError("Selecione os três arquivos: " + ", ".join(missing))
        if not request.panel_path.exists():
            raise ValidationError(f"O painel selecionado não existe: {request.panel_path}")
        ensure_panel_is_closed(request.panel_path)
        if not request.inputs["exames"].exists():
            raise ValidationError(
                "O consolidado de Exames não foi encontrado. Atualize primeiro a aba Exames."
            )

        _progress(progress, "Lendo e validando os três arquivos", 10)
        appointments = _read_input(request.inputs["atendimentos"], APPOINTMENT_COLUMNS)
        exams = _read_input(request.inputs["exames"], EXAM_COLUMNS)
        surgeries = _read_input(request.inputs["cirurgias"], SURGERY_COLUMNS)

        sources = (
            (appointments, "Data", request.inputs["atendimentos"].name),
            (exams, "Data de Solicitação", request.inputs["exames"].name),
            (surgeries, "Data de Solicitação", request.inputs["cirurgias"].name),
        )
        periods: set[pd.Period] = set()
        for frame, date_column, source_name in sources:
            if frame.empty:
                raise ValidationError(f"'{source_name}' não possui registros válidos.")
            parsed_dates = _parse_dates(frame[date_column], source_name)
            frame[date_column] = parsed_dates
            periods.update(parsed_dates.dt.to_period("M").unique().tolist())
        if len(periods) != 1:
            formatted = ", ".join(sorted(str(period) for period in periods))
            raise ValidationError(f"Os arquivos não possuem a mesma competência: {formatted}.")
        period = periods.pop()
        validate_exams_artifact(request.inputs["exames"], period)

        comparison_input, discards = build_comparison(appointments, exams, surgeries)
        if comparison_input.empty:
            raise ValidationError("Os arquivos não produziram registros para o comparativo.")

        _progress(progress, "Lendo o histórico do Painel Comparativo", 25)
        try:
            existing = _normalize_headers(
                pd.read_excel(
                    request.panel_path,
                    sheet_name=self.config.treated_sheet,
                    engine="openpyxl",
                )
            )
        except Exception as exc:
            raise ValidationError(f"Não foi possível ler o histórico do painel: {exc}") from exc
        _validate_columns(existing, OUTPUT_COLUMNS, self.config.treated_sheet)
        existing = existing[OUTPUT_COLUMNS].copy()

        _progress(progress, "Substituindo a competência consolidada", 40)
        merged, keep, historical_discards = merge_period(existing, comparison_input, period)
        updates = (
            TableUpdate(
                sheet_name=self.config.treated_sheet,
                table_name=self.config.treated_table,
                rows_to_delete=tuple(
                    index for index, value in enumerate(keep.tolist()) if not value
                ),
                remaining_row_count=int(keep.sum()),
                appended_data=comparison_input,
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
            {"comparativo-tratado.xlsx": comparison_input},
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
            expected_raw_rows=len(merged),
            expected_treated_rows=len(merged),
        )
        _progress(progress, "Atualização concluída", 100)

        warnings: list[str] = []
        if discards.discarded_rows:
            warnings.append(
                f"{discards.discarded_rows} registro(s) de profissional, médico ou paciente "
                "inválido foram desconsiderados."
            )
        if historical_discards.discarded_rows:
            warnings.append(
                f"{historical_discards.discarded_rows} linha(s) histórica(s) de profissional "
                "de teste ou marcador foram removidas da aba TRATADO."
            )
        return RunResult(
            panel_path=output_path,
            backup_path=backup_path,
            archive_path=archive_path,
            period_label=f"{month_name}/{period.year}",
            raw_rows=len(merged),
            treated_rows=len(merged),
            inserted_rows=len(comparison_input),
            warnings=tuple(warnings),
            row_summaries=(("Total na aba TRATADO", len(merged)),),
        )
