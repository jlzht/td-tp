"""Entrega 3, etapa 2: ELECTRE I, AHP e a alternativa escolhida.

Execute: python -m pilhas_minerio.decisao.executar
Lê configuracoes/decisao.json e a pasta de resultados da Entrega 2; grava
resultados/entrega_3/decisao.json.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from ..caminhos import CONFIG_DIR, DATA_FILE, RESULTS_DIR
from ..multiobjetivo import write_json
from .hiperparametros import Hyperparameters
from .metodos.electre1 import ElectreI
from .pipeline import ElectreThenAhp
from .preparar import Preparation


class FinalDecision:
    """Executa o modelo de decisão com os hiperparâmetros dados."""

    def __init__(self, preparation: Preparation, params: Hyperparameters) -> None:
        """Args: preparation: Problema de decisão; params: Hiperparâmetros lidos do arquivo."""
        keys = tuple(c.key for c in preparation.problem.criteria)
        if keys != params.criteria:
            raise ValueError(f"critérios do problema {keys} diferem dos dos pesos {params.criteria}")
        self.preparation = preparation
        self.params = params
        self.weights = params.criteria_weights()

    def run(self) -> dict:
        """Calibra tau_d se preciso, roda ELECTRE I e AHP e monta o registro dos resultados."""
        problem, params = self.preparation.problem, self.params
        calibration = None
        tau_d = params.tau_d
        if tau_d is None:
            calibration = ElectreI(params.tau_c, 1.0).calibrate_tau_d(
                problem, self.weights, params.target, params.tau_d_search)
            tau_d = calibration.tau_d
        method = ElectreThenAhp(params.tau_c, tau_d, params.local_judgment)
        result = method.evaluate(problem, self.weights)
        codes = problem.identifiers
        summary = result.details["resumo"]
        table = self.preparation.alternatives_table()
        by_code = {row["id"]: row for row in table}
        chosen = codes[result.best]
        return {
            "pesos": {"criterios": list(params.criteria),
                      "valores": [float(w) for w in self.weights],
                      "qc": float(params.judgments_consistency_ratio())},
            "limiares": {"tau_c": params.tau_c, "tau_d": tau_d,
                         "tau_d_calibrado": calibration is not None,
                         "alvo": params.target},
            "calibracao_tau_d": None if calibration is None else {
                "grade": list(calibration.grid), "tamanho_nucleo": list(calibration.sizes)},
            "electre1": {"tamanho_niveis": summary["tamanho_niveis"], "nucleo": summary["nucleo"],
                         "relacoes": result.details["electre"]["relacoes"]},
            "ahp": {"julgamento_local": params.local_judgment,
                    "prioridade_global": summary["prioridade_global"],
                    "qc_maximo_entre_alternativas": summary["qc_maximo_ahp"]},
            "ranking_final": [codes[i] for i in result.ranking[:len(summary["nucleo"])]],
            "escolhida": {"id": chosen, **by_code[chosen]},
            "alternativas_do_nucleo": [by_code[c] for c in summary["nucleo"]],
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dados", type=Path, default=DATA_FILE)
    parser.add_argument("--entrega2", type=Path, default=RESULTS_DIR / "entrega_2")
    parser.add_argument("--hiperparametros", type=Path, default=CONFIG_DIR / "decisao.json")
    parser.add_argument("--saida", type=Path, default=RESULTS_DIR / "entrega_3")
    args = parser.parse_args()
    params = Hyperparameters.load(args.hiperparametros)
    preparation = Preparation(args.dados, args.entrega2, params.extra_criterion)
    record = FinalDecision(preparation, params).run()
    args.saida.mkdir(parents=True, exist_ok=True)
    write_json(args.saida / "decisao.json", record)
    print(f"tau_d = {record['limiares']['tau_d']:.2f}; núcleo com {len(record['electre1']['nucleo'])} "
          f"alternativas; escolhida: {record['escolhida']['id']}")


if __name__ == "__main__":
    main()
