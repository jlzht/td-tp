"""Critérios de decisão: os três objetivos da otimização e o critério extra."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Callable, Sequence

from ..gvns import Case, Evaluation


class DecisionCriterion(ABC):
    """Um atributo pelo qual as alternativas são comparadas.

    Attributes:
        key: Identificador em letras minúsculas, sem acento.
        label: Nome para tabelas e figuras.
        unit: Unidade de medida, para eixos e tabelas.
        minimize: Verdadeiro se menor é melhor.
        tolerance: Diferença abaixo da qual dois valores são considerados iguais
            na dominância.
    """
    key: str
    label: str
    unit: str
    minimize: bool = True
    tolerance: float = 1e-10

    @abstractmethod
    def evaluate(self, case: Case, counts: Sequence[Sequence[int]],
                 evaluation: Evaluation) -> float:
        """Valor do critério para uma receita.

        Args:
            case: Instância do problema.
            counts: Caminhões de cada minério em cada pilha.
            evaluation: Avaliação da receita pela função de objetivos da otimização.
        """


class ObjectiveCriterion(DecisionCriterion):
    """Um dos três objetivos da otimização, lido da avaliação da receita."""

    def __init__(self, index: int, key: str, label: str, unit: str, tolerance: float) -> None:
        self.index = index
        self.key = key
        self.label = label
        self.unit = unit
        self.tolerance = tolerance

    def evaluate(self, case: Case, counts: Sequence[Sequence[int]],
                 evaluation: Evaluation) -> float:
        return float(evaluation.objectives[self.index])


class RecipeHomogeneity(DecisionCriterion):
    """Afastamento das receitas das pilhas de um equipamento em relação à receita comum.

    Para a pilha ``p``, ``r_p`` é a fração de caminhões de cada minério. A receita
    comum do equipamento ``g`` é o total de caminhões de cada minério no grupo
    dividido pelo total de caminhões do grupo. ``H_g`` é a média, sobre as pilhas
    do grupo, da distância L1 entre ``r_p`` e a receita comum; ``H`` é a média de
    ``H_g`` sobre os equipamentos. Vale 0 quando todas as pilhas de cada grupo
    têm a mesma proporção de minérios e no máximo 2.
    """
    key = "homogeneidade"
    label = "Afastamento da receita comum (H)"
    unit = "distância L1"

    def evaluate(self, case: Case, counts: Sequence[Sequence[int]],
                 evaluation: Evaluation) -> float:
        by_group: dict[int, list[Sequence[int]]] = {}
        for group, row in zip(case.groups, counts):
            by_group.setdefault(group, []).append(row)
        distances = []
        for rows in by_group.values():
            total = [sum(row[j] for row in rows) for j in range(len(rows[0]))]
            trucks = sum(total)
            common = [n / trucks for n in total]
            distances.append(sum(
                sum(abs(n / sum(row) - c) for n, c in zip(row, common)) for row in rows
            ) / len(rows))
        return sum(distances) / len(distances)


EXTRA_CRITERIA: dict[str, Callable[[], DecisionCriterion]] = {
    "homogeneidade": RecipeHomogeneity,
}


def objective_criteria() -> tuple[DecisionCriterion, DecisionCriterion, DecisionCriterion]:
    """Custo e desvios quadráticos de SiO2 e Al2O3, na ordem de f1, f2, f3."""
    return (ObjectiveCriterion(0, "custo", "Custo", "R$", 1e-6),
            ObjectiveCriterion(1, "desvio_sio2", "Desvio de SiO₂", "pp²", 1e-10),
            ObjectiveCriterion(2, "desvio_al2o3", "Desvio de Al₂O₃", "pp²", 1e-10))


def build_criteria(extra: str = "homogeneidade") -> tuple[DecisionCriterion, ...]:
    """Os três objetivos mais o critério extra escolhido pelo nome.

    Args:
        extra: Chave em ``EXTRA_CRITERIA``.

    Raises:
        ValueError: Chave desconhecida.
    """
    if extra not in EXTRA_CRITERIA:
        raise ValueError(f"critério extra desconhecido: {extra}; opções: {sorted(EXTRA_CRITERIA)}")
    return (*objective_criteria(), EXTRA_CRITERIA[extra]())
