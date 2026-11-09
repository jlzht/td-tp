"""Gráficos Plotly do painel decisório."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from data import Data

BLUE = "#236EA4"
GREEN = "#29B09D"
GOLD = "#F4C542"
GRAY = "#71859A"

CRITERIA = {"f1": "Custo (R$ milhões)", "f2": "Desvio de SiO₂ (pp²)",
            "f3": "Desvio de Al₂O₃ (pp²)", "h": "Homogeneidade H"}

def _shade(alt: str, data: Data) -> str:
    if alt == data.winner:
        return GOLD
    if alt in data.electre:
        return GREEN
    return BLUE


def scatter(data: Data, filtered: pd.DataFrame, x: str, y: str) -> go.Figure:
    fig = go.Figure()
    regular = filtered.loc[~filtered.id.isin(set(data.electre) | {data.winner})]
    fig.add_trace(go.Scatter(
        x=regular[x], y=regular[y], mode="markers", name="Não dominadas",
        marker={"color": "#60A5FA", "size": 9, "opacity": .85},
        customdata=regular[["id", "f1", "f2", "f3", "h"]].to_numpy(),
        hovertemplate="<b>%{customdata[0]}</b><br>Custo: R$ %{customdata[1]:.2f} mi<br>SiO₂: %{customdata[2]:.4f} pp²<br>Al₂O₃: %{customdata[3]:.4f} pp²<br>H: %{customdata[4]:.4f}<extra></extra>",
    ))
    for ids, label, color, size, symbol in [
        ([a for a in data.electre if a != data.winner], "ELECTRE I", "#34D399", 12, "circle"),
        ([data.winner], "AHP", "#FACC15", 17, "star")
    ]:
        subset = filtered[filtered.id.isin(ids)]
        if subset.empty:
            continue
        fig.add_trace(go.Scatter(
            x=subset[x], y=subset[y], mode="markers", name=label,
            marker={"color": color, "size": size, "opacity": 1,
                    "symbol": symbol, "line": {"width": 1.5, "color": "#0F1826"}},
            customdata=subset[["id", "f1", "f2", "f3", "h"]].to_numpy(),
            hovertemplate="<b>%{customdata[0]}</b><br>Custo: R$ %{customdata[1]:.2f} mi<br>SiO₂: %{customdata[2]:.4f} pp²<br>Al₂O₃: %{customdata[3]:.4f} pp²<br>H: %{customdata[4]:.4f}<extra></extra>",
        ))
    fig.update_layout(height=380, margin={"t": 15, "b": 45, "l": 35, "r": 8},
                      legend={"orientation": "h", "y": 1.16, "x": 0},
                      dragmode="zoom",
                      xaxis_title=CRITERIA[x], yaxis_title=CRITERIA[y])
    return fig


def criterion_bars(data: Data, subset: pd.DataFrame, criterion: str) -> go.Figure:
    subset = subset.copy()
    fig = go.Figure(go.Bar(
        x=subset.id, y=subset[criterion],
        marker_color=[_shade(a, data) for a in subset.id],
        customdata=subset[["id", "f1", "f2", "f3", "h"]].to_numpy(),
        hovertemplate=("<b>%{customdata[0]}</b><br>"
                       + CRITERIA[criterion] + ": %{y:.4f}<extra></extra>"),
        text=([f"{v:.2f}" if criterion == "f1" else f"{v:.3f}"
               for v in subset[criterion]] if len(subset) <= 15 else None),
        textposition="inside", insidetextanchor="end",
        textfont={"color": "#FFFFFF", "size": 11},
    ))
    count = len(subset)
    fig.update_layout(
        height=350 if count <= 15 else 410,
        margin={"t": 25, "b": 75 if len(subset) > 10 else 50, "l": 55, "r": 18},
        xaxis_title="Alternativa", yaxis_title=CRITERIA[criterion],
        xaxis={"type": "category", "categoryorder": "array",
               "categoryarray": subset.id.tolist(),
               "tickangle": -45 if count > 10 else 0,
               "showticklabels": True,
               "tickfont": {"size": 9 if count > 25 else 11}},
        yaxis={"rangemode": "tozero"}, showlegend=False,
        dragmode="zoom",
    )
    return fig


def ranking_chart(df: pd.DataFrame, winner: str) -> go.Figure:
    # Prioridade AHP em ordem decrescente; identificador desempata empates.
    df = df.sort_values(["prioridade", "id"], ascending=[False, True], kind="stable")
    fig = go.Figure(go.Bar(y=df.id, x=df.prioridade, orientation="h",
                           marker_color=[GOLD if a == winner else GREEN for a in df.id],
                           text=df.prioridade.map(lambda x: f"{x:.4f}"), textposition="outside"))
    fig.update_layout(height=max(300, 50 * len(df) + 65), margin={"t": 20, "b": 40, "l": 40, "r": 65},
                      xaxis_title="Prioridade global AHP", xaxis={"rangemode": "tozero"},
                      yaxis={"categoryorder": "array", "categoryarray": df.id.tolist(),
                             "autorange": "reversed"})
    return fig


def weights_chart(weights: dict) -> go.Figure:
    df = pd.DataFrame({"critério": [CRITERIA[k] for k in ("f1", "f2", "f3", "h")],
                       "peso": [weights[k] * 100 for k in ("f1", "f2", "f3", "h")]})
    fig = px.bar(df, x="critério", y="peso", text=df.peso.map(lambda x: f"{x:.1f}%"),
                 color_discrete_sequence=[BLUE])
    fig.update_traces(textposition="outside")
    fig.update_layout(height=285, margin={"t": 15, "b": 65, "l": 45, "r": 5},
                      xaxis_title="", yaxis_title="Peso (%)")
    return fig


def composition(matrix: np.ndarray, data: Data) -> go.Figure:
    names = data.ores.id.tolist()
    piles = data.piles.id.tolist()
    labels = np.where(matrix > 0, matrix.astype(str), "")
    fig = go.Figure(go.Heatmap(
        z=matrix, x=names, y=piles,
        text=labels, texttemplate="%{text}",
        textfont={"size": 10, "color": "#F0F5FB"},
        colorscale=[[0, "#152335"], [.01, "#1C3551"], [.3, "#2E618F"], [.7, "#377DB5"], [1, "#76B4E8"]],
        hovertemplate="Pilha: %{y}<br>Minério: %{x}<br>Caminhões: %{z}<extra></extra>",
        colorbar={"title": "Caminhões"}, zmin=0, zmax=max(1, matrix.max()),
    ))
    fig.update_yaxes(autorange="reversed")
    fig.add_hline(y=4.5, line_color=GRAY, line_width=3)
    fig.update_layout(height=425, margin={"t": 18, "b": 50, "l": 38, "r": 18},
                      xaxis_title="Minério", yaxis_title="Pilha")
    return fig


def quality_chart(piles: pd.DataFrame, limits: pd.DataFrame,
                  sinter: int, criterion: str) -> go.Figure:
    """Show each pile's signed deviation from the Sinter target and valid band."""
    df = piles.loc[piles.sinter == sinter].copy()
    spec = limits.loc[(limits.sinter == sinter) & (limits.criterio == criterion)]
    if spec.empty:
        raise ValueError(f"Não há especificações para Sinter {sinter}/{criterion}.")
    lim = spec.iloc[0]
    df["desvio"] = df[criterion] - float(lim["alvo"])
    lower = float(lim["min"] - lim["alvo"])
    upper = float(lim["max"] - lim["alvo"])
    fig = go.Figure()
    fig.add_hrect(y0=lower, y1=upper, line_width=0,
                  fillcolor="rgba(35, 110, 164, 0.08)")
    fig.add_hline(y=0, line_dash="dash", line_color=BLUE,
                  annotation_text=f"Alvo {float(lim['alvo']):.2f}%",
                  annotation_position="top right")
    fig.add_hline(y=lower, line_dash="dot", line_color=GRAY,
                  annotation_text=f"Mín {float(lim['min']):.2f}%",
                  annotation_position="bottom left")
    fig.add_hline(y=upper, line_dash="dot", line_color=GRAY,
                  annotation_text=f"Máx {float(lim['max']):.2f}%",
                  annotation_position="top left")
    # Amarelo se o teor está a 0,03 p.p. ou menos de um limite;
    # azul nos demais casos. Violações continuam sinalizadas pela página.
    margins = np.minimum(df[criterion] - float(lim["min"]),
                         float(lim["max"]) - df[criterion])
    colors = [GOLD if margin <= 0.03 + 1e-9 else BLUE for margin in margins]
    fig.add_trace(go.Bar(
        x=df.pilha, y=df.desvio,
        marker_color=colors,
        customdata=df[[criterion]].to_numpy(),
        text=df.desvio.map(lambda x: f"{x:+.3f}"),
        textposition="inside", insidetextanchor="end",
        textfont={"color": "#FFFFFF", "size": 11},
        hovertemplate=("%{x}<br>Desvio: %{y:+.4f} p.p.<br>"
                       "Teor da mistura: %{customdata[0]:.4f}%<extra></extra>"),
    ))
    fig.update_layout(
        height=330, margin={"t": 38, "b": 40, "l": 55, "r": 12},
        title={"text": f"Sinter {sinter} · {'SiO₂' if criterion == 'sio2' else 'Al₂O₃'}",
               "font": {"size": 15}},
        xaxis_title="", yaxis_title="Desvio do alvo (p.p.)", showlegend=False,
        yaxis={"range": [min(lower, df.desvio.min(), 0) - 0.12,
                         max(upper, df.desvio.max(), 0) + 0.12]},
    )
    return fig
