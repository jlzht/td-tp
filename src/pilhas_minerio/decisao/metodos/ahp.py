"""AHP (Processo Analítico Hierárquico), na notação das aulas de Teoria da Decisão.

Cada matriz de comparação ``A = [a_ij]`` é positiva e recíproca (``a_ii = 1``,
``a_ji = 1/a_ij``). O vetor de prioridades ``v`` é o autovetor principal de ``A``,
com ``sum(v) = 1``. O índice de consistência é ``IC = (lambda_max - n)/(n - 1)`` e o
quociente de consistência é ``QC = IC/ICA``, em que ``ICA`` é o índice de
consistência aleatório; julgamentos com ``QC <= 0,10`` são aceitos. A síntese global é
``g = P w``, com ``P`` as prioridades locais por critério e ``w`` os pesos dos critérios.

Referências: Saaty (1994), How to Make a Decision: The Analytic Hierarchy Process,
Interfaces 24(6), p. 19-43 (existência confirmada; texto completo não lido), e os
slides da aula 10 da disciplina, que fornecem a tabela de ICA usada até n = 10.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any, Mapping, Sequence

import numpy as np

from ..problema import DecisionProblem
from .base import DecisionMethod, MethodResult, ranking_from_scores, register_method

SAATY_MAXIMUM = 9.0
LOCAL_JUDGMENTS = ("faixa_linear", "razao")
# Tabela de ICA dos slides da aula 10 (n = 1 a 10).
RANDOM_INDEX_TABLE = {1: 0.0, 2: 0.0, 3: 0.52, 4: 0.89, 5: 1.11,
                      6: 1.25, 7: 1.35, 8: 1.40, 9: 1.45, 10: 1.49}
SIMULATION_SAMPLES = 20000
SIMULATION_SEED = 20260510


class ComparisonMatrix:
    """Matriz de comparação par a par e suas medidas de consistência."""

    def __init__(self, values: np.ndarray) -> None:
        """Inicializa a matriz.

        Args:
            values: Matriz quadrada positiva e recíproca.

        Raises:
            ValueError: A matriz não é quadrada, positiva e recíproca.
        """
        matrix = np.asarray(values, dtype=float)
        if (matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1] or np.any(matrix <= 0)
                or not np.allclose(np.diag(matrix), 1.0)
                or not np.allclose(matrix * matrix.T, 1.0)):
            raise ValueError("a matriz de comparação deve ser positiva e recíproca, com diagonal 1")
        self.values = matrix

    @property
    def order(self) -> int:
        return self.values.shape[0]

    def principal_eigenpair(self) -> tuple[float, np.ndarray]:
        """Maior autovalor e o autovetor principal normalizado para somar 1."""
        eigenvalues, eigenvectors = np.linalg.eig(self.values)
        top = int(np.argmax(eigenvalues.real))
        vector = np.abs(eigenvectors[:, top].real)
        return float(eigenvalues[top].real), vector / vector.sum()

    def priorities(self) -> np.ndarray:
        """Vetor de prioridades ``v``."""
        return self.principal_eigenpair()[1]

    def consistency_index(self) -> float:
        """``IC = (lambda_max - n)/(n - 1)``; zero para n <= 2."""
        if self.order <= 2:
            return 0.0
        return (self.principal_eigenpair()[0] - self.order) / (self.order - 1)

    def consistency_ratio(self) -> float:
        """``QC = IC/ICA``; zero para n <= 2."""
        index = RandomIndex.value(self.order)
        return self.consistency_index() / index if index > 0 else 0.0


class RandomIndex:
    """Índice de consistência aleatório (ICA).

    Até n = 10 vale a tabela dos slides da aula. Acima disso o valor é a média de IC
    de matrizes recíprocas sorteadas na escala de Saaty (entradas de 1/9 a 9, com
    semente fixa), a mesma definição da tabela.
    """

    @staticmethod
    @lru_cache(maxsize=None)
    def value(n: int) -> float:
        """ICA para matrizes de ordem ``n``."""
        if n in RANDOM_INDEX_TABLE:
            return RANDOM_INDEX_TABLE[n]
        return RandomIndex.simulate(n, SIMULATION_SAMPLES, SIMULATION_SEED)

    @staticmethod
    def simulate(n: int, samples: int, seed: int) -> float:
        """Média de IC de ``samples`` matrizes recíprocas aleatórias de ordem ``n``."""
        rng = np.random.default_rng(seed)
        scale = np.array([1.0 / k for k in range(9, 1, -1)] + [float(k) for k in range(1, 10)])
        rows, cols = np.triu_indices(n, k=1)
        total = 0.0
        for _ in range(samples):
            matrix = np.ones((n, n))
            matrix[rows, cols] = rng.choice(scale, size=len(rows))
            matrix[cols, rows] = 1.0 / matrix[rows, cols]
            lam = np.max(np.linalg.eigvals(matrix).real)
            total += (lam - n) / (n - 1)
        return total / samples


class CriteriaWeights:
    """Pesos dos critérios a partir dos julgamentos par a par do decisor."""

    def __init__(self, keys: Sequence[str], judgments: Mapping[str, float]) -> None:
        """Inicializa os julgamentos.

        Args:
            keys: Chaves dos critérios, na ordem das colunas do problema.
            judgments: ``"a:b" -> intensidade`` de a sobre b na escala de Saaty
                (1 a 9; abaixo de 1 se b for preferido a a). Todo par (a, b), com
                a antes de b na ordem de ``keys``, deve aparecer.

        Raises:
            ValueError: Par ausente, par desconhecido ou valor fora de [1/9, 9].
        """
        self.keys = tuple(keys)
        position = {key: i for i, key in enumerate(self.keys)}
        n = len(self.keys)
        matrix = np.ones((n, n))
        seen = set()
        for pair, value in judgments.items():
            a, _, b = pair.partition(":")
            if a not in position or b not in position or position[a] >= position[b]:
                raise ValueError(f"julgamento inválido: {pair}")
            if not 1.0 / SAATY_MAXIMUM <= value <= SAATY_MAXIMUM:
                raise ValueError(f"intensidade fora da escala de Saaty em {pair}: {value}")
            i, j = position[a], position[b]
            matrix[i, j], matrix[j, i] = value, 1.0 / value
            seen.add((i, j))
        if len(seen) != n * (n - 1) // 2:
            raise ValueError("faltam julgamentos: são necessários n(n-1)/2 pares")
        self.matrix = ComparisonMatrix(matrix)

    def weights(self, max_ratio: float) -> np.ndarray:
        """Vetor ``w`` de pesos.

        Args:
            max_ratio: Maior QC aceito (0,10 nas aulas).

        Raises:
            ValueError: QC acima de ``max_ratio``; os julgamentos devem ser revistos.
        """
        ratio = self.matrix.consistency_ratio()
        if ratio > max_ratio:
            raise ValueError(f"QC = {ratio:.3f} acima de {max_ratio}: revisar os julgamentos")
        return self.matrix.priorities()


@register_method("ahp")
class Ahp(DecisionMethod):
    """AHP com síntese distributiva: ``g = P w``.

    Os julgamentos entre alternativas, em cada critério, vêm dos valores medidos
    (não há 45 julgamentos manuais por critério):

    * ``faixa_linear``: a vantagem de a_i sobre a_k, medida como fração da amplitude do
      critério no conjunto, vira intensidade ``1 + 8 d`` na escala de Saaty (o melhor
      contra o pior do conjunto vale 9). Respeita a faixa de variação, como pedem as
      aulas ao tratar de pesos.
    * ``razao``: ``a_ik`` é a razão entre os valores medidos (inversa nos critérios de
      minimização), sem limite em 9.
    """
    name = "AHP"

    def __init__(self, local_judgment: str) -> None:
        """Inicializa o método.

        Args:
            local_judgment: ``faixa_linear`` ou ``razao``.

        Raises:
            ValueError: Modo desconhecido.
        """
        if local_judgment not in LOCAL_JUDGMENTS:
            raise ValueError(f"julgamento local desconhecido: {local_judgment}")
        self.local_judgment = local_judgment

    def parameters(self) -> dict[str, Any]:
        return {"julgamento_local": self.local_judgment}

    def comparison_matrix(self, problem: DecisionProblem, criterion: int) -> ComparisonMatrix:
        """Matriz de comparação das alternativas sob um critério."""
        column = problem.values[:, criterion]
        minimize = problem.criteria[criterion].minimize
        if self.local_judgment == "razao":
            ratio = column[None, :] / column[:, None]
            matrix = ratio if minimize else 1.0 / ratio
        else:
            amplitude = column.max() - column.min()
            gain = (column[None, :] - column[:, None]) if minimize else (column[:, None] - column[None, :])
            advantage = gain / amplitude if amplitude > 0 else np.zeros_like(gain)
            strength = 1.0 + (SAATY_MAXIMUM - 1.0) * np.abs(advantage)
            matrix = np.where(advantage >= 0, strength, 1.0 / strength)
        return ComparisonMatrix(matrix)

    def evaluate(self, problem: DecisionProblem, weights: np.ndarray) -> MethodResult:
        matrices = [self.comparison_matrix(problem, j) for j in range(len(problem.criteria))]
        local = np.column_stack([m.priorities() for m in matrices])
        scores = local @ np.asarray(weights, dtype=float)
        ratios = [m.consistency_ratio() for m in matrices]
        return MethodResult(scores, ranking_from_scores(scores), {
            "prioridades_locais": local, "qc_por_criterio": ratios,
            "resumo": {"qc_maximo": float(max(ratios))}})
