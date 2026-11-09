"""Painel de decisão e composição de pilhas de minério."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from charts import (CRITERIA, composition, criterion_bars,
                    quality_chart, ranking_chart, scatter, weights_chart)
from data import Data, evaluate_recipe, load


st.set_page_config(page_title="Otimização de custo e qualidade na formação de pilhas de minério", page_icon="⛏", layout="wide",
                   initial_sidebar_state="expanded")


ROOT = Path(__file__).resolve().parents[1]
def result_files() -> list[Path]:
    paths = [ROOT / "dados" / "dados_exemplo.json"]
    for folder in (ROOT / "resultados" / "entrega_2",
                   ROOT / "resultados" / "entrega_3"):
        if folder.is_dir():
            paths.extend(sorted(folder.rglob("*.json")))
            paths.extend(sorted(folder.rglob("*.csv")))
    return paths



@st.cache_data(show_spinner="Carregando resultados do projeto…")
def dashboard_data(file_signatures: tuple) -> Data:
    return load(ROOT)


try:
    signatures = tuple((str(path), path.stat().st_mtime_ns if path.exists() else None)
                       for path in result_files())
    data = dashboard_data(signatures)
except (OSError, ValueError, KeyError, TypeError) as error:
    st.error("Não foi possível abrir os resultados da otimização.")
    st.write(str(error))
    st.stop()

ids = data.alternatives.id.tolist()
if "view" not in st.session_state:
    st.session_state.view = "Soluções não dominadas"

NAVIGATION = ["Soluções não dominadas", "Comparação de alternativas", "Decisão multicritério", "Solução final"]

with st.sidebar:
    st.title("Otimização de custo e qualidade na formação de pilhas de minério")
    st.caption("Decisão de sinterização")
    st.divider()
    page = st.radio("Navegação", NAVIGATION, key="view", label_visibility="collapsed")
    st.divider()
    st.caption("Plano recomendado")
    st.metric("Alternativa", data.winner)
    st.metric("Alternativas não dominadas", len(data.alternatives))
    st.metric("Selecionadas no ELECTRE I", len(data.electre))

st.title(page)

if data.notices:
    with st.expander("Avisos de consistência dos resultados", expanded=False):
        for notice in data.notices:
            st.warning(notice)



def table_options(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.rename(columns={"id": "Alternativa", "f1": "Custo (R$ mi)",
                                 "f2": "SiO₂ (pp²)", "f3": "Al₂O₃ (pp²)",
                                 "h": "Homogeneidade H"})



def pareto_page() -> None:
    st.caption("Soluções não dominadas nos três pares de objetivos.")
    a, b, c = st.columns(3)
    a.metric("Não dominadas", len(data.alternatives))
    b.metric("ELECTRE I", len(data.electre))
    c.metric("AHP", data.winner)

    min_cost = float(data.alternatives["f1"].min())
    max_cost = float(data.alternatives["f1"].max())
    with st.expander("Filtrar alternativas", expanded=False):
        if min_cost < max_cost:
            cost_range = st.slider(
                "Custo (R$ milhões)", min_value=min_cost, max_value=max_cost,
                value=(min_cost, max_cost), step=0.01,
                key="pareto_cost_range",
            )
        else:
            st.caption(f"Todas as alternativas custam R$ {min_cost:.2f} milhões.")
            cost_range = (min_cost, max_cost)
    subset = data.alternatives.loc[data.alternatives["f1"].between(*cost_range)]
    if subset.empty:
        st.warning("Nenhuma alternativa atende à faixa de custo selecionada.")
        return

    columns = st.columns(3, gap="small")
    for col, (x, y, title, token) in zip(columns, [
        ("f1", "f2", "Custo × SiO₂", "12"),
        ("f1", "f3", "Custo × Al₂O₃", "13"),
        ("f2", "f3", "SiO₂ × Al₂O₃", "23")]):
        with col:
            st.subheader(title)
            st.plotly_chart(scatter(data, subset, x, y),
                            use_container_width=True, key="pareto_" + token)

    st.subheader("Alternativas")
    show = table_options(subset[["id", "f1", "f2", "f3", "h"]].copy())
    st.dataframe(show, hide_index=True, use_container_width=True,
                          column_config={"Custo (R$ mi)": st.column_config.NumberColumn(format="%.2f"),
                                         "SiO₂ (pp²)": st.column_config.NumberColumn(format="%.4f"),
                                         "Al₂O₃ (pp²)": st.column_config.NumberColumn(format="%.4f"),
                                         "Homogeneidade H": st.column_config.NumberColumn(format="%.4f")})


def comparison_page() -> None:
    st.caption("Comparação dos quatro critérios para todas as alternativas não dominadas. "
               "Em cada gráfico, as barras seguem a ordem crescente do respectivo critério. ")
    for criterion in ("f1", "f2", "f3", "h"):
        ordered = data.alternatives.sort_values([criterion, "id"], kind="stable")
        st.subheader(CRITERIA[criterion])
        st.plotly_chart(criterion_bars(data, ordered, criterion),
                        use_container_width=True, key=f"comparison_{criterion}")
    st.subheader("Tabela de critérios")
    st.dataframe(table_options(data.alternatives[["id", "f1", "f2", "f3", "h"]]),
                 hide_index=True, use_container_width=True)


def decision_page() -> None:
    st.caption("Alternativas não dominadas, seleção pelo ELECTRE I e prioridades finais do AHP.")
    a, b, c = st.columns(3)
    a.metric("Alternativas", len(data.alternatives))
    b.metric("Selecionadas no ELECTRE I", len(data.electre))
    c.metric("Escolhida pelo AHP", data.winner)
    st.subheader("Conjunto selecionado pelo ELECTRE I")
    selected = data.alternatives[data.alternatives.id.isin(data.electre)]
    st.dataframe(table_options(selected[["id", "f1", "f2", "f3", "h"]]), hide_index=True, use_container_width=True)
    if not data.ranking.empty:
        st.subheader("Ranking AHP")
        st.plotly_chart(ranking_chart(data.ranking, data.winner), use_container_width=True)
    else:
        st.warning("Não há prioridades AHP disponíveis nos arquivos de resultados.")
    if data.weights:
        st.subheader("Pesos dos critérios")
        st.plotly_chart(weights_chart(data.weights), use_container_width=True)


def recipe_page() -> None:
    st.caption("Composição das dez pilhas, teores das misturas e alocação de caminhões por minério.")
    aid = st.selectbox(
        "Alternativa a analisar", ids, index=ids.index(data.winner),
        key="recipe_alt",
    )
    alt = data.alternatives.set_index("id").loc[aid]
    a, b, c, d = st.columns(4)
    a.metric("Custo total", f"R$ {alt['f1']:.2f} mi")
    b.metric("Desvio SiO₂", f"{alt['f2']:.4f} pp²")
    c.metric("Desvio Al₂O₃", f"{alt['f3']:.4f} pp²")
    d.metric("Homogeneidade H", f"{alt['h']:.4f}")
    try:
        piles, ores = evaluate_recipe(data, aid)
    except (ValueError, KeyError, TypeError) as exc:
        st.error(f"Não foi possível calcular o plano da alternativa {aid}: {exc}")
        return
    matrix = data.recipes[aid]
    total_trucks = int(matrix.sum())
    cols = st.columns(3)
    cols[0].metric("Caminhões", total_trucks)
    cols[1].metric("Massa total", f"{total_trucks*data.truck_kt:.0f} kt")
    cols[2].metric("Pilhas com massa correta", f"{piles.massa_valida.sum()}/{len(piles)}")

    st.subheader("Composição das pilhas")
    st.plotly_chart(composition(matrix, data), use_container_width=True)
    st.subheader("Qualidade das misturas")
    for criterion in ("sio2", "al2o3"):
        cols = st.columns(2)
        for col, sinter in zip(cols, [1, 2]):
            with col:
                if criterion not in piles:
                    st.warning(f"Não há teores de {criterion} na instância.")
                    continue
                st.plotly_chart(quality_chart(piles, data.limits, sinter, criterion), use_container_width=True)
    checks = ["massa_valida", "sio2_valida", "al2o3_valida", "elegibilidade_valida"]
    failed = [str(piles.loc[~piles[check], "pilha"].tolist()) for check in checks if check in piles and not piles[check].all()]
    if failed or not ores.disponibilidade_valida.all():
        st.error("Há restrições não atendidas no plano selecionado. Confira os valores e a composição antes de utilizá-lo.")
    if "elegibilidade_valida" not in piles:
        st.caption("Elegibilidade dos minérios não verificada: a instância não fornece compatibilidades em formato reconhecível.")


if page == NAVIGATION[0]:
    pareto_page()
elif page == NAVIGATION[1]:
    comparison_page()
elif page == NAVIGATION[2]:
    decision_page()
else:
    recipe_page()
