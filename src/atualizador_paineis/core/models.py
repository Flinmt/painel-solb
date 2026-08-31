from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

ProgressCallback = Callable[[str, int], None]


@dataclass(frozen=True, slots=True)
class InputSpec:
    key: str
    label: str
    default_filename: str | None = None
    default_relative_path: Path | None = None
    file_patterns: tuple[str, ...] = ("*.xlsx",)
    selectable: bool = True


@dataclass(frozen=True, slots=True)
class Competence:
    month: int
    year: int


@dataclass(frozen=True, slots=True)
class RunRequest:
    panel_path: Path
    inputs: dict[str, Path]
    workspace: Path
    competence: Competence | None = None


@dataclass(frozen=True, slots=True)
class RunResult:
    panel_path: Path
    backup_path: Path
    archive_path: Path
    period_label: str
    raw_rows: int
    treated_rows: int
    inserted_rows: int
    warnings: tuple[str, ...] = field(default_factory=tuple)
    row_summaries: tuple[tuple[str, int], ...] = field(default_factory=tuple)


class PanelModule(Protocol):
    key: str
    name: str
    description: str
    panel_directory: Path
    input_directory: Path
    panel_glob: str
    input_specs: tuple[InputSpec, ...]
    requires_competence: bool

    def run(
        self,
        request: RunRequest,
        progress: ProgressCallback | None = None,
    ) -> RunResult: ...
