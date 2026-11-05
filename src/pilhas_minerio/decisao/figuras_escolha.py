"""Figuras da escolha: projeções com as alternativas de cada método e a solução final."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from ..gvns import evaluate
from ..multiobjetivo import plan_from_counts
from .preparar import Preparation

AXIS_LABELS = {"custo": "Custo (R$ milhões)", "desvio_sio2": "Desvio de SiO₂ (pp²)",
               "desvio_al2o3": "Desvio de Al₂O₃ (pp²)", "homogeneidade": "Afastamento da receita comum (H)"}
SHORT_LABELS = {"custo": "Custo", "desvio_sio2": "Desvio SiO₂", "desvio_al2o3": "Desvio Al₂O₃",
                "homogeneidade": "Receita (H)"}
GROUP_COLORS = ("#4c72b0", "#dd8452")


class ChoiceFigures:
    """Desenha as projeções dos três objetivos e a figura da solução escolhida."""

    def __init__(self, preparation: Preparation, record: dict) -> None:
        """Args: preparation: Problema de decisão; record: Registro de ``FinalDecision.run``."""
        self.preparation, self.record = preparation, record

    def write(self, directory: Path) -> None:
        """Grava ``projecoes_escolha.pdf`` e ``solucao_final.pdf`` em ``directory``."""
        directory.mkdir(parents=True, exist_ok=True)
        for name, fig in (("projecoes_escolha", self._projections()),
                          ("solucao_final", self._solution())):
            fig.savefig(directory / f"{name}.pdf", format="pdf", bbox_inches="tight")
            plt.close(fig)

    @staticmethod
    def _axis(values: np.ndarray, key: str) -> np.ndarray:
        return values / 1e6 if key == "custo" else values

    def _projections(self) -> plt.Figure:
        rows = self.record["tabela"]
        keys = ["custo", "desvio_sio2", "desvio_al2o3"]
        data = {k: np.array([r["criterios"][k] for r in rows]) for k in keys}
        in_ahp = np.array([r["no_ahp"] for r in rows])
        chosen = np.array([r["id"] == self.record["escolhida"]["id"] for r in rows])
        fig, axes = plt.subplots(1, 3, figsize=(15, 4.6))
        for ax, (a, b) in zip(axes, ((0, 1), (0, 2), (1, 2))):
            x, y = self._axis(data[keys[a]], keys[a]), self._axis(data[keys[b]], keys[b])
            ax.scatter(x[~in_ahp], y[~in_ahp], s=30, color="#c4c4c4", label="Não dominadas")
            ax.scatter(x[in_ahp & ~chosen], y[in_ahp & ~chosen], s=60, color="#4c72b0",
                       edgecolor="black", linewidth=0.6, label="Escolhidas pelo ELECTRE I")
            ax.scatter(x[chosen], y[chosen], s=260, marker="*", color="#c44e52", edgecolor="black",
                       linewidth=0.8, label="Escolhida pelo AHP")
            ax.set(xlabel=AXIS_LABELS[keys[a]], ylabel=AXIS_LABELS[keys[b]])
            ax.grid(alpha=0.25)
            ax.margins(0.08)
        handles, labels = axes[0].get_legend_handles_labels()
        fig.legend(handles, labels, loc="lower center", ncol=3, frameon=False)
        fig.subplots_adjust(bottom=0.24, wspace=0.28)
        return fig

    def _solution(self) -> plt.Figure:
        case = self.preparation.case
        chosen = self.record["escolhida"]
        counts = np.array(chosen["caminhoes_por_pilha_e_minerio"])
        result = evaluate(case, plan_from_counts(case, counts.tolist()))
        piles, ores = counts.shape
        fig = plt.figure(figsize=(15, 7.2))
        grid = fig.add_gridspec(2, 3, width_ratios=[2.3, 1, 1], hspace=0.5, wspace=0.7)
        heat = fig.add_subplot(grid[:, 0])
        heat.imshow(counts, cmap="Blues", vmin=0, vmax=counts.max(), aspect="auto",
                    interpolation="nearest")
        heat.set_xticks(range(ores), [f"M{j + 1}" for j in range(ores)], rotation=60, fontsize=8)
        heat.set_yticks(range(piles), [f"P{i + 1}" for i in range(piles)])
        heat.set_xlabel("Minério (número na célula = caminhões)")
        for p in range(piles):
            for j in range(ores):
                if counts[p, j]:
                    heat.text(j, p, str(counts[p, j]), ha="center", va="center", fontsize=8,
                              color="white" if counts[p, j] >= counts.max() / 2 else "#172554")
        for boundary in np.nonzero(np.diff(case.groups))[0]:
            heat.axhline(boundary + 0.5, color="#111827", linewidth=1.5)
        heat.set_title("Caminhões de cada minério em cada pilha")
        for slot, (values, name, field) in enumerate(((result.si, "SiO₂ (%)", "si"),
                                                       (result.al, "Al₂O₃ (%)", "al"))):
            self._quality(fig.add_subplot(grid[0, 1 + slot]), values, name, field)
        self._profile(fig.add_subplot(grid[1, 1:]))
        criteria = chosen["criterios"]
        fig.suptitle(f"Solução escolhida: {chosen['id']}   |   custo R$ {criteria['custo']:,.0f}   |   "
                     f"SiO₂ {criteria['desvio_sio2']:.2f} pp²   |   Al₂O₃ {criteria['desvio_al2o3']:.2f} pp²"
                     f"   |   H {criteria['homogeneidade']:.3f}", fontsize=12, y=0.98)
        return fig

    def _quality(self, ax: plt.Axes, values: tuple[float, ...], title: str, field: str) -> None:
        case = self.preparation.case
        groups = sorted(set(case.groups))
        ax.bar(range(len(values)), values, color=[GROUP_COLORS[groups.index(g)] for g in case.groups])
        for group in groups:
            members = [p for p, g in enumerate(case.groups) if g == group]
            sinter = case.sinters[group]
            low, target, high = (getattr(sinter, f"{field}_{k}") for k in ("min", "target", "max"))
            span = (members[0] - 0.5, members[-1] + 0.5)
            ax.hlines(target, *span, color="black", linewidth=1.8)
            ax.hlines([low, high], *span, color="black", linestyle="--", linewidth=1)
        ax.set_xticks(range(len(values)), [f"P{p + 1}" for p in range(len(values))], fontsize=7)
        ax.set_ylim(min(0, min(values)), max(values) * 1.15)
        ax.set(title=title)
        ax.text(0.5, -0.28, "linha cheia: alvo; tracejadas: mínimo e máximo", transform=ax.transAxes,
                ha="center", fontsize=7)

    def _profile(self, ax: plt.Axes) -> None:
        report = self.record["compromissos"]
        keys = list(report)
        positions = [report[k]["posicao_na_faixa"] for k in keys]
        ax.barh(range(len(keys)), positions, color="#c44e52")
        ax.set_yticks(range(len(keys)), [SHORT_LABELS.get(k, k) for k in keys])
        ax.invert_yaxis()
        ax.set_xlim(0, 1.0)
        for i, k in enumerate(keys):
            value = report[k]["valor_da_escolhida"]
            text = f"R$ {value / 1e6:.2f} mi" if k == "custo" else f"{value:.2f}"
            ax.text(min(positions[i] + 0.02, 0.8), i, text, va="center", fontsize=8)
        ax.set_xlabel("Posição na faixa das alternativas: 0 = melhor valor, 1 = pior valor")
        ax.set_title("Compromisso da escolha em cada critério")
        ax.grid(axis="x", alpha=0.25)
