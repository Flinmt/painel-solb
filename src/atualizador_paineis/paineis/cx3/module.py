from __future__ import annotations

import logging
import re
import shutil
import unicodedata
from pathlib import Path

import pandas as pd

from atualizador_paineis.core.audit import archive_run
from atualizador_paineis.core.config import PanelConfig, load_panel_config
from atualizador_paineis.core.dates import MONTH_NAMES_PT_BR
from atualizador_paineis.core.errors import ValidationError
from atualizador_paineis.core.models import InputSpec, ProgressCallback, RunRequest, RunResult
from atualizador_paineis.excel.automation import (
    TableUpdate,
    ensure_panel_is_closed,
    publish_panel,
    read_table_dataframe,
)

LOGGER = logging.getLogger(__name__)

TARGET_QUEUE = "8019 SOLB CALLCENTER"
CSV_COLUMNS = [
    "Queue",
    "Extension",
    "Queue Received Calls",
    "Queue Serviced Calls",
    "Extension Serviced Calls",
    "Talk Time",
    "Average Talk Time",
]
SUMMARY_COLUMNS = ["ANO", "Mês", "Recebidas", "Atendidas", "Não atendidas"]
DETAIL_COLUMNS = ["NOME", "ATENDIMENTOS", "TTA", "TMA", "MÊS", "ANO"]


def _progress(callback: ProgressCallback | None, message: str, percent: int) -> None:
    LOGGER.info("%s (%s%%)", message, percent)
    if callback:
        callback(message, percent)


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise ValidationError(f"O arquivo selecionado não existe: {path}")
    try:
        dataframe = pd.read_csv(path, encoding="utf-8-sig")
    except UnicodeDecodeError:
        try:
            dataframe = pd.read_csv(path, encoding="latin-1")
        except Exception as exc:
            raise ValidationError(f"Não foi possível ler '{path.name}': {exc}") from exc
    except Exception as exc:
        raise ValidationError(f"Não foi possível ler '{path.name}': {exc}") from exc
    if dataframe.empty:
        raise ValidationError("O arquivo da 3CX está vazio.")
    missing = [column for column in CSV_COLUMNS if column not in dataframe.columns]
    if missing:
        raise ValidationError(
            f"O arquivo '{path.name}' não possui as colunas: {', '.join(missing)}."
        )
    return dataframe


def _whole_number(value: object, label: str) -> int:
    number = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(number) or float(number) < 0 or not float(number).is_integer():
        raise ValidationError(f"O campo '{label}' deve conter um número inteiro não negativo.")
    return int(number)


def _time_to_minutes(value: object, label: str) -> float:
    if pd.isna(value) or not str(value).strip():
        return 0.0
    try:
        duration = pd.to_timedelta(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"O campo '{label}' possui um tempo inválido: {value}") from exc
    if pd.isna(duration) or duration.total_seconds() < 0:
        raise ValidationError(f"O campo '{label}' possui um tempo inválido: {value}")
    return round(duration.total_seconds() / 60, 2)


def _professional_name(value: object) -> str:
    name = re.sub(r"^\s*\d+\s+", "", str(value)).strip().upper()
    if not name:
        raise ValidationError("Foi encontrada uma extensão sem nome de profissional.")
    return name


