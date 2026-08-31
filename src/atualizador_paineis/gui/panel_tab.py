from __future__ import annotations

import logging
import os
import queue
import threading
import tkinter as tk
import traceback
from datetime import date
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import cast

from atualizador_paineis.core.dates import MONTH_NAMES_PT_BR
from atualizador_paineis.core.errors import ApplicationError
from atualizador_paineis.core.models import Competence, PanelModule, RunRequest, RunResult
from atualizador_paineis.gui.tutorial import open_tutorial, tutorial_available

LOGGER = logging.getLogger(__name__)


class PanelTab(ttk.Frame):
    """Aba reutilizável que conecta um módulo de painel à interface."""

    def __init__(
        self,
        parent: ttk.Notebook,
        workspace: Path,
        module: PanelModule,
    ) -> None:
        super().__init__(parent, padding=20)
        self.workspace = workspace
        self.module = module
        self.panel_directory = workspace / module.panel_directory
        self.input_directory = workspace / module.input_directory
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.file_vars = {spec.key: tk.StringVar() for spec in module.input_specs}
        self.panel_var = tk.StringVar()
        self.status_var = tk.StringVar(value="Selecione os arquivos para começar.")
        self.progress_var = tk.IntVar(value=0)
        today = date.today()
        self.month_var = tk.StringVar(value=MONTH_NAMES_PT_BR[today.month])
        self.year_var = tk.StringVar(value=str(today.year))
        self.last_result: RunResult | None = None

        self._build_widgets()
        self._discover_defaults()
        self.after(100, self._consume_events)

    def _build_widgets(self) -> None:
        ttk.Label(self, text=self.module.name, style="PanelTitle.TLabel").pack(anchor="w")
        ttk.Label(
            self,
            text=self.module.description,
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(2, 16))

        panel_frame = ttk.LabelFrame(self, text="Painel", padding=12)
        panel_frame.pack(fill="x", pady=(0, 12))
        self._file_row(panel_frame, "Arquivo do painel", self.panel_var, self._select_panel)

        inputs_frame = ttk.LabelFrame(self, text="Arquivos da competência", padding=12)
        inputs_frame.pack(fill="x", pady=(0, 12))
        for spec in self.module.input_specs:
            self._file_row(
                inputs_frame,
                spec.label,
                self.file_vars[spec.key],
                lambda key=spec.key: self._select_input(key),
                selectable=spec.selectable,
            )

        if getattr(self.module, "requires_competence", False):
            period_frame = ttk.LabelFrame(self, text="Competência do arquivo", padding=12)
            period_frame.pack(fill="x", pady=(0, 12))
            ttk.Label(period_frame, text="Mês").pack(side="left")
            ttk.Combobox(
                period_frame,
                textvariable=self.month_var,
                values=tuple(MONTH_NAMES_PT_BR.values()),
                state="readonly",
                width=18,
            ).pack(side="left", padx=(8, 24))
            ttk.Label(period_frame, text="Ano").pack(side="left")
            ttk.Spinbox(
                period_frame,
                textvariable=self.year_var,
                from_=2020,
                to=2100,
                width=8,
            ).pack(side="left", padx=8)

        ttk.Progressbar(
            self,
            variable=self.progress_var,
            maximum=100,
            mode="determinate",
        ).pack(fill="x", pady=(4, 8))
        ttk.Label(self, textvariable=self.status_var, wraplength=780).pack(anchor="w")

        buttons = ttk.Frame(self)
        buttons.pack(fill="x", pady=(18, 0))
        self.process_button = ttk.Button(
            buttons,
            text="Processar e atualizar painel",
            command=self._start_processing,
            style="Primary.TButton",
        )
        self.process_button.pack(side="left")
        self.open_panel_button = ttk.Button(
            buttons,
            text="Abrir painel",
            command=self._open_panel,
            state="disabled",
        )
        self.open_panel_button.pack(side="left", padx=8)
        self.open_folder_button = ttk.Button(
            buttons,
            text="Abrir pasta",
            command=self._open_folder,
            state="disabled",
        )
        self.open_folder_button.pack(side="left")
        if tutorial_available(self.module.key):
            ttk.Button(
                buttons,
                text="Tutorial",
                command=lambda: open_tutorial(self, self.module.key),
            ).pack(side="right")

        ttk.Separator(self).pack(fill="x", pady=(20, 10))
        ttk.Label(
            self,
            text=(
                "Antes de processar, feche o painel no Excel. O aplicativo cria um backup "
                "e só publica o novo arquivo após validar a atualização."
            ),
            style="Subtitle.TLabel",
            wraplength=780,
        ).pack(anchor="w")

    @staticmethod
    def _file_row(
        parent: ttk.Widget,
        label: str,
        variable: tk.StringVar,
        command: object,
        *,
        selectable: bool = True,
    ) -> None:
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=4)
        ttk.Label(row, text=label, width=18).pack(side="left")
        entry_state = "normal" if selectable else "readonly"
        ttk.Entry(row, textvariable=variable, state=entry_state).pack(
            side="left",
            fill="x",
            expand=True,
            padx=8,
        )
        if selectable:
            ttk.Button(row, text="Selecionar…", command=command).pack(side="right")
        else:
            ttk.Label(row, text="Gerado em Exames", style="Subtitle.TLabel").pack(side="right")

    def _discover_defaults(self) -> None:
        candidates = [
            path
            for path in self.panel_directory.glob(self.module.panel_glob)
            if not path.name.startswith("~$")
        ]
        if len(candidates) == 1:
            self.panel_var.set(str(candidates[0]))

        for spec in self.module.input_specs:
            if spec.default_relative_path:
                candidate = self.workspace / spec.default_relative_path
                self.file_vars[spec.key].set(str(candidate))
                continue
            elif spec.default_filename:
                candidate = self.input_directory / spec.default_filename
            else:
                continue
            if candidate.exists():
                self.file_vars[spec.key].set(str(candidate))

    def _select_panel(self) -> None:
        selected = filedialog.askopenfilename(
            title=f"Selecione o painel de {self.module.name}",
            initialdir=self.panel_directory,
            filetypes=[("Planilhas Excel", "*.xlsx")],
        )
        if selected:
            self.panel_var.set(selected)

    def _select_input(self, key: str) -> None:
        spec = next(spec for spec in self.module.input_specs if spec.key == key)
        initial_directory = self.input_directory
        if spec.default_relative_path:
            initial_directory = (self.workspace / spec.default_relative_path).parent
        selected = filedialog.askopenfilename(
            title=f"Selecione o arquivo de {spec.label}",
            initialdir=initial_directory,
            filetypes=[("Arquivos compatíveis", " ".join(spec.file_patterns))],
        )
        if selected:
            self.file_vars[key].set(selected)

    def _start_processing(self) -> None:
        panel_text = self.panel_var.get().strip()
        input_values = {key: variable.get().strip() for key, variable in self.file_vars.items()}
        if not panel_text or any(not value for value in input_values.values()):
            messagebox.showwarning(
                "Arquivos incompletos",
                f"Selecione o painel e todos os arquivos do módulo {self.module.name}.",
                parent=self,
            )
            return

        competence = None
        if getattr(self.module, "requires_competence", False):
            month_by_name = {name: number for number, name in MONTH_NAMES_PT_BR.items()}
            try:
                competence = Competence(
                    month=month_by_name[self.month_var.get()],
                    year=int(self.year_var.get()),
                )
                if not 2020 <= competence.year <= 2100:
                    raise ValueError
            except (KeyError, ValueError):
                messagebox.showwarning(
                    "Competência inválida",
                    "Selecione um mês e informe um ano entre 2020 e 2100.",
                    parent=self,
                )
                return

        request = RunRequest(
            panel_path=Path(panel_text),
            inputs={key: Path(value) for key, value in input_values.items()},
            workspace=self.workspace,
            competence=competence,
        )
        self._set_processing_state()
        threading.Thread(
            target=self._run_module,
            args=(request,),
            daemon=True,
        ).start()

    def _set_processing_state(self) -> None:
        self.process_button.configure(state="disabled")
        self.open_panel_button.configure(state="disabled")
        self.open_folder_button.configure(state="disabled")
        self.progress_var.set(0)
        self.status_var.set("Iniciando processamento…")

    def _run_module(self, request: RunRequest) -> None:
        def progress(message: str, percent: int) -> None:
            self.events.put(("progress", (message, percent)))

        try:
            self.events.put(("success", self.module.run(request, progress)))
        except ApplicationError as exc:
            self.events.put(("error", str(exc)))
        except Exception:
            self.events.put(("unexpected", traceback.format_exc()))

    def _consume_events(self) -> None:
        try:
            while True:
                event, payload = self.events.get_nowait()
                if event == "progress":
                    message, percent = cast(tuple[str, int], payload)
                    self.status_var.set(message)
                    self.progress_var.set(percent)
                elif event == "success":
                    self._show_success(cast(RunResult, payload))
                elif event == "error":
                    self._show_error(str(payload))
                elif event == "unexpected":
                    self._show_unexpected(str(payload))
        except queue.Empty:
            pass
        self.after(100, self._consume_events)

    def _show_success(self, result: RunResult) -> None:
        self.last_result = result
        self.panel_var.set(str(result.panel_path))
        self.process_button.configure(state="normal")
        self.open_panel_button.configure(state="normal")
        self.open_folder_button.configure(state="normal")
        self.status_var.set(
            f"Concluído: {result.period_label} — {result.inserted_rows:,} registros processados."
        )
        summary_lines = [
            f"Competência: {result.period_label}",
            f"Registros recebidos: {result.inserted_rows:,}",
        ]
        if result.row_summaries:
            summary_lines.extend(
                f"{label}: {row_count:,}" for label, row_count in result.row_summaries
            )
        else:
            summary_lines.extend(
                (
                    f"Total em DADOS BRUTOS: {result.raw_rows:,}",
                    f"Total em DADOS TRATADOS: {result.treated_rows:,}",
                )
            )
        summary_lines.append(f"Backup: {result.backup_path}")
        if result.warnings:
            summary_lines.extend(("", "Avisos:", *result.warnings))
        messagebox.showinfo(
            f"{self.module.name} atualizado",
            "\n".join(summary_lines).replace(",", "."),
            parent=self,
        )

    def _show_error(self, message: str) -> None:
        self.process_button.configure(state="normal")
        self.status_var.set("A atualização não foi realizada.")
        messagebox.showerror("Não foi possível atualizar", message, parent=self)

    def _show_unexpected(self, details: str) -> None:
        self.process_button.configure(state="normal")
        self.status_var.set("Ocorreu um erro inesperado. Consulte o arquivo de log.")
        messagebox.showerror(
            "Erro inesperado",
            "O painel original não foi substituído. Consulte dados/saida/logs para detalhes.",
            parent=self,
        )
        LOGGER.error("Erro inesperado no módulo %s\n%s", self.module.key, details)

    def _open_panel(self) -> None:
        if self.last_result and self.last_result.panel_path.exists():
            os.startfile(self.last_result.panel_path)  # type: ignore[attr-defined]

    def _open_folder(self) -> None:
        if self.last_result:
            os.startfile(self.last_result.panel_path.parent)  # type: ignore[attr-defined]
