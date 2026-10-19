"""Escolha do critério de parada a partir de execuções longas da GVNS.

Uma execução com orçamento de N ciclos é idêntica, nos seus primeiros k
ciclos, a uma execução com orçamento k e a mesma semente. Por isso o melhor
valor registrado ao fim de cada ciclo de uma execução longa mostra exatamente
o que cada critério de parada teria devolvido, sem rodar tudo de novo:

- ciclos fixos: valor no ciclo k;
- estagnação: para no primeiro ciclo em que já se passaram K ciclos sem melhora.

Execute: python -m pilhas_minerio.criterio_parada
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
from pathlib import Path

from .caminhos import RESULTS_DIR

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

FIXED = (50, 100, 150, 200, 250, 300, 400, 500)
STAGNATION = (10, 20, 30, 50, 75, 100, 150)
NAMES = ("f1 (custo)", "f2 (desvio SiO₂)", "f3 (desvio Al₂O₃)")


class StoppingAnalysis:
    """Lê as curvas por ciclo e compara critérios de parada.

    Args:
        directory: Pasta com convergencia.jsonl gerado por calibracao_n3.py.
    """

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.curves: dict[int, list[list[tuple[int, int, float]]]] = {0: [], 1: [], 2: []}
        with (directory / "convergencia.jsonl").open(encoding="utf-8") as file:
            for line in file:
                record = json.loads(line)
                cycles = record["trace"]["ciclos"]
                if cycles:
                    self.curves[record["objetivo"]].append([tuple(c) for c in cycles])
        self.budget = min(curve[-1][0] for curves in self.curves.values() for curve in curves)

    @staticmethod
    def value_at(curve: list[tuple[int, int, float]], cycle: int) -> tuple[int, float]:
        """Avaliações acumuladas e melhor valor ao fim do ciclo pedido."""
        best = curve[0]
        for entry in curve:
            if entry[0] > cycle:
                break
            best = entry
        return best[1], best[2]

    @staticmethod
    def stop_by_stagnation(curve: list[tuple[int, int, float]],
                           patience: int) -> tuple[int, int, float, bool]:
        """Ciclo, avaliações e valor em que a regra de K ciclos sem melhora para.

        O último campo indica se a regra disparou antes do fim da execução
        longa; se não disparou, o valor é só um limite do que ela daria.
        """
        last_improvement = curve[0][0]
        best = curve[0][2]
        for cycle, evaluations, value in curve[1:]:
            if value < best - 1e-12:
                best, last_improvement = value, cycle
            if cycle - last_improvement >= patience:
                return cycle, evaluations, value, True
        cycle, evaluations, value = curve[-1]
        return cycle, evaluations, value, False

    def run(self) -> None:
        """Gera as tabelas CSV e a figura das curvas de convergência."""
        rows_fixed, rows_stagnation = [], []
        figure, axes = plt.subplots(1, 3, figsize=(15, 4.5))
        for objective, curves in self.curves.items():
            reference = min(curve[-1][2] for curve in curves)
            scale = abs(reference) if reference else 1.0

            def gap(value: float) -> float:
                return (value - reference) / scale

            for budget in (b for b in FIXED if b <= self.budget):
                points = [self.value_at(curve, budget) for curve in curves]
                values = [v for _, v in points]
                rows_fixed.append([
                    f"f{objective + 1}", budget, len(values), statistics.mean(values),
                    statistics.median(values), max(values),
                    statistics.mean(gap(v) for v in values),
                    sum(gap(v) < 1e-9 for v in values) / len(values),
                    statistics.mean(e for e, _ in points)])
            for patience in STAGNATION:
                stops = [self.stop_by_stagnation(curve, patience) for curve in curves]
                rows_stagnation.append([
                    f"f{objective + 1}", patience, len(stops),
                    statistics.mean(s[2] for s in stops),
                    statistics.mean(gap(s[2]) for s in stops),
                    sum(gap(s[2]) < 1e-9 for s in stops) / len(stops),
                    statistics.mean(s[0] for s in stops), max(s[0] for s in stops),
                    statistics.mean(s[1] for s in stops),
                    sum(not s[3] for s in stops)])

            cycles = list(range(curves[0][0][0], self.budget + 1))
            gaps = [[gap(self.value_at(curve, c)[1]) for curve in curves] for c in cycles]
            quartiles = [statistics.quantiles(g, n=4) if len(g) > 1 else [g[0]] * 3
                         for g in gaps]
            ax = axes[objective]
            ax.fill_between(cycles, [q[0] for q in quartiles], [q[2] for q in quartiles],
                            alpha=0.3, label="1º a 3º quartil")
            ax.plot(cycles, [statistics.median(g) for g in gaps], label="mediana")
            ax.plot(cycles, [statistics.mean(g) for g in gaps], "--", label="média")
            ax.set_yscale("symlog", linthresh=1e-6)
            ax.set_title(NAMES[objective])
            ax.set_xlabel("ciclos (reparo + GVNS)")
            ax.set_ylabel("distância relativa ao melhor valor encontrado")
            ax.grid(alpha=0.3)
            ax.legend()
        figure.tight_layout()
        figure.savefig(self.directory / "convergencia_por_ciclo.pdf")
        plt.close(figure)

        self._write("parada_ciclos_fixos.csv",
                    ["objetivo", "ciclos", "execucoes", "media", "mediana", "pior",
                     "distancia_relativa_media", "fracao_no_melhor", "avaliacoes_media"],
                    rows_fixed)
        self._write("parada_estagnacao.csv",
                    ["objetivo", "ciclos_sem_melhora", "execucoes", "media",
                     "distancia_relativa_media", "fracao_no_melhor", "ciclos_media",
                     "ciclos_maximo", "avaliacoes_media", "nao_dispararam"],
                    rows_stagnation)
        print(f"Análise em {self.directory.resolve()}")

    def _write(self, name: str, header: list[str], rows: list) -> None:
        with (self.directory / name).open("w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file, lineterminator="\n")
            writer.writerow(header)
            writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pasta", type=Path,
                        default=RESULTS_DIR / "calibracao" / "criterio_parada")
    StoppingAnalysis(parser.parse_args().pasta).run()


if __name__ == "__main__":
    main()
