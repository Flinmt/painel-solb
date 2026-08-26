from __future__ import annotations

import logging
import shutil
import unicodedata
from pathlib import Path

import pandas as pd

from atualizador_paineis.core.audit import archive_run
from atualizador_paineis.core.config import PanelConfig, load_panel_config
from atualizador_paineis.core.data_cleaning import filter_dashboard_records
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

INPUT_COLUMNS = ["Usuario", "Quantidade", "%"]
OUTPUT_COLUMNS = ["category", "Titulo", "Mês", "Ano"]


def _progress(callback: ProgressCallback | None, message: str, percent: int) -> None:
    LOGGER.info("%s (%s%%)", message, percent)
    if callback:
        callback(message, percent)


def _parse_percentages(values: pd.Series) -> pd.Series:
    normalized = (
        values.astype("string")
        .str.strip()
        .str.removesuffix("%")
        .str.replace(",", ".", regex=False)
    )
    percentages = pd.to_numeric(normalized, errors="coerce")
    if percentages.isna().any() or (percentages < 0).any():
        raise ValidationError("A coluna '%' possui valores vazios ou inválidos.")
    if percentages.sum() <= 1.01:
        percentages *= 100
    return percentages


def read_input(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise ValidationError(f"O arquivo selecionado não existe: {path}")
    try:
        dataframe = pd.read_excel(path, engine="openpyxl")
    except Exception as exc:
        raise ValidationError(f"Não foi possível ler '{path.name}': {exc}") from exc
    dataframe.columns = [str(column).strip() for column in dataframe.columns]
    missing = [column for column in INPUT_COLUMNS if column not in dataframe.columns]
    if missing:
        raise ValidationError(
            f"O arquivo '{path.name}' não possui as colunas: {', '.join(missing)}."
        )
    dataframe = dataframe[INPUT_COLUMNS].copy()
    if dataframe.empty:
        raise ValidationError("O arquivo da Agenda está vazio.")

    users = dataframe["Usuario"].astype("string").str.strip()
    if users.isna().any() or users.eq("").any():
        raise ValidationError("A coluna 'Usuario' possui valores vazios.")
    normalized_users = users.str.casefold()
    duplicates = normalized_users.duplicated(keep=False)
    if duplicates.any():
        names = ", ".join(sorted(users.loc[duplicates].unique().tolist()))
        raise ValidationError(f"Existem usuários duplicados no arquivo: {names}.")

    quantities = pd.to_numeric(dataframe["Quantidade"], errors="coerce")
    invalid_quantities = quantities.isna() | quantities.lt(0) | quantities.mod(1).ne(0)
    if invalid_quantities.any():
        raise ValidationError("A coluna 'Quantidade' deve conter inteiros não negativos.")
    total = int(quantities.sum())
    if total <= 0:
        raise ValidationError("O total de agendamentos deve ser maior que zero.")

    percentages = _parse_percentages(dataframe["%"])
    if abs(float(percentages.sum()) - 100) > 0.1:
        raise ValidationError("Os percentuais da Agenda não totalizam 100%.")
    expected = quantities / total * 100
    if percentages.sub(expected).abs().gt(0.011).any():
        raise ValidationError("Os percentuais não correspondem às quantidades informadas.")

    dataframe["Usuario"] = users
    dataframe["Quantidade"] = quantities.astype("int64")
    dataframe["%"] = percentages
    return dataframe


def transform(dataframe: pd.DataFrame, period: pd.Period) -> pd.DataFrame:
    output = dataframe[["Usuario", "Quantidade"]].rename(
        columns={"Usuario": "category", "Quantidade": "Titulo"}
    )
    output["Mês"] = MONTH_NAMES_PT_BR[period.month]
    output["Ano"] = period.year
    return output[OUTPUT_COLUMNS]


def _normalized_month(value: object) -> str:
    plain = unicodedata.normalize("NFKD", str(value).strip().upper())
    return "".join(character for character in plain if not unicodedata.combining(character))


def period_keep_mask(dataframe: pd.DataFrame, period: pd.Period) -> pd.Series:
    years = pd.to_numeric(dataframe["Ano"], errors="coerce")
    months = dataframe["Mês"].map(_normalized_month)
    selected_month = _normalized_month(MONTH_NAMES_PT_BR[period.month])
    return ~((years == period.year) & months.eq(selected_month))


class ScheduleModule:
    key = "agenda"
    name = "Agenda"
    description = "Atualização incremental do painel de agendamentos por usuário."
    requires_competence = True
    input_specs = (InputSpec("agenda", "Agenda", "agenda.xlsx"),)

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
            raise ValidationError("Selecione o mês e o ano do arquivo da Agenda.")
        if "agenda" not in request.inputs:
            raise ValidationError("Selecione o arquivo da Agenda.")
        if not request.panel_path.exists():
            raise ValidationError(f"O painel selecionado não existe: {request.panel_path}")
        ensure_panel_is_closed(request.panel_path)
        period = pd.Period(
            year=request.competence.year,
            month=request.competence.month,
            freq="M",
        )

        _progress(progress, "Lendo e validando o arquivo da Agenda", 10)
        raw_input = read_input(request.inputs["agenda"])
        treated_source, discards = filter_dashboard_records(raw_input, "Usuario")
        if treated_source.empty:
            raise ValidationError("O arquivo não possui usuários válidos para o dashboard.")
        treated_input = transform(treated_source, period)

        _progress(progress, "Lendo o histórico do painel", 25)
        existing = read_table_dataframe(
            request.panel_path,
            self.config.treated_sheet,
            self.config.treated_table,
        )
        if existing.columns.tolist() != OUTPUT_COLUMNS:
            raise ValidationError("A estrutura da tabela histórica da Agenda não é a esperada.")

        _progress(progress, "Substituindo a competência no histórico", 40)
        keep = period_keep_mask(existing, period)
        merged_rows = int(keep.sum()) + len(treated_input)
        updates = (
            TableUpdate(
                sheet_name=self.config.treated_sheet,
                table_name=self.config.treated_table,
                rows_to_delete=tuple(
                    index for index, should_keep in enumerate(keep.tolist()) if not should_keep
                ),
                remaining_row_count=int(keep.sum()),
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
            {"agenda-tratado.xlsx": treated_input},
            request.inputs,
        )
        shutil.copy2(request.inputs["agenda"], archive_path / "agenda.xlsx")

        _progress(progress, "Atualizando tabela e dashboard no Excel", 60)
        backup_path = publish_panel(
            original_path=request.panel_path,
            output_path=output_path,
            backup_dir=output_root / "backups" / self.key,
            staging_dir=output_root / ".staging",
            config=self.config,
            updates=updates,
            expected_raw_rows=merged_rows,
            expected_treated_rows=merged_rows,
        )
        _progress(progress, "Atualização concluída", 100)

        warnings: list[str] = []
        if discards.discarded_rows:
            warnings.append(
                f"{discards.discarded_rows} usuário(s) de teste ou marcador foram "
                "desconsiderados no dashboard."
            )
        return RunResult(
            panel_path=output_path,
            backup_path=backup_path,
            archive_path=archive_path,
            period_label=f"{month_name}/{period.year}",
            raw_rows=len(raw_input),
            treated_rows=merged_rows,
            inserted_rows=len(treated_input),
            warnings=tuple(warnings),
            row_summaries=(
                ("Usuários processados", len(treated_input)),
                ("Agendamentos", int(treated_input["Titulo"].sum())),
            ),
        )
