"""Entrega 3, etapa 1: une as frentes, calcula os critérios e reduz as alternativas.

Execute: python -m pilhas_minerio.decisao.preparar
Saída em resultados/entrega_3/.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from scipy.stats import spearmanr

from ..caminhos import DATA_FILE, RESULTS_DIR
from ..gvns import load_case
from ..multiobjetivo import write_json
from .alternativas import ParetoUnion, UnionResult
from .criterios import EXTRA_CRITERIA, build_criteria
from .problema import DecisionProblem


class Preparation:
    """Constrói o problema de decisão a partir de uma pasta de resultados da Entrega 2."""

    def __init__(self, data_file: Path, front_dir: Path, extra_criterion: str) -> None:
        """Args: data_file: Instância; front_dir: Resultados da Entrega 2; extra_criterion: Chave em EXTRA_CRITERIA."""
        self.case = load_case(data_file)
        self.union: UnionResult = ParetoUnion.from_directory(self.case, front_dir).build()
        self.problem = DecisionProblem.build(self.case, self.union.alternatives,
                                             build_criteria(extra_criterion))

    def summary(self) -> dict:
        """Contagens da união, faixas dos critérios e correlação de Spearman do critério extra."""
        values = self.problem.values
        extra = values.shape[1] - 1
        correlations = {c.key: float(spearmanr(values[:, extra], values[:, j]).statistic)
                        for j, c in enumerate(self.problem.criteria[:extra])}
        report = self.union.report
        return {
            "uniao": {"por_arquivo": report.per_file, "receitas_distintas": report.distinct_recipes,
                      "dominadas_removidas": report.dominated_removed, "finais": report.final},
            "criterios": {c.key: {"rotulo": c.label, "unidade": c.unit,
                                  "minimo": float(values[:, j].min()),
                                  "maximo": float(values[:, j].max())}
                          for j, c in enumerate(self.problem.criteria)},
            "spearman_do_criterio_extra": correlations,
            "todas_nao_dominadas_nos_criterios": bool(self.problem.nondominated_mask().all()),
        }

    def alternatives_table(self) -> list[dict]:
        """Uma linha por alternativa, com critérios, abordagens e receita."""
        return [{"id": a.identifier, "abordagens": list(a.approaches),
                 "criterios": {c.key: float(v) for c, v in zip(self.problem.criteria, row)},
                 "caminhoes_por_pilha_e_minerio": [list(r) for r in a.counts],
                 "origens": list(a.origins)}
                for a, row in zip(self.problem.alternatives, self.problem.values)]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dados", type=Path, default=DATA_FILE)
    parser.add_argument("--entrega2", type=Path, default=RESULTS_DIR / "entrega_2")
    parser.add_argument("--saida", type=Path, default=RESULTS_DIR / "entrega_3")
    parser.add_argument("--criterio-extra", choices=sorted(EXTRA_CRITERIA), default="homogeneidade")
    args = parser.parse_args()
    preparation = Preparation(args.dados, args.entrega2, args.criterio_extra)
    args.saida.mkdir(parents=True, exist_ok=True)
    write_json(args.saida / "uniao_nao_dominadas.json",
               {"resumo": preparation.summary(), "alternativas": preparation.alternatives_table()})
    print(f"{preparation.union.report.final} alternativas em {args.saida / 'uniao_nao_dominadas.json'}")


if __name__ == "__main__":
    main()
