from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk


def _show_loading_screen(root: tk.Tk) -> tk.StringVar:
    root.title("Atualizador SOLB")
    root.geometry("430x160")
    root.resizable(False, False)
    root.option_add("*Font", "{Segoe UI} 10")

    container = ttk.Frame(root, padding=24)
    container.pack(fill="both", expand=True)
    ttk.Label(
        container,
        text="Atualizador SOLB",
        font=("Segoe UI", 18, "bold"),
    ).pack(anchor="center")

    status = tk.StringVar(value="Carregando a aplicação...")
    ttk.Label(container, textvariable=status).pack(anchor="center", pady=(12, 10))
    progress = ttk.Progressbar(container, mode="indeterminate", length=330)
    progress.pack(anchor="center")
    progress.start(12)

    root.update_idletasks()
    x = max((root.winfo_screenwidth() - root.winfo_width()) // 2, 0)
    y = max((root.winfo_screenheight() - root.winfo_height()) // 2, 0)
    root.geometry(f"+{x}+{y}")
    root.update()
    return status


def main() -> None:
    root = tk.Tk()
    status = _show_loading_screen(root)

    try:
        status.set("Preparando pastas e configurações...")
        root.update()
        from atualizador_paineis.core.config import initialize_workspace, load_panel_config
        from atualizador_paineis.core.logging import configure_logging

        workspace = initialize_workspace()
        configure_logging(workspace / load_panel_config("exames").output_directory)

        status.set("Carregando os módulos dos painéis...")
        root.update()
        from atualizador_paineis.excel.automation import excel_is_available
        from atualizador_paineis.gui.main_window import MainWindow

        if not excel_is_available():
            messagebox.showerror(
                "Microsoft Excel necessário",
                "O Atualizador SOLB precisa do Microsoft Excel instalado "
                "para atualizar os painéis.",
                parent=root,
            )
            root.destroy()
            return

        for widget in root.winfo_children():
            widget.destroy()
        root.resizable(True, True)
        MainWindow(root)
    except Exception as exc:
        messagebox.showerror(
            "Falha ao iniciar",
            f"Não foi possível iniciar o Atualizador SOLB.\n\nDetalhes: {exc}",
            parent=root,
        )
        root.destroy()
        return

    root.mainloop()


if __name__ == "__main__":
    main()
