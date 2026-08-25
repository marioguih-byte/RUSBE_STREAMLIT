"""RUSBÉ em Streamlit.

Direção visual: painel operacional escuro inspirado no notebook original,
com controles no trilho lateral, mapa como foco principal e detalhe horário
aberto sob demanda para cada unidade.
"""

from __future__ import annotations

from datetime import datetime
from html import escape
from typing import Any, Optional

import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from modelos import MODELOS, TZ_BRASILIA, ErroBuscaModelo, buscar_modelo, horario_local
from risco_raio import NIVEIS_RISCO, calcular_risco
from unidades import ESTACOES

st.set_page_config(page_title="RUSBÉ | Painel Meteorológico", page_icon="⚡", layout="wide")

TILES = {
    "Escuro (fundo preto)": {"tiles": "CartoDB dark_matter", "attr": "© OpenStreetMap contributors © CARTO"},
    "Satélite": {
        "tiles": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        "attr": "Tiles © Esri",
    },
    "OpenStreetMap": {"tiles": "OpenStreetMap", "attr": "© OpenStreetMap contributors"},
}

CENTRO_AMERICA_SUL = [-20.0, -47.0]
ZOOM_AMERICA_SUL = 4
NIVEIS_COM_SEM_DADOS = [nivel for _, nivel, _ in NIVEIS_RISCO] + ["Sem dados"]


@st.cache_data(ttl=600, show_spinner=False)
def carregar_dados(modelo_id: str) -> dict[str, Any]:
    """Mantém a previsão consultada por dez minutos."""
    return buscar_modelo(modelo_id)


def _inicializar_estado() -> None:
    valores_iniciais = {
        "modelo_anterior": None,
        "estacao_popup": None,
        "abrir_popup": False,
        "ultimo_clique_mapa": None,
        "centro_mapa": CENTRO_AMERICA_SUL,
        "zoom_mapa": ZOOM_AMERICA_SUL,
        "versao_mapa": 0,
    }
    for chave, valor in valores_iniciais.items():
        st.session_state.setdefault(chave, valor)


def _valor_da_hora(serie: list[Optional[float]], indice: int) -> Optional[float]:
    return serie[indice] if 0 <= indice < len(serie) else None


def _numero(valor: Optional[float], casas: int = 0) -> str:
    if valor is None or pd.isna(valor):
        return "—"
    return f"{valor:.{casas}f}"


def consolidar_estacoes(dados: dict[str, Any]) -> pd.DataFrame:
    """Consolida a leitura atual de todas as unidades em uma tabela."""
    linhas: list[dict[str, Any]] = []
    for estacao in ESTACOES:
        nome = estacao["nome"]
        serie = dados.get(nome, {})
        indice = serie.get("idx_atual", 0)
        cape = _valor_da_hora(serie.get("cape", []), indice)
        lifted_index = _valor_da_hora(serie.get("li", []), indice)
        cin = _valor_da_hora(serie.get("cin", []), indice)
        score, nivel, cor = calcular_risco(cape, lifted_index, cin)
        linhas.append(
            {
                "Unidade": nome,
                "CAPE (J/kg)": cape,
                "Lifted Index (°C)": lifted_index,
                "CIN (J/kg)": cin,
                "Risco": nivel,
                "Score": score,
                "Cor": cor,
                "Latitude": estacao["lat"],
                "Longitude": estacao["lon"],
            }
        )
    return pd.DataFrame(linhas).sort_values("Unidade", kind="stable")


def serie_da_estacao(nome: str, dados: dict[str, Any]) -> pd.DataFrame:
    """Monta as próximas 24 leituras, iniciando na hora de referência atual."""
    serie = dados.get(nome, {})
    tempos = serie.get("tempos", [])
    capes = serie.get("cape", [])
    lis = serie.get("li", [])
    cins = serie.get("cin", [])
    inicio = serie.get("idx_atual", 0)
    fim = min(inicio + 24, len(tempos))
    linhas: list[dict[str, Any]] = []

    for indice in range(inicio, fim):
        cape = _valor_da_hora(capes, indice)
        lifted_index = _valor_da_hora(lis, indice)
        cin = _valor_da_hora(cins, indice)
        score, nivel, cor = calcular_risco(cape, lifted_index, cin)
        try:
            horario = horario_local(tempos[indice]).strftime("%H:%M (%d/%m)")
        except (ValueError, IndexError):
            horario = tempos[indice] if indice < len(tempos) else "—"
        if indice == inicio:
            horario = f"{horario}  ◀ agora"
        linhas.append(
            {
                "Horário": horario,
                "CAPE (J/kg)": cape,
                "Lifted Index": lifted_index,
                "CIN (J/kg)": cin,
                "Score": score,
                "Risco": nivel,
                "Cor": cor,
            }
        )
    return pd.DataFrame(linhas)


