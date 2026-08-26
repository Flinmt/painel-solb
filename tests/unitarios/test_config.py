from __future__ import annotations

import sys

from atualizador_paineis.core.config import initialize_workspace, workspace_root


def test_frozen_workspace_uses_local_app_data(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))

    assert workspace_root() == tmp_path / "LocalAppData" / "SOLB" / "Atualizador SOLB"


def test_initialize_workspace_creates_operational_directories(tmp_path) -> None:
    workspace = initialize_workspace(tmp_path)

    assert workspace == tmp_path
    assert (tmp_path / "atualizados").is_dir()
    assert (tmp_path / "dados" / "entrada" / "exames").is_dir()
    assert (tmp_path / "dados" / "saida").is_dir()
