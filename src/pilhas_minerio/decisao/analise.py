"""Entrega 3, etapa 3: análise de sensibilidade e suas figuras.

Execute: python -m pilhas_minerio.decisao.analise
Lê configuracoes/decisao.json e a pasta de resultados da Entrega 2; grava
resultados/entrega_3/sensibilidade.json e as figuras PDF ao lado.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from ..caminhos import CONFIG_DIR, DATA_FILE, RESULTS_DIR
from ..multiobjetivo import write_json
from .figuras_decisao import SensitivityFigures
from .hiperparametros import Hyperparameters
from .metodos.ahp import Ahp
from .pipeline import ElectreThenAhp
from .preparar import Preparation
from .sensibilidade import (CriticalWeight, JudgmentPerturbation, LevelVariants,
                            LocalJudgmentVariants, Scenario, SensitivityAnalysis,
                            SensitivityResult, ThresholdGrid, ThresholdLine, WeightSweep)


class SensitivityRun:
    """Roda todos os grupos de variações em torno do caso base."""

    def __init__(self, preparation: Preparation, params: Hyperparameters) -> None:
        """Args: preparation: Problema de decisão; params: Hiperparâmetros lidos do arquivo."""
        self.problem = preparation.problem
        self.params = params
        self.weights = params.criteria_weights()
        self.base = Scenario("base", self.problem, ElectreThenAhp(params.pipeline), self.weights,
                             {"tipo": "base"})
        self.base_outcome = SensitivityAnalysis(self.base, []).run().base

    def _group(self, variations: list[Scenario]) -> SensitivityResult:
        return SensitivityAnalysis(self.base, variations).run()

    @staticmethod
    def _describe(result: SensitivityResult) -> dict:
        return {"vencedora_base": result.base.winner,
                "fracao_em_que_a_base_vence": result.base_win_rate(),
                "frequencia_das_vencedoras": result.winner_frequency(),
                "cenarios": result.table()[1:]}

    def run(self) -> dict:
        """Executa os grupos e devolve o registro completo."""
        sens, base = self.params.sensitivity, self.params.pipeline
        problem, weights = self.problem, self.weights
        groups: dict[str, SensitivityResult] = {
            "veto": self._group(ThresholdLine("tau_d", sens.veto).scenarios(problem, base, weights)),
            "apoio": self._group(ThresholdLine("tau_c", sens.support).scenarios(problem, base, weights)),
            "niveis": self._group(LevelVariants(sens.levels).scenarios(problem, base, weights)),
            "modo_ahp": self._group(
                LocalJudgmentVariants(sens.local_judgments).scenarios(problem, base, weights)),
            "mapa_calor": self._group(ThresholdGrid(sens.heat_support, sens.heat_veto).scenarios(
                problem, base, weights)),
            "pesos": self._group(WeightSweep(sens.weight_sweep_steps).scenarios(
                problem, self.base.method, weights)),
            "referencia_ahp_sem_electre": self._group([Scenario(
                "ahp_sobre_todas", problem, Ahp(base.local_judgment), weights,
                {"tipo": "referencia"})]),
        }
        perturbation = JudgmentPerturbation(self.params.criteria, self.params.judgments,
                                            self.params.max_consistency_ratio)
        single, skipped_single = perturbation.one_at_a_time(problem, base, sens.judgment_steps)
        draws, skipped_draws = perturbation.random(problem, base, sens.judgment_samples,
                                                   sens.judgment_max_step, sens.seed)
        groups["julgamentos"] = self._group(single)
        groups["sorteios"] = self._group(draws)
        critical = CriticalWeight(problem, self.base.method, weights)
        record = {
            "base": {"vencedora": self.base_outcome.winner,
                     "pesos": [float(w) for w in weights],
                     "alternativas_no_ahp": self.base_outcome.summary["tamanho_ahp"]},
            "grupos": {name: self._describe(result) for name, result in groups.items()},
            "descartados": {"julgamentos_um_por_vez": skipped_single,
                            "sorteios_com_qc_acima_do_maximo": skipped_draws,
                            "sorteios_aceitos": len(draws)},
            "pesos_criticos": {c.key: dict(zip(("peso_base", "abaixo", "acima"),
                                               (float(weights[j]), *critical.find(j))))
                               for j, c in enumerate(problem.criteria)},
        }
        return record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dados", type=Path, default=DATA_FILE)
    parser.add_argument("--entrega2", type=Path, default=RESULTS_DIR / "entrega_2")
    parser.add_argument("--hiperparametros", type=Path, default=CONFIG_DIR / "decisao.json")
    parser.add_argument("--saida", type=Path, default=RESULTS_DIR / "entrega_3")
    args = parser.parse_args()
    params = Hyperparameters.load(args.hiperparametros)
    preparation = Preparation(args.dados, args.entrega2, params.extra_criterion)
    record = SensitivityRun(preparation, params).run()
    args.saida.mkdir(parents=True, exist_ok=True)
    write_json(args.saida / "sensibilidade.json", record)
    SensitivityFigures(record, params).write(args.saida)
    print(f"vencedora do caso base: {record['base']['vencedora']}")
    for name, group in record["grupos"].items():
        print(f"{name:28s} base vence em {100 * group['fracao_em_que_a_base_vence']:5.1f}% dos "
              f"{len(group['cenarios'])} cenários")


if __name__ == "__main__":
    main()