def criar_mapa(tabela: pd.DataFrame, estilo: str, centro: list[float], zoom: int) -> folium.Map:
    """Cria o mapa Folium com marcadores clicáveis e popup de leitura breve."""
    configuracao = TILES[estilo]
    mapa = folium.Map(
        location=centro,
        zoom_start=zoom,
        tiles=configuracao["tiles"],
        attr=configuracao["attr"],
        control_scale=True,
        prefer_canvas=True,
    )

    for _, linha in tabela.iterrows():
        score = linha["Score"]
        cor = linha["Cor"]
        score_txt = "—" if pd.isna(score) else f"{score:.1f}/100"
        popup_html = f"""
        <div style=\"font-family:Arial,sans-serif; min-width:220px; line-height:1.55;\">
            <strong>{escape(str(linha['Unidade']))}</strong><br>
            <span style=\"color:{cor}; font-weight:700;\">{escape(str(linha['Risco']))} · {score_txt}</span>
            <hr style=\"margin:7px 0; border:0; border-top:1px solid #d6d9df;\">
            CAPE: {_numero(linha['CAPE (J/kg)'])} J/kg<br>
            Lifted Index: {_numero(linha['Lifted Index (°C)'], 1)} °C<br>
            CIN: {_numero(linha['CIN (J/kg)'])} J/kg<br>
            <small>Clique no marcador para abrir o detalhamento horário.</small>
        </div>
        """
        raio = 7 if pd.isna(score) else min(15, 7 + float(score) / 13)
        folium.CircleMarker(
            location=[linha["Latitude"], linha["Longitude"]],
            radius=raio,
            color=cor,
            weight=2,
            fill=True,
            fill_color=cor,
            fill_opacity=0.9,
            tooltip=linha["Unidade"],
            popup=folium.Popup(popup_html, max_width=320),
        ).add_to(mapa)
    return mapa


def abrir_detalhamento(nome: str, dados: dict[str, Any], modelo_id: str) -> None:
    """Abre uma janela de tabela horária, equivalente ao popup do notebook."""

    @st.dialog(nome, width="large", dismissible=False)
    def janela() -> None:
        nome_modelo, origem, frequencia = MODELOS[modelo_id]
        st.caption(f"Modelo: {nome_modelo} · Origem: {origem} · Atualização: {frequencia}")
        st.markdown("#### Previsão horária — próximas 24 horas")

        horario = serie_da_estacao(nome, dados)
        if horario.empty:
            st.info("Não há série horária disponível para esta unidade no modelo selecionado.")
        else:
            exibicao = horario.drop(columns=["Cor"]).copy()

            def colorir_linha(linha: pd.Series) -> list[str]:
                cor = horario.loc[linha.name, "Cor"]
                return [f"background-color: {cor}; color: white;"] * len(linha)

            st.dataframe(
                exibicao.style.apply(colorir_linha, axis=1),
                hide_index=True,
                use_container_width=True,
                height=455,
                column_config={
                    "CAPE (J/kg)": st.column_config.NumberColumn(format="%.0f"),
                    "Lifted Index": st.column_config.NumberColumn(format="%.1f"),
                    "CIN (J/kg)": st.column_config.NumberColumn(format="%.0f"),
                    "Score": st.column_config.NumberColumn(format="%.1f"),
                },
            )
        if st.button("Fechar", type="primary", use_container_width=True):
            st.session_state["abrir_popup"] = False
            st.session_state["ultimo_clique_mapa"] = None
            st.rerun()

    janela()


def selecionar_estacao(nome: str, tabela: pd.DataFrame) -> None:
    """Seleciona a unidade, aproxima o mapa e solicita a abertura do popup."""
    linha = tabela.loc[tabela["Unidade"] == nome].iloc[0]
    st.session_state["estacao_popup"] = nome
    st.session_state["abrir_popup"] = True
    st.session_state["centro_mapa"] = [float(linha["Latitude"]), float(linha["Longitude"])]
    st.session_state["zoom_mapa"] = 8
    st.session_state["versao_mapa"] += 1


