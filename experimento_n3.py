"""Compara frações mínimas de caminhões alterados pela N3 na GVNS.

Para cada fração e cada objetivo, executa a GVNS com as mesmas sementes
(execuções 1..N), o que permite comparar as frações de forma pareada. Cada
execução concluída é gravada na hora em execucoes.csv; repetir o comando
retoma só o que falta, inclusive depois de um desligamento da máquina.

Execute: python experimento_n3.py --execucoes 30 --processos 8
Depois:  python experimento_n3.py --analisar
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
from multiprocessing import Pool
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from mono_objetivo import ITERATIONS, BASE_SEED, load_case, solve  # noqa: E402

FRACTIONS = (0.0, 0.2, 0.25, 0.3, 0.4, 0.5, 0.6, 0.75)
FIELDS = ["fracao", "objetivo", "execucao", "semente", "iteracoes", "avaliacoes",
          "segundos", "f1_rs", "f2_pp2", "f3_pp2", "valor", "ciclos_reparo",
          "reinicios_reparo", "nos_n3"]
UNITS = ("R$ mi", "pp²", "pp²")


def label(fraction: float) -> str:
    """Rótulo legível da regra de mínimo de mudanças."""
    return "2 fixo" if fraction == 0 else f"{fraction:.0%}".replace(".", ",")


class N3Experiment:
    """Executa e analisa o experimento da fração mínima da N3.

    Args:
        data_path: Instância em JSON.
        directory: Pasta de saída do experimento.
        iterations: Ciclos globais da GVNS por execução.
        base_seed: Semente base, a mesma para todas as frações.
    """

    def __init__(self, data_path: Path, directory: Path, iterations: int,
                 base_seed: int) -> None:
        self.data_path = data_path
        self.directory = directory
        self.iterations = iterations
        self.base_seed = base_seed
        self.runs_path = directory / "execucoes.csv"
        self.traces_path = directory / "convergencia.jsonl"

    def done(self) -> set[tuple[float, int, int]]:
        """Execuções já gravadas, para retomar sem repetir."""
        if not self.runs_path.exists():
            return set()
        with self.runs_path.open(encoding="utf-8") as file:
            return {(float(r["fracao"]), int(r["objetivo"]), int(r["execucao"]))
                    for r in csv.DictReader(file)}

    def run(self, fractions: tuple[float, ...], runs: int, processes: int) -> None:
        """Executa as combinações pendentes em paralelo e grava cada resultado.

        Args:
            fractions: Frações mínimas a testar.
            runs: Execuções por objetivo e fração.
            processes: Processos paralelos.
        """
        self.directory.mkdir(parents=True, exist_ok=True)
        (self.directory / "configuracao.json").write_text(json.dumps({
            "fracoes": list(fractions), "execucoes_por_objetivo": runs,
            "iteracoes_gvns": self.iterations, "semente_base": self.base_seed,
            "dados": self.data_path.name,
            "regra": "N3 altera ao menos max(2, ceil(fracao * caminhoes da pilha))",
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        finished = self.done()
        # Objetivo e execução variam mais devagar que a fração, para que as
        # frações avancem juntas e uma parada no meio deixe dados comparáveis.
        tasks = [(f, o, n) for n in range(1, runs + 1) for o in range(3)
                 for f in fractions if (f, o, n) not in finished]
        print(f"{len(finished)} execuções já gravadas; {len(tasks)} pendentes", flush=True)
        new_file = not self.runs_path.exists()
        with self.runs_path.open("a", newline="", encoding="utf-8") as runs_file, \
                self.traces_path.open("a", encoding="utf-8") as traces_file, \
                Pool(processes) as pool:
            writer = csv.writer(runs_file, lineterminator="\n")
            if new_file:
                writer.writerow(FIELDS)
            arguments = [(self.data_path, self.iterations, self.base_seed, *t) for t in tasks]
            for count, (row, trace) in enumerate(pool.imap_unordered(execute, arguments), 1):
                writer.writerow(row)
                runs_file.flush()
                traces_file.write(json.dumps({"fracao": row[0], "objetivo": row[1],
                                              "execucao": row[2], "trace": trace}) + "\n")
                traces_file.flush()
                print(f"[{count}/{len(tasks)}] fração {row[0]}, f{row[1] + 1}, "
                      f"execução {row[2]}: {row[10]:.6g} ({row[6]:.0f} s)", flush=True)

    def analyze(self) -> None:
        """Gera resumo.csv, testes estatísticos e os gráficos comparativos."""
        with self.runs_path.open(encoding="utf-8") as file:
            # Falhas do reparo têm valor NaN e ficam fora da análise.
            rows = [r for r in csv.DictReader(file) if r["valor"] == r["valor"]
                    and r["valor"].lower() != "nan"]
        fractions = sorted({float(r["fracao"]) for r in rows})
        summary, tests = [], []
        figure, axes = plt.subplots(1, 3, figsize=(15, 4.5))
        for objective in range(3):
            by_fraction = {f: {int(r["execucao"]): r for r in rows
                               if float(r["fracao"]) == f and int(r["objetivo"]) == objective}
                           for f in fractions}
            scale = 1e6 if objective == 0 else 1.0
            for f in fractions:
                values = [float(r["valor"]) for r in by_fraction[f].values()]
                evaluations = [int(r["avaliacoes"]) for r in by_fraction[f].values()]
                seconds = [float(r["segundos"]) for r in by_fraction[f].values()]
                if len(values) < 2:
                    continue
                summary.append([f"f{objective + 1}", f, len(values), min(values),
                                statistics.mean(values), statistics.median(values),
                                statistics.stdev(values), max(values),
                                statistics.mean(evaluations), statistics.mean(seconds)])
            # Só execuções presentes em todas as frações entram no teste pareado.
            common = sorted(set.intersection(*(set(v) for v in by_fraction.values())))
            if len(common) >= 5 and len(fractions) >= 3:
                from scipy.stats import friedmanchisquare
                samples = [[float(by_fraction[f][n]["valor"]) for n in common]
                           for f in fractions]
                statistic, p_value = friedmanchisquare(*samples)
                tests.append([f"f{objective + 1}", len(common), statistic, p_value])
            data = [[float(r["valor"]) / scale for r in by_fraction[f].values()]
                    for f in fractions]
            ax = axes[objective]
            ax.boxplot(data, showmeans=True)
            ax.set_xticks(range(1, len(fractions) + 1),
                          [label(f) for f in fractions], rotation=45)
            ax.set_title(f"f{objective + 1}")
            ax.set_xlabel("mínimo alterado pela N3")
            ax.set_ylabel(f"valor final ({UNITS[objective]})")
            ax.grid(axis="y", alpha=0.3)
        figure.tight_layout()
        figure.savefig(self.directory / "comparacao_fracoes.pdf")
        plt.close(figure)

        with (self.directory / "resumo.csv").open("w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file, lineterminator="\n")
            writer.writerow(["objetivo", "fracao", "execucoes", "minimo", "media", "mediana",
                             "desvio_padrao_amostral", "maximo", "avaliacoes_media",
                             "segundos_media"])
            writer.writerows(summary)
        with (self.directory / "teste_friedman.csv").open("w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file, lineterminator="\n")
            writer.writerow(["objetivo", "execucoes_pareadas", "estatistica", "p_valor"])
            writer.writerows(tests)
        print(f"Análise em {self.directory.resolve()}")


def execute(arguments: tuple) -> tuple[list, list]:
    """Uma execução da GVNS; função de módulo para o Pool poder serializá-la."""
    data_path, iterations, base_seed, fraction, objective, number = arguments
    case = load_case(data_path)
    run = solve(case, objective, number, iterations, base_seed, fraction)
    nan = float("nan")
    values = (nan, nan, nan) if run.failed else run.best_evaluation.objectives
    row = [fraction, objective, number, run.seed, run.iterations, run.evaluations,
           run.seconds, *values, values[objective], run.repair_cycles, run.restarts,
           run.n3_nodes]
    return row, {"avaliacoes": run.trace, "ciclos": run.cycle_trace}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--fracoes", type=float, nargs="+", default=list(FRACTIONS))
    parser.add_argument("--execucoes", type=int, default=30)
    parser.add_argument("--processos", type=int, default=4)
    parser.add_argument("--iteracoes", type=int, default=ITERATIONS)
    parser.add_argument("--semente-base", type=int, default=BASE_SEED)
    parser.add_argument("--dados", type=Path,
                        default=Path(__file__).with_name("dados_exemplo.json"))
    parser.add_argument("--saida", type=Path,
                        default=Path(__file__).with_name("resultados_experimento_n3"))
    parser.add_argument("--analisar", action="store_true",
                        help="só gera resumo, teste de Friedman e gráfico")
    args = parser.parse_args()
    experiment = N3Experiment(args.dados, args.saida, args.iteracoes, args.semente_base)
    if not args.analisar:
        experiment.run(tuple(args.fracoes), args.execucoes, args.processos)
    experiment.analyze()


if __name__ == "__main__":
    main()
