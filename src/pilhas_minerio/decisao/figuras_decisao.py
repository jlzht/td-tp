"""Figuras da análise de sensibilidade, desenhadas a partir do registro em JSON."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Patch, Rectangle

from .hiperparametros import Hyperparameters

CRITERION_LABELS = {"custo": "custo", "desvio_sio2": "desvio de SiO₂",
                    "desvio_al2o3": "desvio de Al₂O₃", "homogeneidade": "homogeneidade"}


class SensitivityFigures:
    """Gera os gráficos da sensibilidade com uma cor fixa por alternativa vencedora."""

    def __init__(self, record: dict, params: Hyperparameters) -> None:
        """Args: record: Registro de ``SensitivityRun.run``; params: Hiperparâmetros usados."""
        self.record, self.params = record, params
        winners = {record["base"]["vencedora"]}
        for group in record["grupos"].values():
            winners.update(row["vencedora"] for row in group["cenarios"])
        palette = plt.get_cmap("tab20")
        self.colors = {code: palette(i % 20) for i, code in enumerate(sorted(winners))}

    def write(self, directory: Path) -> None:
        """Grava as quatro figuras em ``directory``."""
        directory.mkdir(parents=True, exist_ok=True)
        for name, draw in (("mapa_calor_limiares", self._heat_map),
                           ("sensibilidade_limiares", self._threshold_lines),
                           ("sensibilidade_pesos", self._weight_sweep),
                           ("sensibilidade_julgamentos", self._judgments)):
            fig = draw()
            fig.savefig(directory / f"{name}.pdf", format="pdf", bbox_inches="tight")
            plt.close(fig)

    @staticmethod
    def _text_color(rgba: tuple) -> str:
        """Branco sobre fundo escuro, preto sobre fundo claro."""
        red, green, blue = rgba[:3]
        return "white" if 0.299 * red + 0.587 * green + 0.114 * blue < 0.5 else "black"

    def _rows(self, group: str) -> list[dict]:
        return self.record["grupos"][group]["cenarios"]

    def _legend(self, ax: plt.Axes, codes: list[str], **kwargs) -> None:
        ax.legend(handles=[Patch(color=self.colors[c], label=c) for c in codes], frameon=False,
                  **kwargs)

    def _heat_map(self) -> plt.Figure:
        rows = self._rows("mapa_calor")
        support = sorted({round(r["tau_c"], 2) for r in rows})
        veto = sorted({round(r["tau_d"], 2) for r in rows})
        size = np.zeros((len(veto), len(support)), dtype=int)
        winner = [[""] * len(support) for _ in veto]
        for r in rows:
            i, j = veto.index(round(r["tau_d"], 2)), support.index(round(r["tau_c"], 2))
            size[i, j], winner[i][j] = r["alternativas_no_ahp"], r["vencedora"]
        fig, (left, right) = plt.subplots(1, 2, figsize=(14, 8))
        image = left.imshow(size, origin="lower", aspect="auto", cmap="viridis_r")
        fig.colorbar(image, ax=left, location="bottom", pad=0.14, fraction=0.04,
                     label="alternativas que seguem para o AHP")
        colored = np.array([[self.colors[c] for c in row] for row in winner])
        right.imshow(colored, origin="lower", aspect="auto")
        base = self.params.pipeline
        for ax in (left, right):
            ax.set_xticks(range(len(support)), [f"{x:.2f}" for x in support], rotation=60)
            ax.set_yticks(range(len(veto)), [f"{y:.2f}" for y in veto])
            ax.set(xlabel="apoio mínimo (tau_c)", ylabel="veto (tau_d)")
            ax.add_patch(Rectangle((support.index(round(base.tau_c, 2)) - 0.5,
                                    veto.index(round(base.tau_d, 2)) - 0.5), 1, 1, fill=False,
                                   edgecolor="black", linewidth=2.5))
        for i in range(len(veto)):
            for j in range(len(support)):
                left.text(j, i, str(size[i, j]), ha="center", va="center", fontsize=7,
                          color="white" if size[i, j] > size.max() / 2 else "black")
                right.text(j, i, winner[i][j].lstrip("A"), ha="center", va="center", fontsize=7,
                           color=self._text_color(self.colors[winner[i][j]]))
        left.set_title("Tamanho do conjunto enviado ao AHP")
        right.set_title("Alternativa escolhida")
        fig.suptitle("Veto e apoio (quadrado: valor base)", y=0.96)
        return fig

    def _threshold_lines(self) -> plt.Figure:
        fig, axes = plt.subplots(1, 2, figsize=(13, 4.8), sharey=True)
        base = self.params.pipeline
        specs = (("veto", "veto (tau_d)", base.tau_d), ("apoio", "apoio mínimo (tau_c)", base.tau_c))
        for ax, (group, label, base_value) in zip(axes, specs):
            rows = self._rows(group)
            xs = [r["valor"] for r in rows]
            sizes = [r["alternativas_no_ahp"] for r in rows]
            ax.bar(range(len(xs)), sizes, color=[self.colors[r["vencedora"]] for r in rows],
                   edgecolor=["black" if abs(x - base_value) < 1e-9 else "none" for x in xs],
                   linewidth=2)
            for i, r in enumerate(rows):
                ax.text(i, sizes[i] + 0.3, r["vencedora"], ha="center", fontsize=8)
            ticks = [f"{x:.2f}" for x in xs]
            ax.set_xticks(range(len(xs)), ticks, rotation=60)
            ax.set(xlabel=f"{label}  (contorno preto: base)",
                   title=f"Variação do {group}")
            ax.grid(axis="y", alpha=0.25)
        axes[0].set_ylabel("alternativas que seguem para o AHP")
        winners = sorted({r["vencedora"] for g in ("veto", "apoio") for r in self._rows(g)})
        self._legend(axes[1], winners, title="escolhida", loc="center left",
                     bbox_to_anchor=(1.0, 0.5))
        return fig

    def _weight_sweep(self) -> plt.Figure:
        rows = self._rows("pesos")
        criteria = list(self.params.criteria)
        fig, axes = plt.subplots(len(criteria), 1, figsize=(11, 1.5 * len(criteria) + 1.5),
                                 sharex=True)
        base_weights = dict(zip(criteria, self.record["base"]["pesos"]))
        for ax, key in zip(axes, criteria):
            sweep = [r for r in rows if r["criterio"] == key]
            step = 1.0 / (len(sweep) - 1)
            ax.bar([r["valor"] for r in sweep], 1, width=step,
                   color=[self.colors[r["vencedora"]] for r in sweep])
            ax.axvline(base_weights[key], color="black", linewidth=2)
            critical = self.record["pesos_criticos"][key]
            for side in ("abaixo", "acima"):
                if critical[side] is not None:
                    ax.axvline(critical[side], color="black", linestyle="--", linewidth=1.2)
            ax.set_yticks([])
            ax.set_ylabel(CRITERION_LABELS.get(key, key), rotation=0, ha="right", va="center")
            ax.set_xlim(-step / 2, 1 + step / 2)
        axes[-1].set_xlabel("peso do critério (os demais mantêm a proporção). "
                            "Linha cheia: peso base; tracejadas: onde a escolha muda")
        self._legend(axes[0], sorted({r["vencedora"] for r in rows}), ncol=6, title="escolhida",
                     loc="lower center", bbox_to_anchor=(0.5, 1.05))
        return fig

    def _judgments(self) -> plt.Figure:
        draws = self.record["grupos"]["sorteios"]
        single = self._rows("julgamentos")
        fig, (left, right) = plt.subplots(1, 2, figsize=(14, 4.8),
                                          gridspec_kw={"width_ratios": [1, 1.5], "wspace": 0.7})
        frequency = draws["frequencia_das_vencedoras"]
        codes = list(frequency)
        left.bar(range(len(codes)), [100 * frequency[c] for c in codes],
                 color=[self.colors[c] for c in codes])
        left.set_xticks(range(len(codes)), codes)
        left.set(ylabel="% dos sorteios", title=(
            f"Todos os julgamentos variando juntos "
            f"({self.record['descartados']['sorteios_aceitos']} sorteios aceitos)"))
        pairs = list(self.params.judgments)
        steps = sorted({*self.params.sensitivity.judgment_steps,
                        *(-s for s in self.params.sensitivity.judgment_steps)})
        by_cell = {(r["par"], r["degraus"]): r["vencedora"] for r in single}
        for i, pair in enumerate(pairs):
            for j, step in enumerate(steps):
                code = by_cell.get((pair, step))
                if code is None:
                    right.text(j, i, "descartado", ha="center", va="center", fontsize=7,
                               color="gray")
                    continue
                right.add_patch(Rectangle((j - 0.5, i - 0.5), 1, 1, color=self.colors[code]))
                right.text(j, i, code, ha="center", va="center", fontsize=8,
                           color=self._text_color(self.colors[code]))
        right.set_xlim(-0.5, len(steps) - 0.5)
        right.set_ylim(len(pairs) - 0.5, -0.5)
        right.set_xticks(range(len(steps)), [f"{s:+d}" for s in steps])
        right.set_yticks(range(len(pairs)), [" x ".join(CRITERION_LABELS.get(k, k) for k in p.split(":")) for p in pairs], fontsize=8)
        right.set(xlabel="degraus na escala de Saaty", title="Um julgamento por vez")
        return fig
