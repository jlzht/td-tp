"""Gera exemplo.png, a figura da devolutiva enviada ao respondente da Cassotis.

Execute na raiz do projeto, depois de python -m pilhas_minerio.decisao.executar:
python entrevista/gerar_exemplo.py
Mostra quatro composições reais (a mais barata, uma intermediária, a melhor em sílica e a
melhor em alumina) na faixa das 73 candidatas, nas unidades que o formulário usa.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

FOLDER = Path(__file__).resolve().parent
RECORD = FOLDER.parent / "resultados" / "entrega_3" / "decisao.json"
CHOSEN = ["A01", "A27", "A53", "A73"]
NAMES = ["1  mais barata", "2  intermediária", "3  melhor em sílica", "4  melhor em alumina"]
COLORS = ["#c44e52", "#8172b3", "#4c72b0", "#55a868"]
ASPECTS = [
    ("Custo (R$ milhões)", lambda c: c["custo"] / 1e6, "{:.2f}"),
    ("Sílica: desvio típico\nao alvo (ponto percentual)", lambda c: math.sqrt(c["desvio_sio2"] / 10), "{:.2f}"),
    ("Alumina: desvio típico\nao alvo (ponto percentual)", lambda c: math.sqrt(c["desvio_al2o3"] / 10), "{:.2f}"),
    ("Receita: caminhões diferentes\nda receita comum (%)", lambda c: 100 * c["homogeneidade"] / 2, "{:.0f}"),
]


class ExampleFigure:
    """Desenha as quatro composições, um painel por aspecto; mais alto é melhor."""

    def __init__(self, record: dict) -> None:
        """Args: record: Registro de ``FinalDecision.run``, com a tabela das 73 alternativas."""
        self.criteria = {row["id"]: row["criterios"] for row in record["tabela"]}

    def write(self, path: Path) -> None:
        """Grava a figura em PNG."""
        fig, axes = plt.subplots(1, 4, figsize=(14, 5.2))
        for ax, (title, value, fmt) in zip(axes, ASPECTS):
            everything = [value(c) for c in self.criteria.values()]
            best, worst = min(everything), max(everything)
            for i, code in enumerate(CHOSEN):
                v = value(self.criteria[code])
                height = (worst - v) / (worst - best)
                ax.vlines(i, 0, height, color=COLORS[i], linewidth=3)
                ax.plot(i, height, "o", color=COLORS[i], markersize=14)
                ax.text(i, height + 0.07, fmt.format(v), ha="center", fontsize=11)
            ax.set_xticks(range(len(CHOSEN)), [str(i + 1) for i in range(len(CHOSEN))])
            ax.set_ylim(-0.08, 1.2)
            ax.set_yticks([0, 1], ["pior valor\nentre as 73", "melhor valor\nentre as 73"], fontsize=9)
            ax.set_title(title, fontsize=10)
            ax.grid(axis="y", alpha=0.25)
            for side in ("top", "right"):
                ax.spines[side].set_visible(False)
        fig.legend(handles=[plt.Line2D([], [], marker="o", linestyle="", color=c, markersize=10, label=n)
                            for c, n in zip(COLORS, NAMES)],
                   loc="lower center", ncol=4, frameon=False, fontsize=10)
        fig.suptitle("Quatro composições reais entre as 73 candidatas: quanto mais alto o ponto, "
                     "melhor o valor", fontsize=12, y=1.0)
        fig.subplots_adjust(bottom=0.2, wspace=0.45)
        fig.savefig(path, dpi=160, bbox_inches="tight")
        plt.close(fig)


if __name__ == "__main__":
    ExampleFigure(json.loads(RECORD.read_text(encoding="utf-8"))).write(FOLDER / "exemplo.png")
    print(f"figura em {FOLDER / 'exemplo.png'}")
