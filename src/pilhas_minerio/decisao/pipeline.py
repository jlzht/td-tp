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
    """
    tau_c: float
    tau_d: float
    local_judgment: str
    levels: int

    def changed(self, **changes: Any) -> "PipelineSettings":
        """Cópia com os campos indicados trocados."""
        return replace(self, **changes)


class ElectreThenAhp(DecisionMethod):
    """Aplica o AHP às alternativas dos primeiros níveis do ELECTRE I.

    A pontuação do resultado é composta: as alternativas que seguem para o AHP recebem
    ``1 + g`` (``g`` é a prioridade global) e ficam à frente; as demais recebem o
    negativo do nível do ELECTRE I. Assim o ranking completo respeita as duas etapas.
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
        return MethodResult(scores, ranking_from_scores(scores), {
            "electre": first.details, "ahp": second.details, "conjunto_ahp": tuple(chosen),
            "resumo": {
                "tamanho_ahp": len(chosen),
                "conjunto_ahp": [codes[i] for i in chosen],
                "tamanho_niveis": first.details["resumo"]["tamanho_niveis"],
                "prioridade_global": {codes[i]: float(g) for i, g in zip(chosen, second.scores)},
                "qc_maximo_ahp": second.details["resumo"]["qc_maximo"]}})
