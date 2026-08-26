from __future__ import annotations

import tkinter as tk
from tkinter import messagebox

from atualizador_paineis.core.config import initialize_workspace, load_panel_config
from atualizador_paineis.core.logging import configure_logging
from atualizador_paineis.excel.automation import excel_is_available
from atualizador_paineis.gui.main_window import MainWindow


def main() -> None:
    workspace = initialize_workspace()
    configure_logging(workspace / load_panel_config("exames").output_directory)
    root = tk.Tk()
    if not excel_is_available():
        messagebox.showerror(
            "Microsoft Excel necessário",
            "O Atualizador SOLB precisa do Microsoft Excel instalado para atualizar os painéis.",
            parent=root,
        )
        root.destroy()
        return
    MainWindow(root)
    root.mainloop()


if __name__ == "__main__":
    main()
