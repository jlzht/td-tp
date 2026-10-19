"""Figuras PDF produzidas com Matplotlib."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


NAMES = ("Custo", "Desvio de SiO₂", "Desvio de Al₂O₃")


def write_convergence(path: Path, runs: list) -> None:
    """Sobrepõe as cinco curvas de melhor valor viável por objetivo."""
    fig, ax = plt.subplots(figsize=(9, 4.8))
    objective = runs[0].objective
    for run in runs:
        if not run.trace:
            continue
        x = [step for step, _ in run.trace] + [run.evaluations]
        y = [value for _, value in run.trace]
        y = [value / 1_000_000 if objective == 0 else value for value in y]
        ax.step(x, y + [y[-1]], where="post", label=f"Execução {run.number}")
    ax.set(title=f"Convergência: {NAMES[objective]}",
           xlabel="Avaliações de soluções candidatas",
           ylabel="R$ milhões" if objective == 0 else "pp²")
    ax.grid(alpha=0.25)
    ax.legend(ncol=5, loc="upper center", bbox_to_anchor=(0.5, -0.16), frameon=False)
    fig.savefig(path, format="pdf", bbox_inches="tight")
    plt.close(fig)


def write_solution(path: Path, case, run) -> None:
    """Mostra caminhões por minério e pilha, junto dos teores de cada pilha."""
    assert run.best_plan is not None and run.best_evaluation is not None
    counts = [[row.count(j) for j in range(len(case.ores))]
              for row in run.best_plan]
    result = run.best_evaluation
    fig, (ax, side) = plt.subplots(
        1, 2, figsize=(13, 5.6),
        gridspec_kw={"width_ratios": [5, 1.2], "wspace": 0.08})
    ax.imshow(counts, cmap="Blues", vmin=0, vmax=max(map(max, counts)),
              aspect="auto", interpolation="nearest")
    ax.set_xticks(range(len(case.ores)), [f"M{j + 1}" for j in range(len(case.ores))],
                  rotation=60, fontsize=8)
    ax.set_yticks(range(len(case.trucks)),
                  [f"P{i + 1}" for i in range(len(case.trucks))])
    ax.set_xlabel("Minério (número dentro da célula = caminhões)")
    for p, row in enumerate(counts):
        for j, value in enumerate(row):
            if value:
                ax.text(j, p, str(value), ha="center", va="center",
                        fontsize=8, color="white" if value >= 5 else "#172554")
    ax.axhline(4.5, color="#111827", linewidth=1.5)

    side.set(xlim=(0, 2), ylim=(len(case.trucks) - 0.5, -0.5))
    side.axis("off")
    side.text(0.2, -0.75, "SiO₂ (%)", fontsize=9, weight="bold")
    side.text(1.05, -0.75, "Al₂O₃ (%)", fontsize=9, weight="bold")
    for p in range(len(case.trucks)):
        side.text(0.2, p, f"{result.si[p]:.3f}", va="center", fontsize=9)
        side.text(1.05, p, f"{result.al[p]:.3f}", va="center", fontsize=9)
    side.axhline(4.5, color="#111827", linewidth=1.5)

    cost, si_error, al_error = result.objectives
    fig.suptitle(f"Melhor plano: {NAMES[run.objective]}", fontsize=14, weight="bold")
    fig.text(0.5, 0.92,
             f"Custo: R$ {cost:,.0f}   |   SiO₂: {si_error:.4f} pp²"
             f"   |   Al₂O₃: {al_error:.4f} pp²",
             ha="center", fontsize=9)
    fig.text(0.5, 0.02, "P1–P5: Sinter 1   |   P6–P10: Sinter 2",
             ha="center", fontsize=9)
    fig.subplots_adjust(top=0.79, bottom=0.23)
    fig.savefig(path, format="pdf", bbox_inches="tight")
    plt.close(fig)


def write_projections(directory: Path, method: str, points: list[dict], rounds: int) -> None:
    """Três projeções de um conjunto filtrado em 3D; cores identificam rodadas.

    Uma receita encontrada em várias rodadas é desenhada em cada cor com
    marcadores vazados de tamanhos diferentes, preservando a procedência.
    """
    labels = ("Custo (R$ milhões)", "Desvio de SiO₂ (pp²)", "Desvio de Al₂O₃ (pp²)")
    colors = plt.get_cmap("tab10")
    title = "Soma Ponderada" if method == "soma" else "ε-restrito"
    for a, b in ((0, 1), (0, 2), (1, 2)):
        fig, ax = plt.subplots(figsize=(7, 4.8))
        for n in range(1, rounds+1):
            selected = [p for p in points if any(o["rodada"] == n for o in p["origens"])]
            x = [p["objetivos"][a] / (1e6 if a == 0 else 1) for p in selected]
            y = [p["objetivos"][b] for p in selected]
            ax.scatter(x, y, facecolors="none", edgecolors=[colors((n-1)%10)],
                       s=35+25*(n-1), linewidths=1.3, label=f"Rodada {n}")
        if not points:
            ax.text(.5, .5, "Nenhuma solução admissível encontrada", ha="center",
                    va="center", transform=ax.transAxes)
        ax.set(title=f"{title}: soluções não dominadas nos três objetivos",
               xlabel=labels[a], ylabel=labels[b])
        ax.grid(alpha=.25)
        ax.legend(loc="upper center", bbox_to_anchor=(.5, -.16), ncol=min(rounds, 5), frameon=False)
        fig.savefig(directory/f"{method}_f{a+1}_f{b+1}.pdf", format="pdf", bbox_inches="tight")
        plt.close(fig)


def write_front_3d(path: Path, fronts: dict[str, list[dict]]) -> None:
    """Conjuntos não dominados das abordagens no espaço dos três objetivos.

    Duas vistas do mesmo espaço e linhas verticais até o menor desvio de
    Al₂O₃ dão noção de profundidade, que uma única perspectiva estática não
    transmite.
    """
    styles = {"soma": ("Soma Ponderada", "tab:blue", "o"),
              "epsilon": ("ε-restrito", "tab:red", "^")}
    points = [p for front in fronts.values() for p in front]
    floor = min(p["objetivos"][2] for p in points) if points else 0.0
    fig = plt.figure(figsize=(13, 6))
    for panel, azimuth in enumerate((-58, 32), start=1):
        ax = fig.add_subplot(1, 2, panel, projection="3d")
        for method, front in fronts.items():
            label, color, marker = styles[method]
            x = [p["objetivos"][0] / 1e6 for p in front]
            y = [p["objetivos"][1] for p in front]
            z = [p["objetivos"][2] for p in front]
            for xi, yi, zi in zip(x, y, z):
                ax.plot([xi, xi], [yi, yi], [floor, zi], color=color, alpha=0.25,
                        linewidth=0.8)
            ax.scatter(x, y, z, color=color, marker=marker, s=40, depthshade=False,
                       edgecolors="black", linewidths=0.4,
                       label=f"{label} ({len(front)} receitas)")
        ax.set_xlabel("Custo (R$ milhões)", labelpad=8)
        ax.set_ylabel("Desvio de SiO₂ (pp²)", labelpad=8)
        ax.set_zlabel("Desvio de Al₂O₃ (pp²)", labelpad=8)
        ax.view_init(elev=22, azim=azimuth)
        if panel == 1:
            ax.legend(loc="upper left")
    fig.subplots_adjust(left=0.02, right=0.95, wspace=0.12)
    fig.savefig(path, format="pdf", bbox_inches="tight", pad_inches=0.3)
    plt.close(fig)
