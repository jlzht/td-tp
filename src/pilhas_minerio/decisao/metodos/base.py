"""Interface comum dos métodos de apoio à decisão e seu registro."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

from ..problema import DecisionProblem


@dataclass(frozen=True, eq=False)
class MethodResult:
    """Saída de um método para um problema e um vetor de pesos.

    Attributes:
        scores: Pontuação de cada alternativa, na ordem do problema; maior é melhor.
        ranking: Posições das alternativas da melhor para a pior.
        details: Grandezas intermediárias do método (matrizes, fluxos, relações).
    """
    scores: np.ndarray
    ranking: tuple[int, ...]
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def best(self) -> int:
        """Posição da alternativa recomendada."""
        return self.ranking[0]


def ranking_from_scores(scores: np.ndarray) -> tuple[int, ...]:
    """Ordena por pontuação decrescente; empate exato fica na ordem do problema."""
    return tuple(sorted(range(len(scores)), key=lambda i: (-scores[i], i)))


class DecisionMethod(ABC):
    """Um método de apoio à decisão multicritério.

    Os parâmetros do método (limiares, funções de preferência) são argumentos
    do construtor; o problema e os pesos chegam em ``evaluate``. Assim a
    análise de sensibilidade varia uns e outros sem conhecer o método.
    """
    name: str

    @abstractmethod
    def evaluate(self, problem: DecisionProblem, weights: np.ndarray) -> MethodResult:
        """Ordena as alternativas do problema.

        Args:
            problem: Alternativas e critérios.
            weights: Pesos dos critérios, não negativos, somando 1, na ordem das colunas.
        """

    @abstractmethod
    def parameters(self) -> dict[str, Any]:
        """Parâmetros do método, para registrar junto dos resultados."""


METHODS: dict[str, Callable[..., DecisionMethod]] = {}


def register_method(key: str) -> Callable[[Callable[..., DecisionMethod]], Callable[..., DecisionMethod]]:
    """Decorador que inclui uma classe de método no registro ``METHODS``.

    Raises:
        ValueError: Chave já registrada.
    """
    def decorator(factory: Callable[..., DecisionMethod]) -> Callable[..., DecisionMethod]:
        if key in METHODS:
            raise ValueError(f"método já registrado: {key}")
        METHODS[key] = factory
        return factory
    return decorator
