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
