"""Análise de sensibilidade: variar pesos, parâmetros e conjunto de alternativas."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence

import numpy as np
from scipy.stats import kendalltau

from .metodos.base import DecisionMethod
from .problema import DecisionProblem
from .selecao import SelectionRule

WEIGHT_TOLERANCE = 1e-9


@dataclass(frozen=True, eq=False)
class Scenario:
    """Uma execução de um método: problema, método (com seus parâmetros) e pesos.

    Attributes:
        name: Nome do cenário, único na análise.
        problem: Alternativas e critérios.
        method: Método com os parâmetros do cenário.
        weights: Pesos dos critérios, não negativos, somando 1.
        tags: Rótulos livres (tipo de variação, critério, valor) para tabelas e figuras.
    """
    name: str
    problem: DecisionProblem
    method: DecisionMethod
    weights: np.ndarray
    tags: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        weights = np.asarray(self.weights, dtype=float)
        if (weights.shape != (len(self.problem.criteria),) or np.any(weights < 0)
                or abs(weights.sum() - 1.0) > WEIGHT_TOLERANCE):
            raise ValueError(f"pesos inválidos no cenário {self.name}")
        object.__setattr__(self, "weights", weights)


@dataclass(frozen=True)
class ScenarioOutcome:
    """Resultado de um cenário, indexado pelos códigos das alternativas.

    Attributes:
        name: Nome do cenário.
        tags: Rótulos do cenário.
        ranked: Códigos da melhor para a pior alternativa.
        scores: Código -> pontuação do método.
    """
    name: str
    tags: Mapping[str, object]
    ranked: tuple[str, ...]
    scores: Mapping[str, float]

    @property
    def winner(self) -> str:
        return self.ranked[0]


class SensitivityResult:
    """Resultados de todos os cenários e as medidas de estabilidade do ranking."""

    def __init__(self, outcomes: Sequence[ScenarioOutcome]) -> None:
        """O primeiro resultado é o cenário-base."""
        if not outcomes:
            raise ValueError("análise sem cenários")
        self.outcomes = tuple(outcomes)

    @property
    def base(self) -> ScenarioOutcome:
        return self.outcomes[0]

    def winner_frequency(self) -> dict[str, float]:
        """Fração dos cenários em que cada alternativa fica em primeiro, em ordem decrescente."""
        counts: dict[str, int] = {}
        for outcome in self.outcomes:
            counts[outcome.winner] = counts.get(outcome.winner, 0) + 1
        total = len(self.outcomes)
        return {k: v / total for k, v in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))}

    def rank_acceptability(self) -> tuple[tuple[str, ...], np.ndarray]:
        """Fração dos cenários em que cada alternativa ocupa cada posição.

        Cada linha considera só os cenários em que a alternativa está presente,
        pois a análise pode variar o conjunto de alternativas.

        Returns:
            Códigos (ordem alfabética) e matriz códigos x posições; cada linha soma 1.
        """
        identifiers = tuple(sorted({a for o in self.outcomes for a in o.ranked}))
        matrix = np.zeros((len(identifiers), len(identifiers)))
        present = np.zeros(len(identifiers))
        for outcome in self.outcomes:
            for position, code in enumerate(outcome.ranked):
                row = identifiers.index(code)
                matrix[row, position] += 1
                present[row] += 1
        return identifiers, matrix / np.maximum(present, 1)[:, None]

    def kendall_tau_to_base(self) -> list[float]:
        """Tau de Kendall entre o ranking de cada cenário e o do cenário-base.

        A correlação usa só as alternativas presentes nos dois rankings; fica NaN
        se houver menos de duas.
        """
        return [self._tau(self.base.ranked, outcome.ranked) for outcome in self.outcomes]

    @staticmethod
    def _tau(reference: Sequence[str], other: Sequence[str]) -> float:
        position = {code: i for i, code in enumerate(other)}
        common = [code for code in reference if code in position]
        if len(common) < 2:
            return float("nan")
        return float(kendalltau(range(len(common)), [position[c] for c in common]).statistic)

    def table(self) -> list[dict]:
        """Uma linha por cenário: nome, rótulos, vencedora, tau com a base e ranking."""
        taus = self.kendall_tau_to_base()
        return [{"cenario": o.name, **o.tags, "vencedora": o.winner,
                 "tau_base": tau, "ranking": list(o.ranked)}
                for o, tau in zip(self.outcomes, taus)]


class SensitivityAnalysis:
    """Executa um cenário-base e suas variações."""

    def __init__(self, base: Scenario, variations: Sequence[Scenario]) -> None:
        names = [base.name, *(s.name for s in variations)]
        if len(set(names)) != len(names):
            raise ValueError("nomes de cenário repetidos")
        self.scenarios = (base, *variations)

    def run(self) -> SensitivityResult:
        """Avalia todos os cenários, o base primeiro."""
        return SensitivityResult([self._outcome(s) for s in self.scenarios])

    @staticmethod
    def _outcome(scenario: Scenario) -> ScenarioOutcome:
        result = scenario.method.evaluate(scenario.problem, scenario.weights)
        codes = scenario.problem.identifiers
        return ScenarioOutcome(scenario.name, dict(scenario.tags),
                               tuple(codes[i] for i in result.ranking),
                               {codes[i]: float(result.scores[i]) for i in range(len(codes))})


class WeightSweep:
    """Cada peso varia de 0 a 1 em passos iguais; os outros se reescalam na proporção original."""

    def __init__(self, steps: int) -> None:
        """Args: steps: Número de valores por critério, no mínimo 2, incluindo 0 e 1."""
        if steps < 2:
            raise ValueError("a varredura precisa de pelo menos dois valores")
        self.steps = steps

    def scenarios(self, problem: DecisionProblem, method: DecisionMethod,
                  base_weights: np.ndarray) -> list[Scenario]:
        """Gera ``steps`` cenários por critério."""
        base = np.asarray(base_weights, dtype=float)
        out = []
        for j, criterion in enumerate(problem.criteria):
            for t in np.linspace(0.0, 1.0, self.steps):
                weights = np.zeros_like(base)
                others = [i for i in range(len(base)) if i != j]
                rest = base[others].sum()
                weights[j] = t
                weights[others] = ((1.0 - t) * base[others] / rest if rest > 0
                                   else (1.0 - t) / len(others))
                out.append(Scenario(f"peso_{criterion.key}={t:.3f}", problem, method, weights,
                                    {"tipo": "peso", "criterio": criterion.key, "valor": float(t)}))
        return out


class DirichletWeights:
    """Pesos sorteados de uma Dirichlet centrada nos pesos-base.

    A concentração controla a dispersão: quanto maior, mais perto da base. Não há
    valor padrão; ela deve ser escolhida e justificada por quem usa.
    """

    def __init__(self, concentration: float, samples: int, seed: int) -> None:
        """
        Args:
            concentration: Soma dos parâmetros da Dirichlet; positiva.
            samples: Número de vetores de pesos sorteados.
            seed: Semente do gerador, para reproduzir.
        """
        if concentration <= 0 or samples < 1:
            raise ValueError("concentração e número de sorteios devem ser positivos")
        self.concentration, self.samples, self.seed = concentration, samples, seed

    def scenarios(self, problem: DecisionProblem, method: DecisionMethod,
                  base_weights: np.ndarray) -> list[Scenario]:
        """Gera ``samples`` cenários; exige todos os pesos-base positivos."""
        base = np.asarray(base_weights, dtype=float)
        if np.any(base <= 0):
            raise ValueError("a Dirichlet exige pesos-base positivos")
        draws = np.random.default_rng(self.seed).dirichlet(self.concentration * base, self.samples)
        return [Scenario(f"dirichlet_{i + 1:04d}", problem, method, w,
                         {"tipo": "dirichlet", "concentracao": self.concentration})
                for i, w in enumerate(draws)]


class ParameterVariants:
    """Mesmo problema e pesos, com versões diferentes dos parâmetros do método."""

    def __init__(self, methods: Mapping[str, DecisionMethod]) -> None:
        """Args: methods: Rótulo -> método já parametrizado."""
        self.methods = dict(methods)

    def scenarios(self, problem: DecisionProblem, base_weights: np.ndarray) -> list[Scenario]:
        return [Scenario(f"parametro_{label}", problem, method, base_weights,
                         {"tipo": "parametro", "variante": label})
                for label, method in self.methods.items()]


class AlternativeCountVariants:
    """Mesmo método e pesos, com o conjunto reduzido por tamanhos diferentes."""

    def __init__(self, counts: Sequence[int]) -> None:
        """Args: counts: Tamanhos do conjunto reduzido a comparar."""
        self.counts = tuple(counts)

    def scenarios(self, full: DecisionProblem, method: DecisionMethod,
                  base_weights: np.ndarray) -> list[Scenario]:
        """Reduz ``full`` com ``SelectionRule`` para cada tamanho."""
        out = []
        for count in self.counts:
            ids = SelectionRule(count).select(full).identifiers
            out.append(Scenario(f"alternativas_{count}", full.subset(ids), method, base_weights,
                                {"tipo": "alternativas", "quantidade": count}))
        return out
