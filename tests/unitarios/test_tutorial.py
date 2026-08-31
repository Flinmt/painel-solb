from atualizador_paineis.core.config import project_root
from atualizador_paineis.gui.tutorial import (
    TUTORIAL_GEOMETRY,
    TUTORIAL_MIN_SIZE,
    TUTORIALS,
    tutorial_available,
)


def test_tutorials_registered_for_agenda_and_exames() -> None:
    assert tutorial_available("agenda")
    assert tutorial_available("exames")
    assert not tutorial_available("cirurgias")
    assert len(TUTORIALS["agenda"].steps) == 2
    assert len(TUTORIALS["exames"].steps) == 5


def test_each_tutorial_page_has_one_existing_image() -> None:
    root = project_root()
    for definition in TUTORIALS.values():
        image_names = [step.image_name for step in definition.steps]
        assert len(image_names) == len(set(image_names))
        assert all(
            (root / definition.directory / image_name).is_file()
            for image_name in image_names
        )


def test_tutorial_window_uses_compact_dimensions() -> None:
    assert TUTORIAL_GEOMETRY == "900x620"
    assert TUTORIAL_MIN_SIZE == (700, 500)
