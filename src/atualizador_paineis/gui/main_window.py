from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from atualizador_paineis.core.config import workspace_root
from atualizador_paineis.gui.panel_tab import PanelTab
from atualizador_paineis.paineis.registry import available_modules


class MainWindow:
    """Janela principal e ponto de navegação entre os módulos de painéis."""

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.workspace = workspace_root()
        self.tabs: list[PanelTab] = []

        self._configure_window()
        self._build_widgets()

    def _configure_window(self) -> None:
        self.root.title("Central de Atualização de Painéis")
        self.root.geometry("900x680")
        self.root.minsize(780, 600)
        self.root.option_add("*Font", "{Segoe UI} 10")

        style = ttk.Style(self.root)
        style.configure("Title.TLabel", font=("Segoe UI", 20, "bold"))
        style.configure("PanelTitle.TLabel", font=("Segoe UI", 15, "bold"))
        style.configure("Subtitle.TLabel", foreground="#4b5563")
        style.configure("Primary.TButton", font=("Segoe UI", 11, "bold"), padding=10)
        style.configure("TNotebook.Tab", padding=(16, 8))

    def _build_widgets(self) -> None:
        container = ttk.Frame(self.root, padding=20)
        container.pack(fill="both", expand=True)

        ttk.Label(
            container,
            text="Central de Atualização de Painéis",
            style="Title.TLabel",
        ).pack(anchor="w")
        ttk.Label(
            container,
            text="Selecione uma aba para atualizar o painel correspondente.",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(2, 16))

        notebook = ttk.Notebook(container)
        notebook.pack(fill="both", expand=True)

        for module in available_modules():
            tab = PanelTab(notebook, self.workspace, module)
            notebook.add(tab, text=module.name)
            self.tabs.append(tab)
