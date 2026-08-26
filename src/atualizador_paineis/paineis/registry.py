from __future__ import annotations

from atualizador_paineis.core.models import PanelModule
from atualizador_paineis.paineis.agenda import ScheduleModule
from atualizador_paineis.paineis.atendimentos import AppointmentsModule
from atualizador_paineis.paineis.cirurgias import SurgeriesModule
from atualizador_paineis.paineis.comparativo import ComparisonModule
from atualizador_paineis.paineis.cx3 import ThreeCXModule
from atualizador_paineis.paineis.exames import ExamsModule


def available_modules() -> tuple[PanelModule, ...]:
    """Retorna os módulos exibidos como abas na interface principal."""
    return (
        ScheduleModule(),
        ExamsModule(),
        SurgeriesModule(),
        AppointmentsModule(),
        ComparisonModule(),
        ThreeCXModule(),
    )
