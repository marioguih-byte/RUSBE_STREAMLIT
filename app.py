"""RUSBÉ em Streamlit.

Painel operacional com barra lateral escura, mapa claro (OpenStreetMap) travado
no Brasil como foco principal e detalhe horário aberto sob demanda para cada
unidade.
"""

from __future__ import annotations

import json
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any, Optional

import folium
import pandas as pd
import streamlit as st
from branca.element import Element, MacroElement
from jinja2 import Template
from streamlit_folium import st_folium

from modelos import MODELOS, TZ_BRASILIA, ErroBuscaModelo, buscar_modelo, horario_local
from risco_raio import NIVEIS_RISCO, calcular_risco
from unidades import ESTACOES

st.set_page_config(page_title="RUSBÉ | Painel Meteorológico", page_icon="⚡", layout="wide")

RAIZ = Path(__file__).resolve().parent

# OpenStreetMap é o padrão (primeiro item). O mapa escuro foi removido.
TILES = {
    "OpenStreetMap": {"tiles": "OpenStreetMap", "attr": "© OpenStreetMap contributors"},
    "Satélite": {
        "tiles": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        "attr": "Tiles © Esri",
    },
}

# Enquadramento fixo no Brasil: sudoeste e nordeste do território continental.
CENTRO_BRASIL = [-14.2, -53.4]
ZOOM_BRASIL = 4
LIMITES_BRASIL = [[-33.75, -74.0], [5.3, -34.8]]
# Limite de navegação (folga pequena em volta do Brasil).
LIMITES_NAVEGACAO = {"min_lat": -36.0, "min_lon": -77.0, "max_lat": 8.0, "max_lon": -31.0}

COR_NIVEL = {nivel: cor for _, nivel, cor in NIVEIS_RISCO}
COR_NIVEL["Sem dados"] = "#3a3f47"
ICONE_NIVEL = {"Severo": "🔴", "Alto": "🟠", "Moderado": "🟡", "Baixo": "🟢", "Nenhum": "⚪", "Sem dados": "⚫"}
CACHE_HORARIO_LOCAL = "america_sao_paulo_v2"


@st.cache_data(ttl=600, show_spinner=False)
def carregar_dados(modelo_id: str, versao_cache: str) -> dict[str, Any]:
    """Mantém a previsão consultada por dez minutos, separada por versão temporal."""
    return buscar_modelo(modelo_id)


@st.cache_resource(show_spinner=False)
def carregar_geojson(arquivo: str) -> dict[str, Any]:
    """Carrega o contorno/máscara do Brasil empacotado em dados/."""
    return json.loads((RAIZ / "dados" / arquivo).read_text(encoding="utf-8"))


