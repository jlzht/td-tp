"""ELECTRE I, na formulação e na notação das aulas de Teoria da Decisão.

Para cada par (a_i, a_k) os critérios se dividem em favoráveis J+, indiferentes J= e
contrários J-. O índice de concordância C_ik soma os pesos de J+ e J=; o de
discordância D_ik é a maior desvantagem de a_i sobre a_k nos critérios de J-,
dividida pela amplitude do critério (fator de escala delta_j). A relação
a_i S a_k vale quando C_ik >= tau_c e D_ik <= tau_d. A ordenação retira, nível a
nível, as ações que nenhuma outra sobreclassifica.

Circuitos do grafo (ações que se sobreclassificam em ciclo) são reduzidos a uma só
classe antes da retirada, pois sem isso nenhuma ação deixaria de ser
sobreclassificada. Roy e colaboradores propuseram o método; Figueira, Mousseau e Roy (2005,
cap. 4 de Multiple Criteria Decision Analysis: State of the Art Surveys) o
resumem.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components

from ..problema import DecisionProblem
from .base import DecisionMethod, MethodResult, register_method

THRESHOLD_TOLERANCE = 1e-12


@register_method("electre1")
class ElectreI(DecisionMethod):
    """Sobreclassificação por concordância e discordância, com ordenação em níveis."""
    name = "ELECTRE I"

    def __init__(self, tau_c: float, tau_d: float) -> None:
        """Inicializa o método.

        Args:
            tau_c: Limiar mínimo de concordância, em (0, 1].
            tau_d: Limiar máximo de discordância, em [0, 1].

        Raises:
            ValueError: Limiar fora do intervalo.
        """
        if not 0 < tau_c <= 1 or not 0 <= tau_d <= 1:
            raise ValueError("tau_c deve estar em (0, 1] e tau_d em [0, 1]")
        self.tau_c = tau_c
        self.tau_d = tau_d

    def parameters(self) -> dict[str, Any]:
        return {"tau_c": self.tau_c, "tau_d": self.tau_d}

    def concordance_discordance(self, problem: DecisionProblem,
                                weights: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Matrizes C e D, com a linha i e a coluna k para a afirmação a_i S a_k.

        A diagonal vale 1 em C e 0 em D e não entra na relação.

        Args:
            problem: Alternativas e critérios.
            weights: Pesos w_j dos critérios.
        """
        n, m = problem.values.shape
        sign = np.array([1.0 if c.minimize else -1.0 for c in problem.criteria])
        tolerance = np.array([c.tolerance for c in problem.criteria])
        amplitude = problem.values.max(axis=0) - problem.values.min(axis=0)
        delta = np.where(amplitude > 0, 1.0 / np.where(amplitude > 0, amplitude, 1.0), 0.0)
        # Desvantagem de a_i sobre a_k no critério j: positiva quando a_i é pior.
        disadvantage = sign * (problem.values[:, None, :] - problem.values[None, :, :])
        favorable = disadvantage < -tolerance
        indifferent = np.abs(disadvantage) <= tolerance
        contrary = disadvantage > tolerance
        concordance = ((favorable | indifferent) * weights).sum(axis=2) / weights.sum()
        scaled = np.where(contrary, disadvantage * delta, 0.0)
        discordance = scaled.max(axis=2) if m else np.zeros((n, n))
        return concordance, discordance

    def outranking(self, concordance: np.ndarray, discordance: np.ndarray) -> np.ndarray:
        """Matriz booleana S: S[i, k] é verdadeiro quando a_i sobreclassifica a_k."""
        relation = ((concordance >= self.tau_c - THRESHOLD_TOLERANCE)
                    & (discordance <= self.tau_d + THRESHOLD_TOLERANCE))
        np.fill_diagonal(relation, False)
        return relation

    @staticmethod
    def levels(relation: np.ndarray) -> tuple[list[list[int]], np.ndarray]:
        """Níveis de ordenação e a classe de cada alternativa.

        Args:
            relation: Matriz S.

        Returns:
            Lista de níveis (do primeiro, o núcleo, ao último), cada um com as
            posições das alternativas, e o vetor com o rótulo do circuito (classe
            fortemente conexa) de cada alternativa.
        """
        _, label = connected_components(csr_matrix(relation), directed=True, connection="strong")
        classes = int(label.max()) + 1
        arcs = {(label[i], label[k]) for i, k in zip(*np.nonzero(relation)) if label[i] != label[k]}
        incoming = np.zeros(classes, dtype=int)
        for _, target in arcs:
            incoming[target] += 1
        remaining = set(range(classes))
        levels: list[list[int]] = []
        while remaining:
            top = sorted(c for c in remaining if incoming[c] == 0)
            levels.append(sorted(int(i) for i in np.nonzero(np.isin(label, top))[0]))
            remaining -= set(top)
            for source, target in arcs:
                if source in top:
                    incoming[target] -= 1
        return levels, label

    def evaluate(self, problem: DecisionProblem, weights: np.ndarray) -> MethodResult:
        concordance, discordance = self.concordance_discordance(problem, weights)
        relation = self.outranking(concordance, discordance)
        levels, label = self.levels(relation)
        level_of = np.empty(len(problem.alternatives), dtype=int)
        for number, members in enumerate(levels):
            level_of[members] = number
        scores = -level_of.astype(float)
        ranking = tuple(sorted(range(len(scores)), key=lambda i: (level_of[i], i)))
        return MethodResult(scores, ranking, {
            "concordancia": concordance, "discordancia": discordance, "sobreclassificacao": relation,
            "niveis": levels, "nivel_de": level_of, "circuito_de": label,
            "relacoes": int(relation.sum()),
            "resumo": {"relacoes": int(relation.sum()), "tamanho_niveis": [len(x) for x in levels]}})

    @staticmethod
    def kernel(result: MethodResult) -> tuple[int, ...]:
        """Núcleo: posições das alternativas que nenhuma outra sobreclassifica (primeiro nível)."""
        return tuple(result.details["niveis"][0])

    def calibrate_tau_d(self, problem: DecisionProblem, weights: np.ndarray, target: int,
                        grid: np.ndarray) -> "KernelCalibration":
        """Escolhe tau_d, mantido tau_c, para que o núcleo fique com ``target`` alternativas.

        Um veto mais frouxo (tau_d maior) cria mais relações de sobreclassificação e
        encolhe o núcleo. A calibração percorre ``grid`` e fica com o tau_d de núcleo mais
        próximo de ``target``; em empate, o menor tau_d (veto mais exigente).

        Args:
            problem: Alternativas e critérios.
            weights: Pesos dos critérios.
            target: Tamanho desejado do núcleo.
            grid: Valores de tau_d a testar, em [0, 1].
        """
        concordance, discordance = self.concordance_discordance(problem, weights)
        sizes = []
        for tau_d in grid:
            relation = ElectreI(self.tau_c, float(tau_d)).outranking(concordance, discordance)
            sizes.append(len(self.levels(relation)[0][0]))
        best = min(range(len(grid)), key=lambda i: (abs(sizes[i] - target), grid[i]))
        return KernelCalibration(float(grid[best]), sizes[best], tuple(float(x) for x in grid),
                                 tuple(sizes))


@dataclass(frozen=True)
class KernelCalibration:
    """Resultado da calibração de tau_d.

    Attributes:
        tau_d: Limiar escolhido.
        kernel_size: Tamanho do núcleo com esse limiar.
        grid: Valores de tau_d testados.
        sizes: Tamanho do núcleo para cada valor de ``grid``.
    """
    tau_d: float
    kernel_size: int
    grid: tuple[float, ...]
    sizes: tuple[int, ...]
