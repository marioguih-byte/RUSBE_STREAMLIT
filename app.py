"""Dashboard Streamlit do RUSBÉ — monitoramento de risco meteorológico."""

from __future__ import annotations

from datetime import datetime
from html import escape
from typing import Any, Optional

import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from modelos import MODELOS, ErroBuscaModelo, buscar_modelo
from risco_raio import NIVEIS_RISCO, calcular_risco
from unidades import ESTACOES

st.set_page_config(page_title="RUSBÉ | Risco de Raios", page_icon="⚡", layout="wide")

TILES = {
    "Escuro": {"tiles": "CartoDB dark_matter", "attr": "© OpenStreetMap contributors © CARTO"},
    "Satélite": {
        "tiles": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        "attr": "Tiles © Esri",
    },
    "OpenStreetMap": {"tiles": "OpenStreetMap", "attr": "© OpenStreetMap contributors"},
}


@st.cache_data(ttl=600, show_spinner=False)
def carregar_dados(modelo_id: str) -> dict[str, Any]:
    """Mantém o resultado por dez minutos para evitar consultas repetidas."""
    return buscar_modelo(modelo_id)


def _valor_da_hora(serie: list[Optional[float]], indice: int) -> Optional[float]:
    return serie[indice] if 0 <= indice < len(serie) else None


def _numero(valor: Optional[float], casas: int = 0, sufixo: str = "") -> str:
    if valor is None:
        return "—"
    return f"{valor:.{casas}f}{sufixo}"


def consolidar_estacoes(dados: dict[str, Any]) -> pd.DataFrame:
    """Gera a tabela de situação atual para as 40 unidades."""
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
                "Escore": score,
                "Cor": cor,
                "Latitude": estacao["lat"],
                "Longitude": estacao["lon"],
            }
        )
    return pd.DataFrame(linhas).sort_values(["Escore", "Unidade"], ascending=[False, True], na_position="last")