def _inicializar_estado() -> None:
    valores_iniciais = {
        "modelo_anterior": None,
        "estacao_popup": None,
        "abrir_popup": False,
        "ultimo_clique_mapa": None,
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


class AjusteBrasil(MacroElement):
    """Mantém o mapa enquadrado no Brasil e oferece o botão de recentralizar.

    O zoom mínimo é calculado no navegador a partir do tamanho do mapa, de modo
    que não é possível afastar a visão além do território brasileiro.
    """

    _template = Template(
        """
        {% macro script(this, kwargs) %}
        (function () {
            var mapa = {{ this._parent.get_name() }};
            var limites = L.latLngBounds({{ this.limites }});
            function ajustar() {
                mapa.invalidateSize();
                mapa.setMinZoom(mapa.getBoundsZoom(limites, false, L.point(8, 8)));
                mapa.fitBounds(limites, {padding: [8, 8], animate: false});
            }
            mapa.whenReady(ajustar);
            window.addEventListener('resize', ajustar);

            var controle = L.control({position: 'topleft'});
            controle.onAdd = function () {
                var caixa = L.DomUtil.create('div', 'leaflet-bar rusbe-home');
                var botao = L.DomUtil.create('a', '', caixa);
                botao.href = '#';
                botao.title = 'Centralizar no Brasil';
                botao.setAttribute('role', 'button');
                botao.innerHTML = '&#8962;';
                L.DomEvent.disableClickPropagation(caixa);
                L.DomEvent.on(botao, 'click', function (e) {
                    L.DomEvent.preventDefault(e);
                    ajustar();
                });
                return caixa;
            };
            controle.addTo(mapa);
        })();
        {% endmacro %}
        """
    )

    def __init__(self, limites: list[list[float]]):
        super().__init__()
        self._name = "AjusteBrasil"
        self.limites = json.dumps(limites)


def _legenda_mapa() -> str:
    itens = "".join(
        f"<div class='rl-item'><span class='rl-dot' style='background:{cor}'></span>{nivel}</div>"
        for _, nivel, cor in NIVEIS_RISCO[::-1]
    )
    return f"""
    <style>
      .leaflet-tooltip {{ font: 600 12px 'Segoe UI', Arial, sans-serif; color:#1f2933; border:0;
        border-radius:6px; padding:4px 8px; box-shadow:0 2px 8px rgba(15,23,42,.25); }}
      .leaflet-popup-content-wrapper {{ border-radius:12px; box-shadow:0 8px 24px rgba(15,23,42,.28); }}
      .leaflet-popup-content {{ margin:0; }}
      .rusbe-home a {{ font-size:20px; line-height:30px; text-align:center; color:#1f2933; }}
      .rusbe-legenda {{ position:absolute; left:12px; bottom:64px; z-index:1000; background:rgba(255,255,255,.94);
        border:1px solid rgba(15,23,42,.12); border-radius:10px; padding:8px 12px 6px;
        font:12px 'Segoe UI', Arial, sans-serif; color:#1f2933; box-shadow:0 4px 14px rgba(15,23,42,.18); }}
      .rusbe-legenda .rl-titulo {{ font-weight:700; font-size:11px; letter-spacing:.06em; text-transform:uppercase;
        color:#52606d; margin-bottom:4px; }}
      .rl-item {{ display:flex; align-items:center; gap:7px; margin:3px 0; }}
      .rl-dot {{ width:11px; height:11px; border-radius:50%; border:2px solid #fff; box-shadow:0 0 0 1px rgba(15,23,42,.25); }}
    </style>
    <div class="rusbe-legenda"><div class="rl-titulo">Risco de raios</div>{itens}</div>
    """


def criar_mapa(tabela: pd.DataFrame, estilo: str) -> folium.Map:
    """Cria o mapa Folium travado no Brasil, com marcadores clicáveis."""
    configuracao = TILES[estilo]
    mapa = folium.Map(
        location=CENTRO_BRASIL,
        zoom_start=ZOOM_BRASIL,
        tiles=configuracao["tiles"],
        attr=configuracao["attr"],
        control_scale=True,
        prefer_canvas=True,
        zoom_snap=0.25,
        zoom_delta=0.5,
        min_zoom=3,
        max_zoom=13,
        max_bounds=True,
        max_bounds_viscosity=1.0,
        **LIMITES_NAVEGACAO,
    )

    # Véu suave fora do Brasil + contorno do país.
    veu = {"fillColor": "#f4f6f8", "fillOpacity": 0.62} if estilo == "OpenStreetMap" else {"fillColor": "#0b1220", "fillOpacity": 0.5}
    folium.GeoJson(
        carregar_geojson("brasil_mascara.geojson"),
        name="Fora do Brasil",
        style_function=lambda _f, veu=veu: {**veu, "weight": 0, "color": "transparent"},
        interactive=False,
    ).add_to(mapa)
    folium.GeoJson(
        carregar_geojson("brasil_contorno.geojson"),
        name="Brasil",
        style_function=lambda _f: {"fill": False, "color": "#1d4e89", "weight": 2, "opacity": 0.85},
        interactive=False,
    ).add_to(mapa)

    for _, linha in tabela.iterrows():
        score = linha["Score"]
        cor = linha["Cor"]
        score_txt = "—" if pd.isna(score) else f"{score:.1f}/100"
        popup_html = f"""
        <div style="font-family:'Segoe UI',Arial,sans-serif; min-width:230px; overflow:hidden; border-radius:12px;">
            <div style="background:{cor}; color:#fff; padding:9px 12px;">
                <div style="font-weight:700; font-size:13px; line-height:1.3;">{escape(str(linha['Unidade']))}</div>
                <div style="font-size:12px; opacity:.95; margin-top:2px;">{escape(str(linha['Risco']))} · {score_txt}</div>
            </div>
            <div style="padding:9px 12px 10px; font-size:12.5px; line-height:1.7; color:#1f2933;">
                <div style="display:flex; justify-content:space-between;"><span>CAPE</span><b>{_numero(linha['CAPE (J/kg)'])} J/kg</b></div>
                <div style="display:flex; justify-content:space-between;"><span>Lifted Index</span><b>{_numero(linha['Lifted Index (°C)'], 1)} °C</b></div>
                <div style="display:flex; justify-content:space-between;"><span>CIN</span><b>{_numero(linha['CIN (J/kg)'])} J/kg</b></div>
                <div style="margin-top:6px; color:#7b8794; font-size:11px;">Clique para abrir a previsão horária.</div>
            </div>
        </div>
        """
        raio = 7 if pd.isna(score) else min(15, 7 + float(score) / 13)
        # Halo translúcido (não interativo) para destacar cada unidade.
        folium.CircleMarker(
            location=[linha["Latitude"], linha["Longitude"]],
            radius=raio + 6,
            weight=0,
            fill=True,
            fill_color=cor,
            fill_opacity=0.25,
            interactive=False,
        ).add_to(mapa)
        folium.CircleMarker(
            location=[linha["Latitude"], linha["Longitude"]],
            radius=raio,
            color="#ffffff",
            weight=2.5,
            fill=True,
            fill_color=cor,
            fill_opacity=0.95,
            tooltip=linha["Unidade"],
            popup=folium.Popup(popup_html, max_width=320),
        ).add_to(mapa)

    mapa.add_child(AjusteBrasil(LIMITES_BRASIL))
    mapa.get_root().html.add_child(Element(_legenda_mapa()))
    return mapa


def abrir_detalhamento(nome: str, dados: dict[str, Any], modelo_id: str) -> None:
    """Abre uma janela de tabela horária, equivalente ao popup do notebook."""

    @st.dialog(nome, width="large", dismissible=False)
    def janela() -> None:
        nome_modelo, origem, frequencia = MODELOS[modelo_id]
        st.caption(f"Modelo: {nome_modelo} · Origem: {origem} · Atualização: {frequencia}")

        horario = serie_da_estacao(nome, dados)
        if horario.empty:
            st.info("Não há série horária disponível para esta unidade no modelo selecionado.")
        else:
            agora = horario.iloc[0]
            cor_agora = agora["Cor"]
            score_agora = "—" if pd.isna(agora["Score"]) else f"{agora['Score']:.1f}"
            st.markdown(
                f"""
                <div class='dlg-resumo'>
                    <div class='dlg-card' style='--cor:{cor_agora}'><span>Risco agora</span><b>{escape(str(agora['Risco']))}</b><small>score {score_agora}</small></div>
                    <div class='dlg-card'><span>CAPE</span><b>{_numero(agora['CAPE (J/kg)'])}</b><small>J/kg</small></div>
                    <div class='dlg-card'><span>Lifted Index</span><b>{_numero(agora['Lifted Index'], 1)}</b><small>°C</small></div>
                    <div class='dlg-card'><span>CIN</span><b>{_numero(agora['CIN (J/kg)'])}</b><small>J/kg</small></div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.markdown("#### Previsão horária — próximas 24 horas")
            exibicao = horario.drop(columns=["Cor"]).copy()

            def colorir_linha(linha: pd.Series) -> list[str]:
                cor = horario.loc[linha.name, "Cor"]
                return [f"background-color: {cor}; color: white;"] * len(linha)

            st.dataframe(
                exibicao.style.apply(colorir_linha, axis=1),
                hide_index=True,
                width="stretch",
                height=420,
                column_config={
                    "CAPE (J/kg)": st.column_config.NumberColumn(format="%.0f"),
                    "Lifted Index": st.column_config.NumberColumn(format="%.1f"),
                    "CIN (J/kg)": st.column_config.NumberColumn(format="%.0f"),
                    "Score": st.column_config.NumberColumn(format="%.1f"),
                },
            )
        if st.button("Fechar", type="primary", width="stretch"):
            st.session_state["abrir_popup"] = False
            st.session_state["ultimo_clique_mapa"] = None
            st.rerun()

    janela()


def selecionar_estacao(nome: str) -> None:
    """Seleciona a unidade e solicita a abertura do detalhamento (o mapa não se move)."""
    st.session_state["estacao_popup"] = nome
    st.session_state["abrir_popup"] = True


def renderizar_estilo() -> None:
    """Aplica a paleta escura do painel; o mapa em si permanece claro."""
    st.markdown(
        """
        <style>
        .stApp { background: radial-gradient(1200px 520px at 15% -10%, #1d2430 0%, #14171c 55%, #101215 100%); color: #f2f4f8; }
        .block-container { max-width: none; padding: 1.1rem 1.6rem 1.6rem; }
        header[data-testid="stHeader"] { background: transparent; }

        [data-testid="stSidebar"] { background: #181c22; border-right: 1px solid #2b323c; }
        [data-testid="stSidebar"] > div:first-child { padding-top: .7rem; }
        [data-testid="stSidebar"] .stButton > button { border: 1px solid #323a46; background: #212731; color: #f2f4f8; border-radius: 9px; min-height: 2.25rem; text-align: left; justify-content: flex-start; transition: all .15s ease; }
        [data-testid="stSidebar"] .stButton > button:hover { border-color: #e0b400; background: #2b323d; color: #ffffff; transform: translateX(2px); }
        [data-testid="stSidebar"] [data-baseweb="select"] > div { background: #212731; border-color: #323a46; color: #f2f4f8; border-radius: 9px; }
        [data-testid="stSidebar"] input { background: #212731 !important; color: #f2f4f8 !important; border-color: #323a46 !important; }
        .marca-lateral { display:flex; align-items:center; gap:.6rem; margin-bottom:.1rem; }
        .marca-lateral .raio { width:2.1rem; height:2.1rem; border-radius:10px; display:grid; place-items:center; font-size:1.15rem; background:linear-gradient(135deg,#f5c518,#e0761f); box-shadow:0 4px 14px rgba(224,118,31,.35); }
        .marca-lateral b { font-size:1.25rem; letter-spacing:.03em; }

        .rusbe-cabecalho { display:flex; flex-wrap:wrap; align-items:center; gap:1rem 1.25rem; padding:1rem 1.25rem; margin-bottom:.9rem;
            background:linear-gradient(120deg,#222a36 0%,#1b2029 60%,#171b22 100%); border:1px solid #333c49; border-radius:14px;
            box-shadow:0 8px 28px rgba(0,0,0,.28); }
        .rusbe-cabecalho .raio { width:2.8rem; height:2.8rem; border-radius:12px; display:grid; place-items:center; font-size:1.5rem;
            background:linear-gradient(135deg,#f5c518,#e0761f); box-shadow:0 6px 18px rgba(224,118,31,.38); }
        .rusbe-titulo { margin:0; font-size:1.6rem; font-weight:800; letter-spacing:.04em; line-height:1.1; }
        .rusbe-subtitulo { margin:.2rem 0 0; color:#a9b3c1; font-size:.85rem; }
        .rusbe-pills { margin-left:auto; display:flex; flex-wrap:wrap; gap:.5rem; }
        .pill { background:#11151b; border:1px solid #394352; color:#d5dbe4; border-radius:999px; padding:.3rem .8rem; font-size:.78rem; }
        .pill b { color:#ffffff; }

        .kpi { background:#1c222b; border:1px solid #333c49; border-top:3px solid var(--cor); border-radius:12px; padding:.7rem .9rem; box-shadow:0 4px 14px rgba(0,0,0,.2); }
        .kpi .kpi-v { font-size:1.9rem; font-weight:800; line-height:1.1; color:#fff; }
        .kpi .kpi-r { font-size:.78rem; letter-spacing:.07em; text-transform:uppercase; color:var(--cor); font-weight:700; }

        .destaque { margin:.8rem 0 .7rem; padding:.65rem 1rem; background:#1c222b; border:1px solid #333c49; border-left:4px solid var(--cor); border-radius:10px; color:#c9d1db; font-size:.88rem; }
        .destaque b { color:#fff; }
        .secao { margin:.2rem 0 .5rem; font-size:1.05rem; font-weight:700; letter-spacing:.02em; }

        .stDataFrame { border: 1px solid #353d4a; border-radius: 8px; overflow: hidden; }
        iframe[title*="folium"], [data-testid="stCustomComponentV1"] iframe { border:1px solid #3a4452; border-radius:14px; box-shadow:0 10px 30px rgba(0,0,0,.35); background:#e9edf2; }

        [data-testid="stDialog"] > div { background: #1c2026 !important; color: #f2f4f8 !important; border: 1px solid #3b4350; border-radius:14px; }
        [data-testid="stDialog"] h1, [data-testid="stDialog"] h2, [data-testid="stDialog"] h3, [data-testid="stDialog"] h4, [data-testid="stDialog"] p, [data-testid="stDialog"] [data-testid="stCaptionContainer"] { color: #f2f4f8 !important; }
        [data-testid="stDialog"] .stButton > button { background: #e0b400; border-color: #e0b400; color: #141619; font-weight: 700; text-align: center; border-radius:9px; }
        [data-testid="stDialog"] .stButton > button:hover { background: #f0c52b; border-color: #f0c52b; color: #141619; }
        .dlg-resumo { display:grid; grid-template-columns:repeat(4,1fr); gap:.6rem; margin:.3rem 0 .9rem; }
        .dlg-card { background:#242a33; border:1px solid #38414e; border-top:3px solid var(--cor,#5a6472); border-radius:10px; padding:.5rem .75rem; display:flex; flex-direction:column; }
        .dlg-card span { font-size:.7rem; letter-spacing:.07em; text-transform:uppercase; color:#aab3c0; }
        .dlg-card b { font-size:1.35rem; line-height:1.2; color:#fff; }
        .dlg-card small { color:#aab3c0; }

        @media (max-width: 760px) {
            .block-container { padding: .9rem .75rem; }
            .rusbe-pills { margin-left:0; }
            .dlg-resumo { grid-template-columns:repeat(2,1fr); }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def main() -> None:
    _inicializar_estado()
    renderizar_estilo()

    with st.sidebar:
        st.markdown(
            "<div class='marca-lateral'><div class='raio'>⚡</div><b>RUSBÉ</b></div>",
            unsafe_allow_html=True,
        )
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

        if st.button("Atualizar dados de todos os modelos", width="stretch"):
            carregar_dados.clear()
            st.session_state["ultimo_clique_mapa"] = None

        st.divider()
        st.caption("ESTILO DO MAPA")
        estilo = st.selectbox("Estilo do mapa", options=list(TILES), index=0, label_visibility="collapsed")

    if modelo_id != st.session_state["modelo_anterior"]:
        st.session_state["modelo_anterior"] = modelo_id
        st.session_state["ultimo_clique_mapa"] = None
        st.session_state["abrir_popup"] = False

    try:
        with st.spinner(f"Buscando {nome_modelo} para {len(ESTACOES)} unidades..."):
            dados = carregar_dados(modelo_id, CACHE_HORARIO_LOCAL)
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
        ordem = st.radio("Ordenar por", ["Nome", "Maior risco"], horizontal=True, label_visibility="collapsed")
        termo_normalizado = termo.casefold().strip()
        exibicao_lateral = tabela[tabela["Unidade"].str.casefold().str.contains(termo_normalizado, na=False, regex=False)]
        if ordem == "Maior risco":
            exibicao_lateral = exibicao_lateral.sort_values(["Score", "Unidade"], ascending=[False, True], na_position="last", kind="stable")
        if exibicao_lateral.empty:
            st.caption("Nenhuma unidade encontrada.")
        for _, linha in exibicao_lateral.iterrows():
            score_txt = "—" if pd.isna(linha["Score"]) else f"{linha['Score']:.0f}"
            icone = ICONE_NIVEL.get(linha["Risco"], "⚫")
            if st.button(
                f"{icone} {score_txt} · {linha['Unidade']}",
                key=f"unidade_{linha['Unidade']}",
                width="stretch",
                help=f"{linha['Risco']} — abrir previsão horária",
            ):
                selecionar_estacao(linha["Unidade"])

    st.markdown(
        f"""
        <div class='rusbe-cabecalho'>
            <div class='raio'>⚡</div>
            <div>
                <p class='rusbe-titulo'>RUSBÉ</p>
                <p class='rusbe-subtitulo'>Rastreamento e Utilização de Sistema Baseado em Eletricidade Atmosférica</p>
            </div>
            <div class='rusbe-pills'>
                <span class='pill'>Modelo · <b>{escape(nome_modelo)}</b></span>
                <span class='pill'>Referência · <b>{escape(str(dados.get('_hora_referencia', '—')))}</b></span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    contagens = tabela["Risco"].value_counts()
    colunas = st.columns(5)
    for coluna, (_, nivel, cor) in zip(colunas, NIVEIS_RISCO[::-1]):
        coluna.markdown(
            f"<div class='kpi' style='--cor:{cor}'><div class='kpi-v'>{int(contagens.get(nivel, 0))}</div><div class='kpi-r'>{nivel}</div></div>",
            unsafe_allow_html=True,
        )

    com_score = tabela.dropna(subset=["Score"])
    if com_score.empty:
        destaque = "Sem dados de risco disponíveis para o modelo selecionado."
        cor_destaque = COR_NIVEL["Sem dados"]
    else:
        topo = com_score.sort_values(["Score", "Unidade"], ascending=[False, True]).iloc[0]
        cor_destaque = topo["Cor"]
        destaque = (
            f"Maior risco no momento: <b>{escape(str(topo['Unidade']))}</b> — "
            f"<span style='color:{cor_destaque}; font-weight:700;'>{escape(str(topo['Risco']))} · {topo['Score']:.1f}/100</span>. "
            "Clique em um marcador ou em uma unidade da barra lateral para ver a previsão horária."
        )
    sem_dados = int(contagens.get("Sem dados", 0))
    if sem_dados:
        destaque += f" ({sem_dados} unidade(s) sem dados.)"
    st.markdown(f"<div class='destaque' style='--cor:{cor_destaque}'>{destaque}</div>", unsafe_allow_html=True)
    st.markdown("<div class='secao'>Mapa de unidades monitoradas</div>", unsafe_allow_html=True)

    mapa = criar_mapa(tabela, estilo)
    resultado_mapa = st_folium(
        mapa,
        height=680,
        use_container_width=True,
        key=f"mapa_{modelo_id}_{estilo}",
        returned_objects=["last_object_clicked_tooltip"],
    )

    clique = resultado_mapa.get("last_object_clicked_tooltip") if resultado_mapa else None
    if clique and clique in set(tabela["Unidade"]) and clique != st.session_state["ultimo_clique_mapa"]:
        st.session_state["ultimo_clique_mapa"] = clique
        selecionar_estacao(clique)
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
