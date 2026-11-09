"""Entrega 3, etapa 2: ELECTRE I, AHP e a alternativa escolhida.

Execute: python -m pilhas_minerio.decisao.executar
Lê configuracoes/decisao.json e a pasta de resultados da Entrega 2; grava em
resultados/entrega_3/ o registro da decisão (decisao.json), a tabela de todas as
alternativas (tabela_alternativas.csv e .tex) e as figuras da escolha.
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import numpy as np

from ..caminhos import CONFIG_DIR, DATA_FILE, RESULTS_DIR
from ..multiobjetivo import write_json
from .figuras_escolha import ChoiceFigures
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
                      "qc": float(self.params.judgments_consistency_ratio()),
                      "qc_maximo": self.params.max_consistency_ratio,
                      "qc_aceito_acima_do_maximo": self.params.accept_above_limit},
            "limiares": {"tau_c": base.tau_c, "tau_d": base.tau_d, "niveis_para_ahp": base.levels},
            "electre1": {"tamanho_niveis": summary["tamanho_niveis"],
                         "relacoes": result.details["electre"]["relacoes"],
                         "conjunto_ahp": summary["conjunto_ahp"]},
            "ahp": {"julgamento_local": base.local_judgment,
                    "prioridade_global": summary["prioridade_global"],
                    "qc_maximo_entre_alternativas": summary["qc_maximo_ahp"]},
            "desempate": {"tolerancia_relativa": base.tie_tolerance,
                          "alternativas_empatadas": summary["empatadas"]},
            "ranking_final": [codes[i] for i in result.ranking[:summary["tamanho_ahp"]]],
            "escolhida": {"id": chosen, **by_code[chosen]},
            "alternativas_do_ahp": [by_code[c] for c in summary["conjunto_ahp"]],
            "compromissos": self._compromises(result.best),
            "tabela": self._table(result),
        }

    def _table(self, result) -> list[dict]:
        """Uma linha por alternativa: critérios, nível no ELECTRE I e, se foi ao AHP, prioridade e posição."""
        problem = self.preparation.problem
        codes = problem.identifiers
        level = result.details["electre"]["nivel_de"]
        priority = result.details["resumo"]["prioridade_global"]
        position = {codes[i]: place + 1 for place, i in enumerate(result.ranking)}
        return [{"id": a.identifier, "abordagens": list(a.approaches),
                 "criterios": {c.key: float(v) for c, v in zip(problem.criteria, row)},
                 "nivel_electre": int(level[i]) + 1, "no_ahp": a.identifier in priority,
                 "prioridade_ahp": priority.get(a.identifier),
                 "posicao_final": position[a.identifier] if a.identifier in priority else None}
                for i, (a, row) in enumerate(zip(problem.alternatives, problem.values))]

    def _compromises(self, chosen: int) -> dict:
        """Onde a escolhida está na faixa de cada critério e o que muda ao trocá-la pela melhor dele."""
        problem = self.preparation.problem
        codes, values, losses = problem.identifiers, problem.values, problem.losses()
        report = {}
        for j, criterion in enumerate(problem.criteria):
            best = int(np.argmin(losses[:, j]))
            worst = int(np.argmax(losses[:, j]))
            report[criterion.key] = {
                "valor_da_escolhida": float(values[chosen, j]),
                "melhor_valor": float(values[best, j]), "pior_valor": float(values[worst, j]),
                "posicao_na_faixa": float(losses[chosen, j]),
                "melhor_alternativa": codes[best],
                "ao_trocar_pela_melhor": {
                    k.key: {"variacao": float(values[best, m] - values[chosen, m]),
                            "variacao_relativa": float((values[best, m] - values[chosen, m])
                                                       / abs(values[chosen, m]))}
                    for m, k in enumerate(problem.criteria)}}
        return report


def write_table(path: Path, rows: list[dict], criteria: tuple[str, ...]) -> None:
    """Grava a tabela de todas as alternativas em CSV, com ponto decimal."""
    fields = ["id", *criteria, "nivel_electre", "no_ahp", "prioridade_ahp", "posicao_final",
              "abordagens"]
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({"id": row["id"], **row["criterios"],
                             "nivel_electre": row["nivel_electre"],
                             "no_ahp": "sim" if row["no_ahp"] else "não",
                             "prioridade_ahp": "" if row["prioridade_ahp"] is None
                             else f"{row['prioridade_ahp']:.6f}",
                             "posicao_final": row["posicao_final"] or "",
                             "abordagens": "+".join(row["abordagens"])})


def write_latex_table(path: Path, rows: list[dict], chosen: str) -> None:
    """Grava a tabela das alternativas em LaTeX, em dois blocos lado a lado.

    Só o ambiente ``tabular``: a legenda e o rótulo ficam no relatório. Vírgula decimal,
    como no restante do texto; a escolhida sai em negrito.
    """
    def number(value: float, digits: int) -> str:
        return f"{value:.{digits}f}".replace(".", "{,}")

    def cells(row: dict) -> list[str]:
        c = row["criterios"]
        priority = "--" if row["prioridade_ahp"] is None else number(row["prioridade_ahp"], 3)
        values = [row["id"], number(c["custo"] / 1e6, 2), number(c["desvio_sio2"], 2),
                  number(c["desvio_al2o3"], 2), number(c["homogeneidade"], 3),
                  str(row["nivel_electre"]), priority]
        return [f"\\textbf{{{v}}}" for v in values] if row["id"] == chosen else values

    half = (len(rows) + 1) // 2
    header = ["Alt.", "$f_1$", "$f_2$", "$f_3$", "$H$", "Nív.", "$g$"]
    lines = ["\\begin{tabular}{l r r r r c r @{\\hspace{1.2em}} l r r r r c r}", "\\toprule",
             " & ".join(f"\\textbf{{{h}}}" for h in header * 2) + " \\\\", "\\midrule"]
    for i in range(half):
        left = cells(rows[i])
        right = cells(rows[half + i]) if half + i < len(rows) else [""] * len(header)
        lines.append(" & ".join(left + right) + " \\\\")
    lines += ["\\bottomrule", "\\end{tabular}"]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


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
    write_table(args.saida / "tabela_alternativas.csv", record["tabela"], params.criteria)
    write_latex_table(args.saida / "tabela_alternativas.tex", record["tabela"], record["escolhida"]["id"])
    ChoiceFigures(preparation, record).write(args.saida)
    print(f"{len(record['electre1']['conjunto_ahp'])} alternativas no AHP; "
          f"escolhida: {record['escolhida']['id']}")


if __name__ == "__main__":
    main()
