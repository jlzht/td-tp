"""Regra declarada para reduzir a frente a um conjunto tratável pelos métodos."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .problema import DecisionProblem


@dataclass(frozen=True)
class Selection:
    """Alternativas escolhidas e o motivo de cada uma.

    Attributes:
        identifiers: Códigos, na ordem em que a regra os escolheu.
        reasons: Código -> motivo da escolha.
    """
    identifiers: tuple[str, ...]
    reasons: dict[str, str]


class SelectionRule:
    """Escolhe ``count`` alternativas sem usar pesos: âncoras e cobertura da frente.

    1. A melhor alternativa em cada critério (desempate lexicográfico pelos demais
       critérios, na ordem das colunas, e depois pela posição).
    2. A mais próxima do ponto ideal, em distância euclidiana sobre os valores
       normalizados em [0, 1] pelo mínimo e máximo do conjunto, critérios com
       peso igual.
    3. As restantes, uma a uma, pela que mais se afasta das já escolhidas na
       mesma distância (maximin, desempate pela posição).

    Os pesos do decisor não entram, para que a redução do conjunto não
    antecipe a decisão.
    """

    def __init__(self, count: int) -> None:
        """Inicializa a regra.

        Args:
            count: Tamanho do conjunto reduzido.
        """
        self.count = count

    def select(self, problem: DecisionProblem) -> Selection:
        """Aplica a regra.

        Raises:
            ValueError: ``count`` menor que o número de âncoras distintas ou
                maior que o número de alternativas.
        """
        n = len(problem.alternatives)
        if self.count > n:
            raise ValueError(f"o conjunto tem só {n} alternativas")
        loss = problem.losses()
        reasons: dict[str, str] = {}
        chosen: list[int] = []

        def take(index: int, reason: str) -> None:
            if index not in chosen:
                chosen.append(index)
            key = problem.alternatives[index].identifier
            reasons[key] = f"{reasons[key]}; {reason}" if key in reasons else reason

        for j, criterion in enumerate(problem.criteria):
            order = [j] + [k for k in range(loss.shape[1]) if k != j]
            best = min(range(n), key=lambda i: (*(loss[i, k] for k in order), i))
            take(best, f"melhor em {criterion.label}")
        take(int(np.argmin(np.linalg.norm(loss, axis=1))), "mais próxima do ponto ideal")
        if self.count < len(chosen):
            raise ValueError(f"a regra exige pelo menos {len(chosen)} alternativas")
        while len(chosen) < self.count:
            rest = [i for i in range(n) if i not in chosen]
            gap = {i: np.min(np.linalg.norm(loss[chosen] - loss[i], axis=1)) for i in rest}
            farthest = min(rest, key=lambda i: (-gap[i], i))
            take(farthest, f"cobertura da frente (distância {gap[farthest]:.3f} às já escolhidas)")
        return Selection(tuple(problem.alternatives[i].identifier for i in chosen), reasons)
