from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pandas as pd

from atualizador_paineis.core.errors import ValidationError

EXAMS_SHARED_RELATIVE_PATH = Path("dados/saida/compartilhados/exames/exames-consolidado.xlsx")


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def publish_exams_artifact(
    workspace: Path,
    dataframe: pd.DataFrame,
    period: pd.Period,
    input_paths: dict[str, Path],
) -> Path:
    output_path = workspace / EXAMS_SHARED_RELATIVE_PATH
    metadata_path = output_path.with_suffix(".json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    token = uuid4().hex
    temporary_xlsx = output_path.with_name(f".{output_path.stem}-{token}.xlsx")
    temporary_json = metadata_path.with_name(f".{metadata_path.stem}-{token}.json")
    try:
        dataframe.to_excel(temporary_xlsx, index=False)
        metadata = {
            "competencia": str(period),
            "gerado_em": datetime.now().astimezone().isoformat(),
            "linhas": len(dataframe),
            "sha256": file_hash(temporary_xlsx),
            "fontes": {
                key: {"arquivo": path.name, "sha256": file_hash(path)}
                for key, path in input_paths.items()
            },
        }
        temporary_json.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary_xlsx, output_path)
        os.replace(temporary_json, metadata_path)
    finally:
        temporary_xlsx.unlink(missing_ok=True)
        temporary_json.unlink(missing_ok=True)
    return output_path


def validate_exams_artifact(path: Path, period: pd.Period) -> None:
    metadata_path = path.with_suffix(".json")
    if not path.exists() or not metadata_path.exists():
        raise ValidationError(
            "O consolidado de Exames não foi encontrado. Atualize primeiro a aba Exames."
        )
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError("O manifesto do consolidado de Exames é inválido.") from exc
    if metadata.get("competencia") != str(period):
        raise ValidationError(
            "O consolidado de Exames pertence à competência "
            f"{metadata.get('competencia', 'desconhecida')}; esperado: {period}."
        )
    if metadata.get("sha256") != file_hash(path):
        raise ValidationError(
            "O consolidado de Exames foi alterado após sua geração. "
            "Atualize a aba Exames novamente."
        )
