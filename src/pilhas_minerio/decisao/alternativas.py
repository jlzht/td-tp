"""União das frentes não dominadas das abordagens da Entrega 2."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from ..gvns import Case, evaluate
from ..multiobjetivo import DOM_TOL, dominates, plan_from_counts

Counts = tuple[tuple[int, ...], ...]

ARQUIVOS_PADRAO = {"soma": "nao_dominadas_soma.json",
                   "epsilon": "nao_dominadas_epsilon.json"}


@dataclass(frozen=True)
class Alternative:
    """Uma receita candidata à decisão final.

    Attributes:
        identifier: Código estável (A01, A02, ...) pela ordem canônica dos
            objetivos; muda se o conjunto de entrada mudar.
        counts: Caminhões de cada minério em cada pilha.
        objectives: Custo (R$) e desvios quadráticos de SiO2 e Al2O3 (pp²).
        approaches: Abordagens da Entrega 2 que encontraram a receita.
        origins: Rodada, configuração e semente de cada descoberta.
    """
    identifier: str
    counts: Counts
    objectives: tuple[float, float, float]
    approaches: tuple[str, ...]
    origins: tuple[dict, ...]


@dataclass(frozen=True)
class UnionReport:
    """Contagens de cada etapa da união, para o relatório e para conferência."""
    per_file: dict[str, int]
    distinct_recipes: int
    dominated_removed: int
    final: int


@dataclass(frozen=True)
class UnionResult:
    """Alternativas finais e o relatório da sua construção."""
    alternatives: tuple[Alternative, ...]
    report: UnionReport


class ParetoUnion:
    """Une as frentes das abordagens, reavalia cada receita e filtra a dominância global.

    As frentes da Entrega 2 são não dominadas dentro de cada abordagem; uma
    receita de uma abordagem pode ser dominada por outra da outra abordagem.
    Receitas idênticas viram uma só, com as origens somadas. Receitas
    distintas com objetivos iguais permanecem, como na Entrega 2.
    """

    def __init__(self, case: Case, files: Mapping[str, Path]) -> None:
        """Inicializa a união.

        Args:
            case: Instância usada para reavaliar cada receita.
            files: Abordagem -> arquivo JSON de não dominadas da Entrega 2.
        """
        self.case = case
        self.files = dict(files)

    @classmethod
    def from_directory(cls, case: Case, directory: Path) -> "ParetoUnion":
        """Usa os arquivos padrão de uma pasta de resultados da Entrega 2."""
        return cls(case, {name: directory / file for name, file in ARQUIVOS_PADRAO.items()})

    def build(self) -> UnionResult:
        """Executa a união.

        Returns:
            Alternativas ordenadas por (objetivos, receita) e o relatório.

        Raises:
            ValueError: Receita inadmissível ou com objetivos diferentes dos
                gravados no arquivo.
        """
        distinct: dict[Counts, dict] = {}
        per_file: dict[str, int] = {}
        for approach, path in self.files.items():
            records = json.loads(path.read_text(encoding="utf-8"))
            per_file[approach] = len(records)
            for record in records:
                counts = tuple(tuple(row) for row in record["caminhoes_por_pilha_e_minerio"])
                entry = distinct.setdefault(counts, {"approaches": [], "origins": [],
                                                     "stored": record["objetivos"]})
                if approach not in entry["approaches"]:
                    entry["approaches"].append(approach)
                entry["origins"].extend({"abordagem": approach, **origin}
                                        for origin in record["origens"])
        evaluated = [(counts, self._reevaluate(counts, entry["stored"]), entry)
                     for counts, entry in distinct.items()]
        kept = [(counts, objectives, entry) for counts, objectives, entry in evaluated
                if not any(dominates(other, objectives) for _, other, _ in evaluated)]
        kept.sort(key=lambda item: (item[1], item[0]))
        width = max(2, len(str(len(kept))))
        alternatives = tuple(
            Alternative(f"A{number:0{width}d}", counts, objectives,
                        tuple(entry["approaches"]), tuple(entry["origins"]))
            for number, (counts, objectives, entry) in enumerate(kept, start=1))
        report = UnionReport(per_file, len(distinct), len(distinct) - len(kept), len(kept))
        return UnionResult(alternatives, report)

    def _reevaluate(self, counts: Counts, stored: list[float]) -> tuple[float, float, float]:
        result = evaluate(self.case, plan_from_counts(self.case, [list(row) for row in counts]))
        if not result.feasible:
            raise ValueError("receita da Entrega 2 inadmissível para esta instância")
        if any(abs(x - y) > tol for x, y, tol in zip(result.objectives, stored, DOM_TOL)):
            raise ValueError("objetivos gravados divergem da reavaliação da receita")
        return result.objectives
