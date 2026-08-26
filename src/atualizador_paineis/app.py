from __future__ import annotations

import tkinter as tk

from atualizador_paineis.core.config import load_panel_config, workspace_root
from atualizador_paineis.core.logging import configure_logging
from atualizador_paineis.gui.main_window import MainWindow


def main() -> None:
    workspace = workspace_root()
    configure_logging(workspace / load_panel_config("exames").output_directory)
    root = tk.Tk()
    MainWindow(root)
    root.mainloop()


if __name__ == "__main__":
    main()