def renderizar_estilo() -> None:
    """Aplica a paleta e o ritmo visual próximos do notebook original."""
    st.markdown(
        """
        <style>
        .stApp { background: #141619; color: #f2f4f8; }
        .block-container { max-width: none; padding: 1.25rem 1.5rem 1.5rem; }
        [data-testid="stSidebar"] { background: #1c2026; border-right: 1px solid #303641; }
        [data-testid="stSidebar"] > div:first-child { padding-top: .7rem; }
        [data-testid="stSidebar"] .stButton > button { border: 1px solid #3b4350; background: #252b34; color: #f2f4f8; border-radius: 7px; min-height: 2.25rem; text-align: left; }
        [data-testid="stSidebar"] .stButton > button:hover { border-color: #e0b400; background: #303743; color: #ffffff; }
        [data-testid="stSidebar"] [data-baseweb="select"] > div { background: #252b34; border-color: #3b4350; color: #f2f4f8; }
        [data-testid="stSidebar"] input { background: #252b34 !important; color: #f2f4f8 !important; border-color: #3b4350 !important; }
        [data-testid="stMetric"] { background: #1f242c; border: 1px solid #353d4a; border-radius: 8px; padding: .75rem; }
        [data-testid="stDialog"] > div { background: #1c2026 !important; color: #f2f4f8 !important; border: 1px solid #3b4350; }
        [data-testid="stDialog"] h1, [data-testid="stDialog"] h2, [data-testid="stDialog"] h3, [data-testid="stDialog"] p, [data-testid="stDialog"] [data-testid="stCaptionContainer"] { color: #f2f4f8 !important; }
        [data-testid="stDialog"] .stButton > button { background: #e0b400; border-color: #e0b400; color: #141619; font-weight: 700; text-align: center; }
        [data-testid="stDialog"] .stButton > button:hover { background: #f0c52b; border-color: #f0c52b; color: #141619; }
        .rusbe-titulo { margin: 0; font-size: 1.5rem; font-weight: 700; letter-spacing: .02em; }
        .rusbe-subtitulo { margin: .15rem 0 .95rem; color: #aeb6c2; font-size: .9rem; }
        .painel-info { background: #1f242c; border: 1px solid #353d4a; border-radius: 8px; padding: .75rem 1rem; color: #c6ccd5; }
        .legenda { font-size: .78rem; color: #c6ccd5; margin: .25rem 0 .6rem; }
        .stDataFrame { border: 1px solid #353d4a; border-radius: 7px; overflow: hidden; }
        @media (max-width: 760px) { .block-container { padding: .9rem .75rem; } }
        </style>
        """,
        unsafe_allow_html=True,
    )


