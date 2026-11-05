"""Análise de sensibilidade: variar limiares, níveis, modo do AHP, pesos e julgamentos."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence

import numpy as np
from scipy.stats import kendalltau

from .metodos.ahp import SAATY_MAXIMUM, CriteriaWeights
from .metodos.base import DecisionMethod
from .pipeline import ElectreThenAhp, PipelineSettings
from .problema import DecisionProblem

WEIGHT_TOLERANCE = 1e-9
# Resolução numérica da busca do peso crítico; não é parâmetro do modelo de decisão.
CRITICAL_SCAN_STEP = 0.005
CRITICAL_TOLERANCE = 1e-4
SAATY_STEPS = np.array([1.0 / k for k in range(int(SAATY_MAXIMUM), 1, -1)]
                       + [float(k) for k in range(1, int(SAATY_MAXIMUM) + 1)])


@dataclass(frozen=True, eq=False)
class Scenario:
    """Uma execução de um método: problema, método (com seus parâmetros) e pesos.

    Attributes:
        name: Nome do cenário, único na análise.
        problem: Alternativas e critérios.
        method: Método com os parâmetros do cenário.
        weights: Pesos dos critérios, não negativos, somando 1.
        tags: Rótulos livres (tipo de variação, valor) para tabelas e figuras.
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
        summary: Grandezas resumidas do método (conjunto do AHP, QC), sem as matrizes.
        weights: Pesos usados no cenário.
    """
    name: str
    tags: Mapping[str, object]
    ranked: tuple[str, ...]
    scores: Mapping[str, float]
    summary: Mapping[str, object] = field(default_factory=dict)
    weights: tuple[float, ...] = ()

    @property
    def winner(self) -> str:
        return self.ranked[0]

    @property
    def evaluated(self) -> tuple[str, ...]:
        """Alternativas que o método efetivamente comparou (as que seguiram para o AHP)."""
        return tuple(self.summary.get("conjunto_ahp", self.ranked))


class SensitivityResult:
    """Resultados de todos os cenários e as medidas de estabilidade da escolha."""

    def __init__(self, outcomes: Sequence[ScenarioOutcome]) -> None:
        """O primeiro resultado é o cenário-base."""
        if not outcomes:
            raise ValueError("análise sem cenários")
        self.outcomes = tuple(outcomes)

    @property
    def base(self) -> ScenarioOutcome:
        return self.outcomes[0]

    @property
    def variations(self) -> tuple[ScenarioOutcome, ...]:
        """Todos os cenários, menos o base."""
        return self.outcomes[1:]

    def winner_frequency(self) -> dict[str, float]:
        """Fração das variações em que cada alternativa fica em primeiro, em ordem decrescente."""
        counts: dict[str, int] = {}
        for outcome in self.variations:
            counts[outcome.winner] = counts.get(outcome.winner, 0) + 1
        total = max(len(self.variations), 1)
        return {k: v / total for k, v in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))}

    def base_win_rate(self) -> float:
        """Fração das variações em que a vencedora do cenário-base continua vencendo."""
        if not self.variations:
            return float("nan")
        return sum(o.winner == self.base.winner for o in self.variations) / len(self.variations)

    def base_winner_positions(self) -> list[int | None]:
        """Posição (a partir de 1) da vencedora-base em cada cenário; ``None`` se ausente."""
        code = self.base.winner
        return [o.ranked.index(code) + 1 if code in o.ranked else None for o in self.outcomes]

    def kendall_tau_to_base(self) -> list[float]:
        """Tau de Kendall entre o ranking de cada cenário e o do cenário-base.

        A correlação usa só as alternativas que os dois cenários comparam no AHP
        (a ordem das demais depende do nível do ELECTRE I e de desempates de posição);
        fica NaN se houver menos de duas.
        """
        return [self._tau(self.base, o) for o in self.outcomes]

    @staticmethod
    def _tau(reference: ScenarioOutcome, other: ScenarioOutcome) -> float:
        shared = set(reference.evaluated) & set(other.evaluated)
        first = [c for c in reference.ranked if c in shared]
        position = {c: i for i, c in enumerate(c for c in other.ranked if c in shared)}
        if len(first) < 2:
            return float("nan")
        return float(kendalltau(range(len(first)), [position[c] for c in first]).statistic)

    def table(self) -> list[dict]:
        """Uma linha por cenário: nome, rótulos, vencedora, posição da base, tau e tamanho do AHP."""
        taus, positions = self.kendall_tau_to_base(), self.base_winner_positions()
        return [{"cenario": o.name, **o.tags, "vencedora": o.winner,
                 "mudou": o.winner != self.base.winner, "posicao_da_base": pos,
                 "tau_base": None if np.isnan(tau) else tau,
                 "alternativas_no_ahp": len(o.evaluated), "pesos": list(o.weights)}
                for o, tau, pos in zip(self.outcomes, taus, positions)]


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
                               {codes[i]: float(result.scores[i]) for i in range(len(codes))},
                               result.details.get("resumo", {}),
                               tuple(float(w) for w in scenario.weights))


class ThresholdLine:
    """Varia um limiar do ELECTRE I, com o resto no valor base."""

    def __init__(self, parameter: str, values: Sequence[float]) -> None:
        """Args: parameter: ``tau_d`` (veto) ou ``tau_c`` (apoio); values: valores a testar."""
        if parameter not in ("tau_c", "tau_d"):
            raise ValueError("o limiar deve ser tau_c ou tau_d")
        self.parameter = parameter
        self.values = tuple(values)

    def scenarios(self, problem: DecisionProblem, settings: PipelineSettings,
                  weights: np.ndarray) -> list[Scenario]:
        kind = "veto" if self.parameter == "tau_d" else "apoio"
        return [Scenario(f"{kind}={v:.2f}", problem,
                         ElectreThenAhp(settings.changed(**{self.parameter: v})), weights,
                         {"tipo": kind, "valor": v})
                for v in self.values]


class ThresholdGrid:
    """Todos os pares de apoio e veto, para o mapa de calor."""

    def __init__(self, support: Sequence[float], veto: Sequence[float]) -> None:
        """Args: support: Valores de tau_c; veto: Valores de tau_d."""
        self.support, self.veto = tuple(support), tuple(veto)

    def scenarios(self, problem: DecisionProblem, settings: PipelineSettings,
                  weights: np.ndarray) -> list[Scenario]:
        return [Scenario(f"grade_c{c:.2f}_d{d:.2f}", problem,
                         ElectreThenAhp(settings.changed(tau_c=c, tau_d=d)), weights,
                         {"tipo": "grade", "tau_c": c, "tau_d": d})
                for c in self.support for d in self.veto]


class LevelVariants:
    """Quantos níveis do ELECTRE I seguem para o AHP, com o resto no valor base."""

    def __init__(self, levels: Sequence[int]) -> None:
        """Args: levels: Números de níveis a testar."""
        self.levels = tuple(levels)

    def scenarios(self, problem: DecisionProblem, settings: PipelineSettings,
                  weights: np.ndarray) -> list[Scenario]:
        return [Scenario(f"niveis={n}", problem,
                         ElectreThenAhp(settings.changed(levels=n)), weights,
                         {"tipo": "niveis", "valor": n})
                for n in self.levels]


class LocalJudgmentVariants:
    """Modos de julgamento entre alternativas no AHP, com o resto no valor base."""

    def __init__(self, modes: Sequence[str]) -> None:
        """Args: modes: Modos a testar."""
        self.modes = tuple(modes)

    def scenarios(self, problem: DecisionProblem, settings: PipelineSettings,
                  weights: np.ndarray) -> list[Scenario]:
        return [Scenario(f"modo_ahp={m}", problem,
                         ElectreThenAhp(settings.changed(local_judgment=m)), weights,
                         {"tipo": "modo_ahp", "valor": m})
                for m in self.modes]


class WeightSweep:
    """Cada peso varia de 0 a 1 em passos iguais; os outros se reescalam na proporção original."""

    def __init__(self, steps: int) -> None:
        """Args: steps: Número de valores por critério, no mínimo 2, incluindo 0 e 1."""
        if steps < 2:
            raise ValueError("a varredura precisa de pelo menos dois valores")
        self.steps = steps

    @staticmethod
    def weights_at(base: np.ndarray, index: int, value: float) -> np.ndarray:
        """Pesos com ``base[index]`` trocado por ``value`` e os demais na proporção original."""
        weights = np.zeros_like(base, dtype=float)
        others = [i for i in range(len(base)) if i != index]
        rest = base[others].sum()
        weights[index] = value
        weights[others] = ((1.0 - value) * base[others] / rest if rest > 0
                           else (1.0 - value) / len(others))
        return weights

    def scenarios(self, problem: DecisionProblem, method: DecisionMethod,
                  base_weights: np.ndarray) -> list[Scenario]:
        """Gera ``steps`` cenários por critério."""
        base = np.asarray(base_weights, dtype=float)
        return [Scenario(f"peso_{c.key}={t:.3f}", problem, method, self.weights_at(base, j, t),
                         {"tipo": "peso", "criterio": c.key, "valor": float(t)})
                for j, c in enumerate(problem.criteria)
                for t in np.linspace(0.0, 1.0, self.steps)]


class CriticalWeight:
    """Peso de um critério a partir do qual outra alternativa passa a vencer."""

    def __init__(self, problem: DecisionProblem, method: DecisionMethod,
                 base_weights: np.ndarray) -> None:
        """Args: problem: Alternativas; method: Método; base_weights: Pesos do caso base."""
        self.problem, self.method = problem, method
        self.base = np.asarray(base_weights, dtype=float)

    def _winner(self, index: int, value: float) -> str:
        weights = WeightSweep.weights_at(self.base, index, value)
        return self.problem.alternatives[self.method.evaluate(self.problem, weights).best].identifier

    def find(self, index: int) -> tuple[float | None, float | None]:
        """Pesos críticos abaixo e acima do peso base do critério ``index``.

        Cada valor é o ponto em que a vencedora deixa de ser a do caso base,
        encontrado por varredura e refinado por bisseção; ``None`` se a vencedora
        se mantém até o extremo (0 ou 1).
        """
        start = float(self.base[index])
        winner = self._winner(index, start)
        found = []
        for limit in (0.0, 1.0):
            direction = 1.0 if limit > start else -1.0
            previous, value, crossing = start, start, None
            while (value - limit) * direction < 0:
                value = min(max(value + direction * CRITICAL_SCAN_STEP, 0.0), 1.0)
                if self._winner(index, value) != winner:
                    crossing = (previous, value)
                    break
                previous = value
            if crossing is None:
                found.append(None)
                continue
            keep, change = crossing
            while abs(change - keep) > CRITICAL_TOLERANCE:
                middle = (keep + change) / 2
                if self._winner(index, middle) == winner:
                    keep = middle
                else:
                    change = middle
            found.append(change)
        return found[0], found[1]


class JudgmentPerturbation:
    """Perturba os julgamentos do decisor em degraus da escala de Saaty.

    Um degrau leva a intensidade ao valor vizinho da escala 1/9, ..., 1/2, 1, 2, ..., 9.
    Perturbações que saem da escala ou deixam o QC acima do máximo são descartadas.
    """

    def __init__(self, keys: Sequence[str], judgments: Mapping[str, float],
                 max_ratio: float) -> None:
        """Args: keys: Critérios; judgments: Julgamentos do decisor; max_ratio: QC máximo."""
        self.keys, self.judgments, self.max_ratio = tuple(keys), dict(judgments), max_ratio

    @staticmethod
    def shifted(value: float, steps: int) -> float | None:
        """Intensidade ``steps`` degraus acima de ``value``; ``None`` se sai da escala."""
        position = int(np.argmin(np.abs(SAATY_STEPS - value))) + steps
        return float(SAATY_STEPS[position]) if 0 <= position < len(SAATY_STEPS) else None

    def _weights(self, judgments: Mapping[str, float]) -> np.ndarray | None:
        try:
            return CriteriaWeights(self.keys, judgments).weights(self.max_ratio)
        except ValueError:
            return None

    def one_at_a_time(self, problem: DecisionProblem, settings: PipelineSettings,
                      steps: Sequence[int]) -> tuple[list[Scenario], list[str]]:
        """Um julgamento por vez, de ``-s`` a ``+s`` degraus para cada ``s`` em ``steps``.

        Returns:
            Cenários gerados e a lista de perturbações descartadas.
        """
        method = ElectreThenAhp(settings)
        scenarios, skipped = [], []
        for pair, value in self.judgments.items():
            for step in sorted({*steps, *(-s for s in steps)}):
                name = f"julgamento_{pair}_{step:+d}"
                new = self.shifted(value, step)
                weights = None if new is None else self._weights({**self.judgments, pair: new})
                if weights is None:
                    skipped.append(name)
                    continue
                scenarios.append(Scenario(name, problem, method, weights,
                                          {"tipo": "julgamento", "par": pair, "degraus": step}))
        return scenarios, skipped

    def random(self, problem: DecisionProblem, settings: PipelineSettings, samples: int,
               max_step: int, seed: int) -> tuple[list[Scenario], int]:
        """Todos os julgamentos variando juntos, cada um de ``-max_step`` a ``+max_step`` degraus.

        Returns:
            Cenários aceitos e o número de sorteios descartados.
        """
        rng = np.random.default_rng(seed)
        method = ElectreThenAhp(settings)
        scenarios, skipped = [], 0
        for _ in range(samples):
            shifts = rng.integers(-max_step, max_step + 1, size=len(self.judgments))
            new = {pair: self.shifted(value, int(s))
                   for (pair, value), s in zip(self.judgments.items(), shifts)}
            weights = None if None in new.values() else self._weights(new)
            if weights is None:
                skipped += 1
                continue
            scenarios.append(Scenario(f"sorteio_{len(scenarios) + 1:04d}", problem, method, weights,
                                      {"tipo": "sorteio"}))
        return scenarios, skipped