def criar_mapa(tabela: pd.DataFrame, estilo: str) -> folium.Map:
    """Monta um mapa Folium com círculos coloridos pelo nível de risco."""
    configuracao = TILES[estilo]
    mapa = folium.Map(
        location=[-17.5, -43.5],
        zoom_start=4,
        tiles=configuracao["tiles"],
        attr=configuracao["attr"],
        control_scale=True,
    )

    for _, linha in tabela.iterrows():
        score = linha["Escore"]
        cor = linha["Cor"]
        score_html = "Sem dados" if pd.isna(score) else f"{score:.1f}/100"
        popup_html = f"""
        <div style=\"font-family:Arial,sans-serif;min-width:215px;line-height:1.45\">
            <strong>{escape(str(linha['Unidade']))}</strong><br>
            <span style=\"color:{cor};font-weight:700\">{escape(str(linha['Risco']))} — {score_html}</span><hr style=\"margin:6px 0\">
            CAPE: {_numero(linha['CAPE (J/kg)'])} J/kg<br>
            Lifted Index: {_numero(linha['Lifted Index (°C)'], 1)} °C<br>
            CIN: {_numero(linha['CIN (J/kg)'])} J/kg
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
            fill_opacity=0.88,
            tooltip=f"{linha['Unidade']} | {linha['Risco']}",
            popup=folium.Popup(popup_html, max_width=300),
        ).add_to(mapa)

    return mapa


def serie_da_estacao(nome: str, dados: dict[str, Any]) -> pd.DataFrame:
    """Prepara as próximas 24 horas de previsão da unidade escolhida."""
    serie = dados.get(nome, {})
    tempos = serie.get("tempos", [])
    capes = serie.get("cape", [])
    lis = serie.get("li", [])
    cins = serie.get("cin", [])
    linhas: list[dict[str, Any]] = []

    for indice, tempo in enumerate(tempos[:24]):
        cape = _valor_da_hora(capes, indice)
        lifted_index = _valor_da_hora(lis, indice)
        cin = _valor_da_hora(cins, indice)
        score, nivel, _ = calcular_risco(cape, lifted_index, cin)
        linhas.append(
            {
                "Horário": pd.to_datetime(tempo),
                "Escore de risco": score,
                "CAPE (J/kg)": cape,
                "Lifted Index (°C)": lifted_index,
                "CIN (J/kg)": cin,
                "Nível": nivel,
            }
        )
    return pd.DataFrame(linhas)


def renderizar_estilo() -> None:
    st.markdown(
        """
        <style>
        .block-container {max-width: 1500px; padding-top: 2rem; padding-bottom: 2.5rem;}
        [data-testid="stMetric"] {background: #151d28; border: 1px solid #283548; border-radius: .7rem; padding: .75rem;}
        [data-testid="stMetricLabel"] {font-size: .85rem;}
        .rusbe-subtitulo {color: #93a4ba; margin-top: -0.6rem; margin-bottom: 1.4rem;}
        </style>
        """,
        unsafe_allow_html=True,
    )


def main() -> None:
    renderizar_estilo()
    st.title("RUSBÉ")
    st.markdown(
        '<p class="rusbe-subtitulo">Rastreamento e utilização de sistema baseado em eletricidade atmosférica</p>',
        unsafe_allow_html=True,
    )

    with st.sidebar:
        st.header("Controles")
        modelo_id = st.selectbox(
            "Modelo numérico",
            options=list(MODELOS),
            format_func=lambda chave: MODELOS[chave][0],
        )
        estilo = st.selectbox("Mapa base", options=list(TILES))
        if st.button("Atualizar dados agora", use_container_width=True):
            carregar_dados.clear()
        st.divider()
        st.caption("A previsão é atualizada automaticamente a cada 10 minutos nesta interface.")

    nome_modelo, origem, frequencia = MODELOS[modelo_id]
    try:
        with st.spinner(f"Consultando {nome_modelo} para {len(ESTACOES)} unidades..."):
            dados = carregar_dados(modelo_id)
    except ErroBuscaModelo as erro:
        st.error(f"Não foi possível carregar o modelo selecionado. {erro}")
        st.stop()
    except Exception as erro:  # proteção adicional para manter a interface compreensível
        st.error(f"Ocorreu um erro inesperado ao montar o painel: {erro}")
        st.stop()

    tabela = consolidar_estacoes(dados)
    st.caption(
        f"**Modelo:** {nome_modelo} | **Origem:** {origem} | **Atualização do provedor:** {frequencia} | "
        f"**Horário de referência:** {dados.get('_hora_referencia', '—')}"
    )

    contagens = tabela["Risco"].value_counts()
    sem_dados = int(tabela["Escore"].isna().sum())
    maximo = tabela.dropna(subset=["Escore"])
    maior_score = maximo.iloc[0] if not maximo.empty else None

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Severo", int(contagens.get("Severo", 0)))
    c2.metric("Alto", int(contagens.get("Alto", 0)))
    c3.metric("Moderado", int(contagens.get("Moderado", 0)))
    c4.metric("Baixo ou nenhum", int(contagens.get("Baixo", 0) + contagens.get("Nenhum", 0)))
    c5.metric("Sem dados", sem_dados)

    mapa_coluna, lista_coluna = st.columns([1.45, 1])
    with mapa_coluna:
        st.subheader("Distribuição geográfica")
        st_folium(criar_mapa(tabela, estilo), height=560, use_container_width=True, returned_objects=[])

    with lista_coluna:
        st.subheader("Situação atual")
        niveis_disponiveis = [nivel for _, nivel, _ in NIVEIS_RISCO] + ["Sem dados"]
        niveis = st.multiselect("Filtrar níveis", niveis_disponiveis, default=niveis_disponiveis)
        exibicao = tabela[tabela["Risco"].isin(niveis)].copy()
        exibicao["Escore"] = exibicao["Escore"].map(lambda valor: "—" if pd.isna(valor) else f"{valor:.1f}")
        st.dataframe(
            exibicao[["Unidade", "Risco", "Escore"]],
            hide_index=True,
            use_container_width=True,
            height=500,
            column_config={
                "Unidade": st.column_config.TextColumn(width="large"),
                "Risco": st.column_config.TextColumn(width="small"),
                "Escore": st.column_config.TextColumn(width="small"),
            },
        )

    st.divider()
    st.subheader("Detalhamento da unidade")
    nomes = tabela["Unidade"].tolist()
    nome_estacao = st.selectbox("Selecione uma unidade", options=nomes)
    linha = tabela.loc[tabela["Unidade"] == nome_estacao].iloc[0]

    d1, d2, d3, d4 = st.columns(4)
    d1.metric("Risco atual", linha["Risco"], "—" if pd.isna(linha["Escore"]) else f"{linha['Escore']:.1f}/100")
    d2.metric("CAPE", _numero(linha["CAPE (J/kg)"], 0, " J/kg"))
    d3.metric("Lifted Index", _numero(linha["Lifted Index (°C)"], 1, " °C"))
    d4.metric("CIN", _numero(linha["CIN (J/kg)"], 0, " J/kg"))

    historico = serie_da_estacao(nome_estacao, dados)
    if not historico.empty and historico["Escore de risco"].notna().any():
        grafico_coluna, tabela_coluna = st.columns([1.3, 1])
        with grafico_coluna:
            st.caption("Evolução prevista nas próximas 24 horas")
            st.line_chart(historico.set_index("Horário")[["Escore de risco"]], height=290, color="#e0761f")
        with tabela_coluna:
            st.caption("Valores horários")
            horario_formatado = historico.copy()
            horario_formatado["Horário"] = horario_formatado["Horário"].dt.strftime("%d/%m %H:%M")
            st.dataframe(
                horario_formatado[["Horário", "Nível", "Escore de risco", "CAPE (J/kg)", "Lifted Index (°C)", "CIN (J/kg)"]],
                hide_index=True,
                use_container_width=True,
                height=290,
                column_config={
                    "Escore de risco": st.column_config.NumberColumn(format="%.1f"),
                    "CAPE (J/kg)": st.column_config.NumberColumn(format="%.0f"),
                    "Lifted Index (°C)": st.column_config.NumberColumn(format="%.1f"),
                    "CIN (J/kg)": st.column_config.NumberColumn(format="%.0f"),
                },
            )
    else:
        st.info("Não há série horária disponível para esta unidade no modelo selecionado.")

    with st.expander("Como interpretar o painel"):
        st.write(
            "O escore é uma heurística baseada em CAPE, Lifted Index e CIN: valores altos de CAPE e "
            "Lifted Index mais negativo elevam o risco, enquanto CIN elevado reduz a probabilidade de disparo convectivo. "
            "Este painel apoia o acompanhamento meteorológico e não substitui sistemas de detecção de descargas atmosféricas ou alertas oficiais."
        )
        st.caption(f"Consulta realizada em {datetime.now().strftime('%d/%m/%Y às %H:%M:%S')}. Dados de previsão: Open-Meteo.")


if __name__ == "__main__":
    main()
