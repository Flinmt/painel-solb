from __future__ import annotations

import json

import pandas as pd
import pytest

from atualizador_paineis.core.errors import ValidationError
from atualizador_paineis.core.shared_artifacts import (
    EXAMS_SHARED_RELATIVE_PATH,
    publish_exams_artifact,
    validate_exams_artifact,
)


def test_publishes_and_validates_exams_artifact(tmp_path) -> None:
    source = tmp_path / "imagem.xlsx"
    pd.DataFrame({"origem": [1]}).to_excel(source, index=False)
    period = pd.Period("2026-07", freq="M")

    path = publish_exams_artifact(
        tmp_path,
        pd.DataFrame({"Tipo de Exame": ["RM"], "Tipo": ["Imagem"]}),
        period,
        {"imagem": source},
    )

    assert path == tmp_path / EXAMS_SHARED_RELATIVE_PATH
    validate_exams_artifact(path, period)
    metadata = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
    assert metadata["competencia"] == "2026-07"
    assert metadata["linhas"] == 1


def test_rejects_wrong_period_or_modified_artifact(tmp_path) -> None:
    source = tmp_path / "imagem.xlsx"
    pd.DataFrame({"origem": [1]}).to_excel(source, index=False)
    path = publish_exams_artifact(
        tmp_path,
        pd.DataFrame({"Tipo de Exame": ["RM"], "Tipo": ["Imagem"]}),
        pd.Period("2026-07", freq="M"),
        {"imagem": source},
    )

    with pytest.raises(ValidationError, match="competência 2026-07"):
        validate_exams_artifact(path, pd.Period("2026-08", freq="M"))

    pd.DataFrame({"Tipo de Exame": ["ALTERADO"]}).to_excel(path, index=False)
    with pytest.raises(ValidationError, match="alterado"):
        validate_exams_artifact(path, pd.Period("2026-07", freq="M"))
