"""Problema de decisão: alternativas, critérios e a matriz de valores."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

from ..gvns import Case, evaluate
from ..multiobjetivo import plan_from_counts
from .alternativas import Alternative
from .criterios import DecisionCriterion


@dataclass(frozen=True, eq=False)
class DecisionProblem:
    """Alternativas avaliadas em todos os critérios.

    Attributes:
        alternatives: Alternativas, na ordem das linhas de ``values``.
        criteria: Critérios, na ordem das colunas de ``values``.
        values: Matriz (alternativas x critérios) com os valores brutos.
    """
    alternatives: tuple[Alternative, ...]
    criteria: tuple[DecisionCriterion, ...]
    values: np.ndarray

    @classmethod
    def build(cls, case: Case, alternatives: Sequence[Alternative],
              criteria: Sequence[DecisionCriterion]) -> "DecisionProblem":
        """Avalia cada alternativa em cada critério."""
        rows = []
        for alternative in alternatives:
            counts = [list(row) for row in alternative.counts]
            evaluation = evaluate(case, plan_from_counts(case, counts))
            rows.append([criterion.evaluate(case, counts, evaluation) for criterion in criteria])
        return cls(tuple(alternatives), tuple(criteria), np.array(rows, dtype=float))

    @property
    def identifiers(self) -> tuple[str, ...]:
        return tuple(a.identifier for a in self.alternatives)

    def index_of(self, identifier: str) -> int:
        """Posição da alternativa; ``ValueError`` se não pertence ao problema."""
        return self.identifiers.index(identifier)

    def subset(self, identifiers: Sequence[str]) -> "DecisionProblem":
        """Subproblema com as alternativas dadas, mantendo a ordem original."""
        wanted = set(identifiers)
        if not wanted <= set(self.identifiers):
            raise ValueError(f"alternativas inexistentes: {sorted(wanted - set(self.identifiers))}")
        rows = [i for i, a in enumerate(self.alternatives) if a.identifier in wanted]
        return DecisionProblem(tuple(self.alternatives[i] for i in rows), self.criteria,
                               self.values[rows])

    def losses(self) -> np.ndarray:
        """Valores em [0, 1] por critério, com 0 para o melhor e 1 para o pior do conjunto.

        Critério sem variação entre as alternativas vira coluna de zeros.
        """
        low, high = self.values.min(axis=0), self.values.max(axis=0)
        span = np.where(high > low, high - low, 1.0)
        loss = (self.values - low) / span
        for j, criterion in enumerate(self.criteria):
            if not criterion.minimize:
                loss[:, j] = np.where(high[j] > low[j], 1.0 - loss[:, j], 0.0)
        return loss

    def nondominated_mask(self) -> np.ndarray:
        """Quais alternativas não são dominadas em todos os critérios do problema."""
        sign = np.array([1.0 if c.minimize else -1.0 for c in self.criteria])
        tol = np.array([c.tolerance for c in self.criteria])
        oriented = self.values * sign
        mask = np.ones(len(self.alternatives), dtype=bool)
        for i, point in enumerate(oriented):
            no_worse = np.all(oriented <= point + tol, axis=1)
            better = np.any(oriented < point - tol, axis=1)
            mask[i] = not np.any(no_worse & better)
        return mask
