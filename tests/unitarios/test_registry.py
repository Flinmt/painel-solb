from atualizador_paineis.paineis.registry import available_modules


def test_agenda_is_registered_as_first_panel_tab() -> None:
    modules = available_modules()

    assert [module.key for module in modules] == [
        "agenda",
        "exames",
        "cirurgias",
        "atendimentos",
        "comparativo",
        "3cx",
    ]
    assert [module.name for module in modules] == [
        "Agenda",
        "Exames",
        "Cirurgias",
        "Atendimentos",
        "Comparativo",
        "3CX",
    ]
    assert [spec.default_filename for spec in modules[0].input_specs] == ["agenda.xlsx"]
    assert modules[0].requires_competence is True
    assert [spec.default_filename for spec in modules[1].input_specs] == [
        "imagem.xlsx",
        "laboratorio.xlsx",
        "terapia.xlsx",
        "outros.xlsx",
    ]
    assert [spec.default_filename for spec in modules[2].input_specs] == ["cirurgias.xlsx"]
    assert [spec.default_filename for spec in modules[3].input_specs] == ["atendimentos.xlsx"]
    assert [spec.default_filename for spec in modules[4].input_specs] == [
        "atendimentos.xlsx",
        None,
        "cirurgias.xlsx",
    ]
    assert str(modules[4].input_specs[1].default_relative_path).endswith("exames-consolidado.xlsx")
    assert [spec.default_filename for spec in modules[5].input_specs] == [
        "queue_performance.csv"
    ]
    assert modules[5].input_specs[0].file_patterns == ("*.csv",)
    assert modules[5].requires_competence is True