def process_csv(
    dataframe: pd.DataFrame,
    period: pd.Period,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    queues = dataframe["Queue"].astype("string").str.strip()
    extensions = dataframe["Extension"].astype("string")
    summary_mask = queues.eq(TARGET_QUEUE) & (
        extensions.isna() | extensions.str.strip().eq("")
    )
    summaries = dataframe.loc[summary_mask]
    if len(summaries) != 1:
        raise ValidationError(
            f"Era esperada uma linha-resumo da fila '{TARGET_QUEUE}', mas foram encontradas "
            f"{len(summaries)}."
        )

    summary_source = summaries.iloc[0]
    received = _whole_number(summary_source["Queue Received Calls"], "Queue Received Calls")
    serviced = _whole_number(summary_source["Queue Serviced Calls"], "Queue Serviced Calls")
    if serviced > received:
        raise ValidationError("O total de chamadas atendidas é maior que o total recebido.")

    queue_rows = dataframe.loc[queues.eq(TARGET_QUEUE)].copy()
    calls = pd.to_numeric(queue_rows["Extension Serviced Calls"], errors="coerce")
    invalid_calls = calls.isna() | (calls < 0) | (calls.mod(1) != 0)
    if invalid_calls.any():
        raise ValidationError("Existem valores inválidos em 'Extension Serviced Calls'.")
    active = queue_rows.loc[queue_rows["Extension"].notna() & calls.gt(0)].copy()

    month_name = MONTH_NAMES_PT_BR[period.month]
    details: list[dict[str, object]] = []
    for _, row in active.iterrows():
        details.append(
            {
                "NOME": _professional_name(row["Extension"]),
                "ATENDIMENTOS": _whole_number(
                    row["Extension Serviced Calls"], "Extension Serviced Calls"
                ),
                "TTA": _time_to_minutes(row["Talk Time"], "Talk Time"),
                "TMA": _time_to_minutes(row["Average Talk Time"], "Average Talk Time"),
                "MÊS": month_name,
                "ANO": period.year,
            }
        )
    detailed = pd.DataFrame(details, columns=DETAIL_COLUMNS)
    detailed_total = int(detailed["ATENDIMENTOS"].sum()) if not detailed.empty else 0
    if detailed_total != serviced:
        raise ValidationError(
            "A soma dos atendimentos dos profissionais "
            f"({detailed_total}) não corresponde ao total atendido da fila ({serviced})."
        )
    detailed = detailed.sort_values("NOME").reset_index(drop=True)
    summary = pd.DataFrame(
        [[period.year, month_name, received, serviced, received - serviced]],
        columns=SUMMARY_COLUMNS,
    )
    return summary, detailed


def _normalized_month(value: object) -> str:
    plain = unicodedata.normalize("NFKD", str(value).strip().upper())
    return "".join(character for character in plain if not unicodedata.combining(character))


def period_keep_mask(dataframe: pd.DataFrame, period: pd.Period) -> pd.Series:
    years = pd.to_numeric(dataframe["ANO"], errors="coerce")
    month_column = "Mês" if "Mês" in dataframe.columns else "MÊS"
    months = dataframe[month_column].map(_normalized_month)
    selected_month = _normalized_month(MONTH_NAMES_PT_BR[period.month])
    return ~((years == period.year) & months.eq(selected_month))


class ThreeCXModule:
    key = "3cx"
    name = "3CX"
    description = "Atualização incremental do painel de ligações da fila SOLB Callcenter."
    requires_competence = True
    input_specs = (
        InputSpec(
            "queue_performance",
            "Relatório da 3CX",
            "queue_performance.csv",
            file_patterns=("*.csv",),
        ),
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
        if request.competence is None:
            raise ValidationError("Selecione o mês e o ano do relatório da 3CX.")
        if "queue_performance" not in request.inputs:
            raise ValidationError("Selecione o relatório CSV da 3CX.")
        if not request.panel_path.exists():
            raise ValidationError(f"O painel selecionado não existe: {request.panel_path}")
        ensure_panel_is_closed(request.panel_path)
        period = pd.Period(
            year=request.competence.year,
            month=request.competence.month,
            freq="M",
        )

        _progress(progress, "Lendo e validando o relatório da 3CX", 10)
        source = _read_csv(request.inputs["queue_performance"])
        summary_input, detailed_input = process_csv(source, period)

        _progress(progress, "Lendo o histórico do painel", 25)
        existing_summary = read_table_dataframe(
            request.panel_path, self.config.raw_sheet, self.config.raw_table
        )
        existing_detail = read_table_dataframe(
            request.panel_path, self.config.treated_sheet, self.config.treated_table
        )
        if existing_summary.columns.tolist() != SUMMARY_COLUMNS:
            raise ValidationError("A estrutura da Tabela1 do painel 3CX não é a esperada.")
        if existing_detail.columns.tolist() != DETAIL_COLUMNS:
            raise ValidationError("A estrutura da Tabela2 do painel 3CX não é a esperada.")

        _progress(progress, "Substituindo a competência no histórico", 40)
        summary_keep = period_keep_mask(existing_summary, period)
        detail_keep = period_keep_mask(existing_detail, period)
        updates = (
            TableUpdate(
                sheet_name=self.config.raw_sheet,
                table_name=self.config.raw_table,
                rows_to_delete=tuple(
                    index for index, keep in enumerate(summary_keep.tolist()) if not keep
                ),
                remaining_row_count=int(summary_keep.sum()),
                appended_data=summary_input,
            ),
            TableUpdate(
                sheet_name=self.config.treated_sheet,
                table_name=self.config.treated_table,
                rows_to_delete=tuple(
                    index for index, keep in enumerate(detail_keep.tolist()) if not keep
                ),
                remaining_row_count=int(detail_keep.sum()),
                appended_data=detailed_input,
            ),
        )
        merged_summary_rows = int(summary_keep.sum()) + len(summary_input)
        merged_detail_rows = int(detail_keep.sum()) + len(detailed_input)
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
                "resumo-mensal.xlsx": summary_input,
                "detalhado.xlsx": detailed_input,
            },
            request.inputs,
        )
        shutil.copy2(request.inputs["queue_performance"], archive_path / "queue_performance.csv")

        _progress(progress, "Atualizando tabelas e dashboard no Excel", 60)
        backup_path = publish_panel(
            original_path=request.panel_path,
            output_path=output_path,
            backup_dir=output_root / "backups" / self.key,
            staging_dir=output_root / ".staging",
            config=self.config,
            updates=updates,
            expected_raw_rows=merged_summary_rows,
            expected_treated_rows=merged_detail_rows,
        )
        _progress(progress, "Atualização concluída", 100)
        return RunResult(
            panel_path=output_path,
            backup_path=backup_path,
            archive_path=archive_path,
            period_label=f"{month_name}/{period.year}",
            raw_rows=merged_summary_rows,
            treated_rows=merged_detail_rows,
            inserted_rows=len(detailed_input),
            row_summaries=(
                ("Chamadas recebidas", int(summary_input.loc[0, "Recebidas"])),
                ("Chamadas atendidas", int(summary_input.loc[0, "Atendidas"])),
                ("Chamadas não atendidas", int(summary_input.loc[0, "Não atendidas"])),
                ("Profissionais ativos", len(detailed_input)),
            ),
        )
