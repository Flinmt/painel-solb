from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import messagebox, ttk

from PIL import Image, ImageTk

from atualizador_paineis.core.config import project_root

TUTORIAL_GEOMETRY = "900x620"
TUTORIAL_MIN_SIZE = (700, 500)


@dataclass(frozen=True, slots=True)
class TutorialStep:
    image_name: str
    title: str
    instructions: str


@dataclass(frozen=True, slots=True)
class TutorialDefinition:
    title: str
    subtitle: str
    directory: Path
    steps: tuple[TutorialStep, ...]


TUTORIALS = {
    "agenda": TutorialDefinition(
        title="Tutorial da Agenda",
        subtitle="Siga as duas etapas abaixo para atualizar o painel da Agenda.",
        directory=Path("assets") / "tutorials" / "agenda",
        steps=(
            TutorialStep(
                image_name="01-biodata-agendamentos.png",
                title="1. Obter os dados no BIODATA",
                instructions=(
                    "Abra Atendimento > Agendamentos. Informe a mesma data inicial e final "
                    "para consultar o dia desejado, confira a tabela Usuário Registro e "
                    "exporte os dados."
                ),
            ),
            TutorialStep(
                image_name="02-atualizador-agenda.png",
                title="2. Atualizar o painel",
                instructions=(
                    "Na aba Agenda, selecione o arquivo exportado. Depois escolha o mês e o "
                    "ano correspondentes aos dados e clique em Processar e atualizar painel."
                ),
            ),
        ),
    ),
    "exames": TutorialDefinition(
        title="Tutorial de Exames",
        subtitle="Siga as cinco etapas abaixo para exportar e processar os exames.",
        directory=Path("assets") / "tutorials" / "exames",
        steps=(
            TutorialStep(
                image_name="01-exames-solicitados.png",
                title="1. Acessar Exames Solicitados",
                instructions="No BIODATA, abra Exame > Exames Solicitados.",
            ),
            TutorialStep(
                image_name="02-abrir-filtros.png",
                title="2. Abrir os filtros",
                instructions="Clique no ícone de pesquisa destacado acima da tabela.",
            ),
            TutorialStep(
                image_name="03-preencher-filtros.png",
                title="3. Preencher os filtros",
                instructions=(
                    "Informe a data inicial, a data final e o tipo de exame. Não utilize "
                    "acentos nos campos de pesquisa."
                ),
            ),
            TutorialStep(
                image_name="04-exportar-resultados.png",
                title="4. Exportar os resultados",
                instructions="Após filtrar os registros, clique no ícone de exportação destacado.",
            ),
            TutorialStep(
                image_name="05-selecionar-arquivos.png",
                title="5. Atualizar o painel",
                instructions=(
                    "Na aba Exames, selecione os arquivos de Imagem, Laboratório, Terapia e "
                    "Outros. Depois clique em Processar e atualizar painel."
                ),
            ),
        ),
    ),
}


class TutorialWindow(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Widget,
        definition: TutorialDefinition,
        image_directory: Path,
    ) -> None:
        super().__init__(parent)
        self.title(definition.title)
        self.geometry(TUTORIAL_GEOMETRY)
        self.minsize(*TUTORIAL_MIN_SIZE)
        self.transient(parent.winfo_toplevel())

        container = ttk.Frame(self, padding=14)
        container.pack(fill="both", expand=True)
        ttk.Label(
            container,
            text=definition.title,
            font=("Segoe UI", 16, "bold"),
        ).pack(anchor="w")
        ttk.Label(container, text=definition.subtitle).pack(anchor="w", pady=(2, 10))

        notebook = ttk.Notebook(container)
        notebook.pack(fill="both", expand=True)
        for step in definition.steps:
            self._add_step(notebook, image_directory / step.image_name, step)

        ttk.Button(container, text="Fechar", command=self.destroy).pack(anchor="e", pady=(10, 0))
        self.after_idle(self._center_on_parent)

    def _add_step(
        self,
        notebook: ttk.Notebook,
        image_path: Path,
        step: TutorialStep,
    ) -> None:
        page = ttk.Frame(notebook, padding=10)
        notebook.add(page, text=step.title)
        ttk.Label(page, text=step.instructions, wraplength=820).pack(
            anchor="w",
            pady=(0, 8),
        )
        ResponsiveImage(page, image_path).pack(fill="both", expand=True)

    def _center_on_parent(self) -> None:
        self.update_idletasks()
        parent = self.master.winfo_toplevel()
        x = parent.winfo_rootx() + max((parent.winfo_width() - self.winfo_width()) // 2, 0)
        y = parent.winfo_rooty() + max((parent.winfo_height() - self.winfo_height()) // 2, 0)
        self.geometry(f"+{x}+{y}")


class ResponsiveImage(ttk.Frame):
    def __init__(self, parent: tk.Widget, image_path: Path) -> None:
        super().__init__(parent)
        with Image.open(image_path) as source:
            self.source_image = source.convert("RGB")
        self.photo: ImageTk.PhotoImage | None = None
        self.resize_job: str | None = None

        self.image_label = ttk.Label(self, anchor="center")
        self.image_label.pack(fill="both", expand=True)
        self.bind("<Configure>", self._schedule_resize)
        self.bind("<Map>", self._schedule_resize)
        self.after_idle(self._resize_image)

    def _schedule_resize(self, _event: tk.Event) -> None:
        if self.resize_job is not None:
            self.after_cancel(self.resize_job)
        self.resize_job = self.after(60, self._resize_image)

    def _resize_image(self) -> None:
        self.resize_job = None
        available_width = self.winfo_width()
        available_height = self.winfo_height()
        if available_width < 10 or available_height < 10:
            return

        source_width, source_height = self.source_image.size
        scale = min(
            available_width / source_width,
            available_height / source_height,
            1.0,
        )
        target_size = (
            max(round(source_width * scale), 1),
            max(round(source_height * scale), 1),
        )
        resized = self.source_image.resize(target_size, Image.Resampling.LANCZOS)
        self.photo = ImageTk.PhotoImage(resized, master=self)
        self.image_label.configure(image=self.photo)


def tutorial_available(module_key: str) -> bool:
    return module_key in TUTORIALS


def open_tutorial(parent: tk.Widget, module_key: str) -> TutorialWindow | None:
    definition = TUTORIALS.get(module_key)
    if definition is None:
        return None

    image_directory = project_root() / definition.directory
    missing = [
        step.image_name
        for step in definition.steps
        if not (image_directory / step.image_name).exists()
    ]
    if missing:
        messagebox.showerror(
            "Tutorial indisponível",
            "As imagens do tutorial não foram encontradas. Reinstale ou extraia novamente "
            "o aplicativo.",
            parent=parent,
        )
        return None
    return TutorialWindow(parent, definition, image_directory)
