"""ELECTRE I seguido de AHP: o primeiro reduz o conjunto, o segundo escolhe a alternativa final."""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

import numpy as np

from .metodos.ahp import Ahp
from .metodos.base import DecisionMethod, MethodResult, ranking_from_scores
from .metodos.electre1 import ElectreI
from .problema import DecisionProblem


@dataclass(frozen=True)
class PipelineSettings:
    """Parâmetros do encadeamento, sem os pesos.

    Attributes:
        tau_c: Limiar mínimo de concordância do ELECTRE I.
        tau_d: Limiar máximo de discordância (veto) do ELECTRE I.
        local_judgment: Modo dos julgamentos entre alternativas no AHP.
        levels: Quantos níveis do ELECTRE I, a contar do núcleo, seguem para o AHP.
        tie_tolerance: Diferença relativa de prioridade global, em relação à maior, abaixo da qual
            o AHP considera duas alternativas empatadas.
    """
    tau_c: float
    tau_d: float
    local_judgment: str
    levels: int
    tie_tolerance: float

    def changed(self, **changes: Any) -> "PipelineSettings":
        """Cópia com os campos indicados trocados."""
        return replace(self, **changes)


class ElectreThenAhp(DecisionMethod):
    """Aplica o AHP às alternativas dos primeiros níveis do ELECTRE I.

    A pontuação do resultado é composta: as alternativas que seguem para o AHP recebem
    ``1 + g`` (``g`` é a prioridade global) e ficam à frente; as demais recebem o
    negativo do nível do ELECTRE I. Assim o ranking completo respeita as duas etapas.

    Se o AHP deixa duas ou mais alternativas empatadas no primeiro lugar (prioridade global a
    menos de ``tie_tolerance`` da maior), vence a de menor pior posição na faixa dos critérios,
    isto é, a que evita o pior desempenho relativo em algum critério (minimax).
    """
    name = "ELECTRE I + AHP"

    def __init__(self, settings: PipelineSettings) -> None:
        """Args: settings: Limiares, modo do AHP e número de níveis."""
        self.settings = settings
        self.electre = ElectreI(settings.tau_c, settings.tau_d)
        self.ahp = Ahp(settings.local_judgment)

    def parameters(self) -> dict[str, Any]:
        return {**self.electre.parameters(), **self.ahp.parameters(),
                "niveis": self.settings.levels}

    def evaluate(self, problem: DecisionProblem, weights: np.ndarray) -> MethodResult:
        first = self.electre.evaluate(problem, weights)
        chosen = sorted(ElectreI.top_levels(first, self.settings.levels))
        reduced = problem.subset([problem.alternatives[i].identifier for i in chosen])
        second = self.ahp.evaluate(reduced, weights)
        scores = -first.details["nivel_de"].astype(float)
        scores[chosen] = 1.0 + second.scores
        codes = problem.identifiers
        ranking, tied = self._break_tie(problem, scores, chosen, second.scores)
        return MethodResult(scores, ranking, {
            "electre": first.details, "ahp": second.details, "conjunto_ahp": tuple(chosen),
            "resumo": {
                "empatadas": [codes[i] for i in tied],
                "tamanho_ahp": len(chosen),
                "conjunto_ahp": [codes[i] for i in chosen],
                "tamanho_niveis": first.details["resumo"]["tamanho_niveis"],
                "prioridade_global": {codes[i]: float(g) for i, g in zip(chosen, second.scores)},
                "qc_maximo_ahp": second.details["resumo"]["qc_maximo"]}})

    def _break_tie(self, problem: DecisionProblem, scores: np.ndarray, chosen: list[int],
                   priorities: np.ndarray) -> tuple[tuple[int, ...], list[int]]:
        """Ranking completo e as alternativas empatadas no primeiro lugar (vazio se não há empate)."""
        ranking = ranking_from_scores(scores)
        best = float(priorities.max())
        tied = [i for i, g in zip(chosen, priorities) if g >= best * (1.0 - self.settings.tie_tolerance)]
        if len(tied) < 2:
            return ranking, []
        worst_position = problem.losses().max(axis=1)
        order = sorted(tied, key=lambda i: (worst_position[i], i))
        return tuple(order) + tuple(i for i in ranking if i not in tied), tied
