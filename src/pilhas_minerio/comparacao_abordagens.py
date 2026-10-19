"""Compara os conjuntos não dominados da Soma Ponderada e do ε-restrito.

Lê a pasta de saída de multiobjetivo.py e calcula, por abordagem e por rodada:
- número de receitas não dominadas e faixa de cada objetivo;
- hipervolume no espaço normalizado, com ponto de referência comum;
- cobertura C(A, B): fração dos pontos de B dominados ou igualados por A;
- contribuição de cada abordagem para o conjunto não dominado da união.

Execute: python -m pilhas_minerio.comparacao_abordagens
"""
from __future__ import annotations

import argparse
import csv
import json
import statistics
from pathlib import Path

from .caminhos import RESULTS_DIR
from .multiobjetivo import dominates

METHODS = ("soma", "epsilon")
REFERENCE = (1.1, 1.1, 1.1)


def hypervolume_2d(points: list[tuple[float, float]], reference: tuple[float, float]) -> float:
    """Área dominada por pontos 2D (minimização) até o ponto de referência."""
    area, best_y = 0.0, reference[1]
    for x, y in sorted(p for p in points if p[0] < reference[0] and p[1] < reference[1]):
        if y < best_y:
            area += (reference[0] - x) * (best_y - y)
            best_y = y
    return area


def hypervolume_3d(points: list[tuple[float, float, float]],
                   reference: tuple[float, float, float] = REFERENCE) -> float:
    """Volume dominado em 3D por fatias no terceiro objetivo (minimização).

    Entre dois valores consecutivos de f3, a seção dominada é a área 2D dos
    pontos com f3 até o início da fatia; somar área vezes espessura dá o volume.
    """
    inside = sorted((p for p in points if all(v < r for v, r in zip(p, reference))),
                    key=lambda p: p[2])
    volume = 0.0
    for index, point in enumerate(inside):
        top = inside[index + 1][2] if index + 1 < len(inside) else reference[2]
        if top > point[2]:
            section = hypervolume_2d([(p[0], p[1]) for p in inside[:index + 1]],
                                     reference[:2])
            volume += section * (top - point[2])
    return volume


def coverage(a: list[dict], b: list[dict]) -> float:
    """Fração dos pontos de b dominados ou com objetivos iguais a algum ponto de a."""
    if not b:
        return float("nan")

    def covered(point: dict) -> bool:
        return any(dominates(other["objetivos"], point["objetivos"]) or
                   other["objetivos"] == point["objetivos"] for other in a)

    return sum(covered(point) for point in b) / len(b)


class ApproachComparison:
    """Calcula e grava as métricas de comparação entre as duas abordagens.

    Args:
        directory: Pasta de saída de multiobjetivo.py.
    """

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.fronts = {m: self._load(f"nao_dominadas_{m}.json") for m in METHODS}
        self.rounds = {m: self._load(f"nao_dominadas_rodadas_{m}.json") for m in METHODS}

    def _load(self, name: str):
        path = self.directory / name
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    def run(self) -> None:
        """Grava comparacao_abordagens.csv e comparacao_rodadas.csv."""
        methods = [m for m in METHODS if self.fronts[m] is not None]
        union = [dict(p, metodo=m) for m in methods for p in self.fronts[m]]
        joint = [p for p in union if not any(
            dominates(o["objetivos"], p["objetivos"]) for o in union)]
        rows = []
        for m in methods:
            front = self.fronts[m]
            others = [o for o in methods if o != m]
            rows.append([
                m, len(front),
                *[f(p["objetivos"][q] for p in front) for q in range(3) for f in (min, max)],
                hypervolume_3d([tuple(p["normalizados"]) for p in front]),
                coverage(front, self.fronts[others[0]]) if others else "",
                sum(p["metodo"] == m for p in joint),
            ])
        self._write("comparacao_abordagens.csv",
                    ["abordagem", "receitas_nao_dominadas", "f1_min", "f1_max",
                     "f2_min", "f2_max", "f3_min", "f3_max", "hipervolume_normalizado",
                     "cobertura_sobre_a_outra", "pontos_na_uniao_nao_dominada"], rows)

        round_rows = []
        for m in methods:
            volumes = []
            for number, front in sorted(self.rounds[m].items(), key=lambda i: int(i[0])):
                volume = hypervolume_3d([tuple(p["normalizados"]) for p in front])
                volumes.append(volume)
                round_rows.append([m, number, len(front), volume])
            if len(volumes) > 1:
                round_rows.append([m, "media", "", statistics.mean(volumes)])
                round_rows.append([m, "desvio_padrao", "", statistics.stdev(volumes)])
        self._write("comparacao_rodadas.csv",
                    ["abordagem", "rodada", "receitas_nao_dominadas", "hipervolume_normalizado"],
                    round_rows)
        for row in rows:
            print(f"{row[0]}: {row[1]} não dominadas, hipervolume {row[8]:.4f}, "
                  f"cobertura {row[9]}, {row[10]} pontos na união")
        print(f"Métricas em {self.directory.resolve()}")

    def _write(self, name: str, header: list[str], rows: list) -> None:
        with (self.directory / name).open("w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file, lineterminator="\n")
            writer.writerow(header)
            writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pasta", type=Path, default=RESULTS_DIR / "entrega_2")
    ApproachComparison(parser.parse_args().pasta).run()


if __name__ == "__main__":
    main()