def main() -> None:
    _inicializar_estado()
    renderizar_estilo()

    with st.sidebar:
        st.markdown("### RUSBÉ")
        st.caption("PAINEL METEOROLÓGICO")
        st.divider()
        st.caption("MODELO NUMÉRICO")
        modelo_id = st.selectbox(
            "Modelo numérico",
            options=list(MODELOS),
            format_func=lambda chave: MODELOS[chave][0],
            label_visibility="collapsed",
        )
        nome_modelo, origem, frequencia = MODELOS[modelo_id]
        st.caption(f"Origem: {origem} · Atualiza: {frequencia}")

        if st.button("Atualizar dados de todos os modelos", use_container_width=True):
            carregar_dados.clear()
            st.session_state["ultimo_clique_mapa"] = None

        st.divider()
        st.caption("ESTILO DO MAPA")
        estilo = st.selectbox("Estilo do mapa", options=list(TILES), label_visibility="collapsed")
        if st.button("Centralizar América do Sul", use_container_width=True):
            st.session_state["centro_mapa"] = CENTRO_AMERICA_SUL
            st.session_state["zoom_mapa"] = ZOOM_AMERICA_SUL
            st.session_state["versao_mapa"] += 1

    if modelo_id != st.session_state["modelo_anterior"]:
        st.session_state["modelo_anterior"] = modelo_id
        st.session_state["ultimo_clique_mapa"] = None
        st.session_state["abrir_popup"] = False

    try:
        with st.spinner(f"Buscando {nome_modelo} para {len(ESTACOES)} unidades..."):
            dados = carregar_dados(modelo_id)
    except ErroBuscaModelo as erro:
        st.error(f"Falha ao buscar o modelo selecionado: {erro}")
        st.stop()
    except Exception as erro:
        st.error(f"Ocorreu um erro inesperado ao carregar o painel: {erro}")
        st.stop()

    tabela = consolidar_estacoes(dados)

    with st.sidebar:
        st.divider()
        st.caption(f"UNIDADES MONITORADAS ({len(ESTACOES)})")
        termo = st.text_input("Pesquisar unidade", placeholder="Pesquisar unidade...", label_visibility="collapsed")
        termo_normalizado = termo.casefold().strip()
        exibicao_lateral = tabela[
            tabela["Unidade"].str.casefold().str.contains(termo_normalizado, na=False)
        ]
        for _, linha in exibicao_lateral.iterrows():
            score_txt = "sem dados" if pd.isna(linha["Score"]) else f"{linha['Score']:.0f}"
            if st.button(
                f"{linha['Risco']} · {score_txt} | {linha['Unidade']}",
                key=f"unidade_{linha['Unidade']}",
                use_container_width=True,
            ):
                selecionar_estacao(linha["Unidade"], tabela)

        st.divider()
        st.caption("LEGENDA DE RISCO")
        for _, nivel, cor in NIVEIS_RISCO:
            st.markdown(f"<div class='legenda'><span style='color:{cor}; font-size:1.05rem;'>●</span> {nivel}</div>", unsafe_allow_html=True)

    st.markdown("<p class='rusbe-titulo'>RUSBÉ — Rastreamento e Utilização de Sistema Baseado em Eletricidade Atmosférica</p>", unsafe_allow_html=True)
    st.markdown(
        f"<p class='rusbe-subtitulo'>Modelo: {nome_modelo} · Horário de referência do dado: {dados.get('_hora_referencia', '—')} · "
        f"Clique em um marcador ou em uma unidade da barra lateral para abrir a previsão horária.</p>",
        unsafe_allow_html=True,
    )

    contagens = tabela["Risco"].value_counts()
    metr1, metr2, metr3, metr4, metr5 = st.columns(5)
    metr1.metric("Severo", int(contagens.get("Severo", 0)))
    metr2.metric("Alto", int(contagens.get("Alto", 0)))
    metr3.metric("Moderado", int(contagens.get("Moderado", 0)))
    metr4.metric("Baixo", int(contagens.get("Baixo", 0)))
    metr5.metric("Nenhum", int(contagens.get("Nenhum", 0)))

    st.markdown("<div class='painel-info'>Marcadores coloridos apresentam o risco calculado na hora de referência. O pop-up de cada unidade mantém a leitura horária de CAPE, Lifted Index, CIN, score e classificação nas próximas 24 horas.</div>", unsafe_allow_html=True)
    st.markdown("#### Mapa de unidades monitoradas")

    mapa = criar_mapa(
        tabela,
        estilo,
        st.session_state["centro_mapa"],
        st.session_state["zoom_mapa"],
    )
    resultado_mapa = st_folium(
        mapa,
        height=680,
        use_container_width=True,
        key=f"mapa_{modelo_id}_{estilo}_{st.session_state['versao_mapa']}",
        returned_objects=["last_object_clicked_tooltip"],
    )

    clique = resultado_mapa.get("last_object_clicked_tooltip") if resultado_mapa else None
    if clique and clique in set(tabela["Unidade"]) and clique != st.session_state["ultimo_clique_mapa"]:
        st.session_state["ultimo_clique_mapa"] = clique
        selecionar_estacao(clique, tabela)
        st.rerun()

    if st.session_state["abrir_popup"] and st.session_state["estacao_popup"]:
        abrir_detalhamento(st.session_state["estacao_popup"], dados, modelo_id)

    with st.expander("Como interpretar o painel"):
        st.write(
            "O score é uma heurística baseada em CAPE, Lifted Index e CIN. CAPE alto e Lifted Index mais negativo "
            "elevam o risco; CIN elevado reduz a probabilidade de disparo convectivo. O painel serve ao acompanhamento "
            "meteorológico e não substitui alertas oficiais ou sistemas de detecção de descargas atmosféricas."
        )
        st.caption(f"Última renderização local: {datetime.now(TZ_BRASILIA).strftime('%d/%m/%Y %H:%M:%S')} (America/Sao_Paulo).")


if __name__ == "__main__":
    main()
