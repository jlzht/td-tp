"""Entrega 3: comparação de atributos candidatos a critério extra.

Execute: python -m pilhas_minerio.decisao.candidatos
Mede, nas alternativas da união das frentes, a correlação de Spearman de cada candidato,
orientado para minimização, com custo, desvio de SiO2 e desvio de Al2O3. Correlação
negativa indica conflito com o objetivo. Grava resultados/entrega_3/criterios_candidatos.json.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Callable

import numpy as np
from scipy.stats import spearmanr

from ..caminhos import DATA_FILE, RESULTS_DIR
from ..multiobjetivo import write_json
from .preparar import Preparation

Attribute = Callable[[np.ndarray, np.ndarray], float]


class CandidateStudy:
    """Calcula os atributos candidatos e suas correlações com os três objetivos."""

    def __init__(self, preparation: Preparation, data_file: Path) -> None:
        """Args: preparation: Problema de decisão; data_file: Instância (fornece FeT e disponibilidade)."""
        raw = json.loads(data_file.read_text(encoding="utf-8"))
        ores = sorted(raw["minerios"], key=lambda o: o["id"])
        self.preparation = preparation
        self.fet = np.array([o["fet"] for o in ores], dtype=float)
        self.maximum = np.array([o["max"] for o in ores], dtype=float)
        self.groups = np.array(preparation.case.groups)

    def attributes(self) -> dict[str, tuple[bool, Attribute]]:
        """Nome -> (maior é melhor, função de ``(caminhões por pilha e minério)`` em valor)."""
        def pile_fet(counts: np.ndarray) -> np.ndarray:
            return (counts @ self.fet) / counts.sum(axis=1)

        def group_fet_spread(counts: np.ndarray) -> float:
            fet = pile_fet(counts)
            return float(np.mean([np.abs(fet[self.groups == g] - fet[self.groups == g].mean()).mean()
                                  for g in np.unique(self.groups)]))

        def at_maximum(counts: np.ndarray) -> float:
            use = counts.sum(axis=0)
            return float(((use >= self.maximum) & (self.maximum > 0)).sum())

        return {
            "Teor de ferro médio": (True, lambda c: float((c @ self.fet).sum() / c.sum())),
            "Teor de ferro da pior pilha": (True, lambda c: float(pile_fet(c).min())),
            "Variação do ferro entre pilhas do equipamento": (False, group_fet_spread),
            "Maior uso da disponibilidade de um minério": (
                False, lambda c: float((c.sum(axis=0) / self.maximum).max())),
            "Minérios no limite de disponibilidade": (False, at_maximum),
            "Minérios distintos no plano": (False, lambda c: float((c.sum(axis=0) > 0).sum())),
            "Minérios distintos por pilha (média)": (False, lambda c: float((c > 0).sum(axis=1).mean())),
        }

    def run(self) -> dict:
        """Correlação de Spearman de cada candidato com f1, f2 e f3, e se continua não dominado."""
        problem = self.preparation.problem
        objectives = problem.values[:, :3]
        homogeneity = problem.values[:, 3]
        study = {"Afastamento da receita comum (H)": self._row(homogeneity, objectives)}
        counts = [np.array(a.counts, dtype=float) for a in problem.alternatives]
        for name, (larger_is_better, function) in self.attributes().items():
            values = np.array([function(c) for c in counts])
            study[name] = self._row(-values if larger_is_better else values, objectives)
        return study

    @staticmethod
    def _row(minimized: np.ndarray, objectives: np.ndarray) -> dict:
        if np.ptp(minimized) == 0:
            return {"constante": True}
        matrix = np.column_stack([objectives, minimized])
        tolerance = 1e-9
        dominated = sum(bool(np.any(np.all(matrix <= point + tolerance, axis=1)
                                    & np.any(matrix < point - tolerance, axis=1)))
                        for point in matrix)
        return {"constante": False,
                "spearman_com_custo": float(spearmanr(minimized, objectives[:, 0]).statistic),
                "spearman_com_desvio_sio2": float(spearmanr(minimized, objectives[:, 1]).statistic),
                "spearman_com_desvio_al2o3": float(spearmanr(minimized, objectives[:, 2]).statistic),
                "alternativas_dominadas_com_o_candidato": int(dominated)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dados", type=Path, default=DATA_FILE)
    parser.add_argument("--entrega2", type=Path, default=RESULTS_DIR / "entrega_2")
    parser.add_argument("--saida", type=Path, default=RESULTS_DIR / "entrega_3")
    args = parser.parse_args()
    preparation = Preparation(args.dados, args.entrega2, "homogeneidade")
    study = CandidateStudy(preparation, args.dados).run()
    args.saida.mkdir(parents=True, exist_ok=True)
    write_json(args.saida / "criterios_candidatos.json", study)
    for name, row in study.items():
        if row["constante"]:
            print(f"{name}: constante nas alternativas")
        else:
            print(f"{name}: custo {row['spearman_com_custo']:+.2f}, SiO2 "
                  f"{row['spearman_com_desvio_sio2']:+.2f}, Al2O3 {row['spearman_com_desvio_al2o3']:+.2f}")


if __name__ == "__main__":
    main()
