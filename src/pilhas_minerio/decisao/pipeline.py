"""ELECTRE I seguido de AHP: o primeiro reduz o conjunto, o segundo escolhe a alternativa final."""
from __future__ import annotations

from typing import Any

import numpy as np

from .metodos.ahp import Ahp
from .metodos.base import DecisionMethod, MethodResult, ranking_from_scores
from .metodos.electre1 import ElectreI
from .problema import DecisionProblem


class ElectreThenAhp(DecisionMethod):
    """Aplica o AHP às alternativas do núcleo do ELECTRE I.

    A pontuação do resultado é composta: as alternativas do núcleo recebem
    ``1 + g`` (``g`` é a prioridade global do AHP) e ficam à frente; as demais recebem o
    negativo do nível do ELECTRE I. Assim o ranking completo respeita as duas etapas.
    """
    name = "ELECTRE I + AHP"

    def __init__(self, tau_c: float, tau_d: float, local_judgment: str) -> None:
        """Inicializa os dois métodos.

        Args:
            tau_c: Limiar de concordância do ELECTRE I.
            tau_d: Limiar de discordância do ELECTRE I.
            local_judgment: Modo dos julgamentos entre alternativas no AHP.
        """
        self.electre = ElectreI(tau_c, tau_d)
        self.ahp = Ahp(local_judgment)

    def parameters(self) -> dict[str, Any]:
        return {**self.electre.parameters(), **self.ahp.parameters()}

    def evaluate(self, problem: DecisionProblem, weights: np.ndarray) -> MethodResult:
        first = self.electre.evaluate(problem, weights)
        kernel = sorted(ElectreI.kernel(first))
        reduced = problem.subset([problem.alternatives[i].identifier for i in kernel])
        second = self.ahp.evaluate(reduced, weights)
        scores = -first.details["nivel_de"].astype(float)
        scores[kernel] = 1.0 + second.scores
        codes = problem.identifiers
        return MethodResult(scores, ranking_from_scores(scores), {
            "electre": first.details, "ahp": second.details, "nucleo": tuple(kernel),
            "resumo": {
                "tamanho_nucleo": len(kernel),
                "nucleo": [codes[i] for i in kernel],
                "tamanho_niveis": first.details["resumo"]["tamanho_niveis"],
                "prioridade_global": {codes[i]: float(g) for i, g in zip(kernel, second.scores)},
                "qc_maximo_ahp": second.details["resumo"]["qc_maximo"]}})
