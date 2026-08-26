from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

import pandas as pd


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def archive_run(
    archive_root: Path,
    period: pd.Period,
    dataframes: dict[str, pd.DataFrame],
    input_paths: dict[str, Path],
) -> Path:
    """Arquiva dados gerados e um manifesto sem registrar conteúdo sensível."""
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    archive_dir = archive_root / f"{period.year}-{period.month:02d}_{timestamp}"
    archive_dir.mkdir(parents=True, exist_ok=False)

    for filename, dataframe in dataframes.items():
        dataframe.to_excel(archive_dir / filename, index=False)

    manifest = {
        "competencia": str(period),
        "criado_em": datetime.now().astimezone().isoformat(),
        "arquivos_gerados": {name: len(frame) for name, frame in dataframes.items()},
        "entradas": {
            key: {"arquivo": path.name, "sha256": _file_hash(path)}
            for key, path in input_paths.items()
        },
    }
    (archive_dir / "manifesto.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return archive_dir
