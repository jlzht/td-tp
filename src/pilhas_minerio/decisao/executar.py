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
from .pipeline import ElectreThenAhp
from .preparar import Preparation


class FinalDecision:
    """Executa o modelo de decisão do caso base."""

    def __init__(self, preparation: Preparation, params: Hyperparameters) -> None:
        """Args: preparation: Problema de decisão; params: Hiperparâmetros lidos do arquivo."""
        keys = tuple(c.key for c in preparation.problem.criteria)
        if keys != params.criteria:
            raise ValueError(f"critérios do problema {keys} diferem dos dos pesos {params.criteria}")
        self.preparation = preparation
        self.params = params
        self.weights = params.criteria_weights()

    def run(self) -> dict:
        """Roda ELECTRE I e AHP com os valores base e monta o registro dos resultados."""
        problem, base = self.preparation.problem, self.params.pipeline
        result = ElectreThenAhp(base).evaluate(problem, self.weights)
        codes = problem.identifiers
        summary = result.details["resumo"]
        by_code = {row["id"]: row for row in self.preparation.alternatives_table()}
        chosen = codes[result.best]
        return {
            "pesos": {"criterios": list(self.params.criteria),
                      "valores": [float(w) for w in self.weights],
                      "qc": float(self.params.judgments_consistency_ratio())},
            "limiares": {"tau_c": base.tau_c, "tau_d": base.tau_d, "niveis_para_ahp": base.levels},
            "electre1": {"tamanho_niveis": summary["tamanho_niveis"],
                         "relacoes": result.details["electre"]["relacoes"],
                         "conjunto_ahp": summary["conjunto_ahp"]},
            "ahp": {"julgamento_local": base.local_judgment,
                    "prioridade_global": summary["prioridade_global"],
                    "qc_maximo_entre_alternativas": summary["qc_maximo_ahp"]},
            "ranking_final": [codes[i] for i in result.ranking[:summary["tamanho_ahp"]]],
            "escolhida": {"id": chosen, **by_code[chosen]},
            "alternativas_do_ahp": [by_code[c] for c in summary["conjunto_ahp"]],
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
    print(f"{len(record['electre1']['conjunto_ahp'])} alternativas no AHP; "
          f"escolhida: {record['escolhida']['id']}")


if __name__ == "__main__":
    main()
