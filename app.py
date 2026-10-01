"""RUSBÉ em Streamlit.

Painel operacional com barra lateral escura, mapa claro (OpenStreetMap) travado
no Brasil, seletor de hora da previsão, tendência por unidade, consenso entre
modelos, filtros, exportação e detalhe horário com gráficos para cada unidade.
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any, Optional

import altair as alt
import folium
import pandas as pd
import streamlit as st
from branca.element import Element, MacroElement
from jinja2 import Template
from streamlit_folium import st_folium

from analise import (
    consolidar,
    contar_raios,
    filtrar_janela,
    horas_a_frente,
    ler_raios,
    rotulo_horario,
    series_por_unidade,
)
from modelos import MODELOS, TZ_BRASILIA, ErroBuscaModelo, buscar_modelo, horario_local
from relatorio import gerar_pdf, gerar_png
from risco_raio import (
    ICONES,
    NIVEIS_RISCO,
    ROTULOS,
    ParametrosRisco,
    cores_da_paleta,
)
from unidades import ESTACOES, UFS

st.set_page_config(
    page_title="RUSBÉ | Painel Meteorológico",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="auto",  # recolhida automaticamente em telas pequenas
)

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

CONSENSO_PADRAO = ["ecmwf_ifs025", "gfs_seamless", "icon_seamless"]
HORIZONTE_MAX_H = 48
CACHE_HORARIO_LOCAL = "america_sao_paulo_v3"
ESPERA_APOS_FALHA_S = 60  # após uma falha, usa o último dado válido por este tempo sem tentar de novo


# ----------------------------------------------------------------------------
# Dados: cache, tentativas e último dado válido
# ----------------------------------------------------------------------------
@st.cache_data(ttl=600, show_spinner=False)
def _buscar_modelo_cache(modelo_id: str, versao_cache: str) -> dict[str, Any]:
    """Mantém a previsão consultada por dez minutos, separada por versão temporal."""
    return buscar_modelo(modelo_id)


@st.cache_data(ttl=600, show_spinner=False)
def _buscar_varios_cache(modelos: tuple[str, ...], versao_cache: str) -> dict[str, dict[str, Any]]:
    """Consulta vários modelos em paralelo; falhas individuais viram {'_erro': mensagem}."""

    def um(modelo_id: str) -> dict[str, Any]:
        try:
            return buscar_modelo(modelo_id)
        except ErroBuscaModelo as erro:
            return {"_erro": str(erro)}

    with ThreadPoolExecutor(max_workers=max(1, len(modelos))) as pool:
        return dict(zip(modelos, pool.map(um, modelos)))


@st.cache_resource(show_spinner=False)
def _estado_dados() -> dict[str, dict[str, Any]]:
    """Último dado válido e instante da última falha, por modelo (compartilhado entre sessões)."""
    return {"valido": {}, "falha": {}}


def limpar_cache_dados() -> None:
    _buscar_modelo_cache.clear()
    _buscar_varios_cache.clear()
    _estado_dados()["falha"].clear()


def carregar_dados(modelo_id: str) -> tuple[dict[str, Any], Optional[str]]:
    """Devolve (dados, aviso). Se a API falhar, usa o último dado válido e avisa."""
    estado = _estado_dados()
    ultima_falha = estado["falha"].get(modelo_id)
    valido = estado["valido"].get(modelo_id)
    if ultima_falha and valido and time.time() - ultima_falha < ESPERA_APOS_FALHA_S:
        return valido, _aviso_defasado(valido, "serviço indisponível; nova tentativa em instantes")
    try:
        dados = _buscar_modelo_cache(modelo_id, CACHE_HORARIO_LOCAL)
    except ErroBuscaModelo as erro:
        estado["falha"][modelo_id] = time.time()
        if valido:
            return valido, _aviso_defasado(valido, str(erro))
        raise
    estado["valido"][modelo_id] = dados
    estado["falha"].pop(modelo_id, None)
    return dados, None


def _minutos_desde(dados: dict[str, Any]) -> Optional[int]:
    try:
        obtido = datetime.fromisoformat(dados["_obtido_em"])
    except (KeyError, ValueError):
        return None
    return max(0, int((datetime.now(TZ_BRASILIA) - obtido).total_seconds() // 60))


def _aviso_defasado(dados: dict[str, Any], motivo: str) -> str:
    minutos = _minutos_desde(dados)
    quando = f"de {minutos} min atrás" if minutos is not None else "anteriores"
    return f"Exibindo dados {quando} — {motivo}."


def _inicializar_estado() -> None:
    valores_iniciais = {
        "modelo_anterior": None,
        "estacao_popup": None,
        "abrir_popup": False,
        "ultimo_clique_mapa": None,
        "versao_mapa": 0,
        "relatorio": None,
        "fator_cape": 1.0,
        "fator_li": 1.0,
        "peso_cin": 1.0,
    }
    for chave, valor in valores_iniciais.items():
        st.session_state.setdefault(chave, valor)


def recriar_mapa() -> None:
    """Descarta o clique antigo do componente (a posição é preservada no navegador)."""
    st.session_state["versao_mapa"] += 1


def selecionar_estacao(nome: str) -> None:
    """Seleciona a unidade e solicita a abertura do detalhamento (o mapa não se move)."""
    st.session_state["estacao_popup"] = nome
    st.session_state["abrir_popup"] = True


def _numero(valor: Optional[float], casas: int = 0) -> str:
    if valor is None or pd.isna(valor):
        return "—"
    return f"{valor:.{casas}f}"


def _cor_texto(cor_hex: str) -> str:
    """Preto ou branco, conforme o contraste com a cor de fundo."""
    h = cor_hex.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    return "#111827" if 0.299 * r + 0.587 * g + 0.114 * b > 150 else "#ffffff"


def _rgba(cor_hex: str, alfa: float) -> str:
    """Converte #rrggbb em rgba(r, g, b, alfa)."""
    h = cor_hex.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r}, {g}, {b}, {alfa})"


@st.cache_resource(show_spinner=False)
def carregar_geojson(arquivo: str) -> dict[str, Any]:
    """Carrega o contorno/máscara do Brasil empacotado em dados/."""
    return json.loads((RAIZ / "dados" / arquivo).read_text(encoding="utf-8"))


class AjusteBrasil(MacroElement):
    """Mantém o mapa limitado ao Brasil e preserva a posição entre recriações.

    - O zoom mínimo é calculado no navegador a partir do tamanho do mapa, então
      não é possível afastar a visão além do território brasileiro.
    - A posição/zoom atuais são guardados no próprio navegador (sem acionar o
      servidor). Se o mapa for recriado (ao fechar o painel, por exemplo), ele
      reabre exatamente onde estava. Na primeira abertura, enquadra o Brasil.
    """

    _template = Template(
        """
        {% macro script(this, kwargs) %}
        (function () {
            var mapa = {{ this._parent.get_name() }};
            var limites = L.latLngBounds({{ this.limites }});
            var CHAVE = '__rusbeVista';

            function lerVista() {
                try { if (window.parent[CHAVE]) { return window.parent[CHAVE]; } } catch (e) {}
                return null;
            }
            function gravarVista() {
                var c = mapa.getCenter();
                try { window.parent[CHAVE] = {lat: c.lat, lng: c.lng, zoom: mapa.getZoom()}; } catch (e) {}
            }
            function limitarZoom() {
                mapa.invalidateSize();
                mapa.setMinZoom(mapa.getBoundsZoom(limites, false, L.point(8, 8)));
            }
            function enquadrar() {
                mapa.invalidateSize();
                mapa.fitBounds(limites, {padding: [8, 8], animate: false});
                limitarZoom();
            }

            mapa.whenReady(function () {
                var vista = lerVista();
                if (vista) {
                    // Primeiro a posição, depois o zoom mínimo: o inverso dispara uma
                    // animação de zoom que terminaria por cima da posição restaurada.
                    mapa.invalidateSize();
                    mapa.setView([vista.lat, vista.lng], vista.zoom, {animate: false});
                    limitarZoom();
                } else {
                    enquadrar();
                }
                gravarVista();
                mapa.on('moveend', gravarVista);
            });
            window.addEventListener('resize', limitarZoom);

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
                    enquadrar();
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


def _legenda_mapa(cores: dict[str, str], rotulo_hora: str, fonte: str, tem_raios: bool) -> str:
    itens = "".join(
        f"<div class='rl-item'><span class='rl-dot' style='background:{cores[nivel]}'></span>{nivel}</div>"
        for _, nivel, _ in NIVEIS_RISCO[::-1]
    )
    if tem_raios:
        itens += "<div class='rl-item'><span class='rl-dot rl-raio'></span>Raio observado</div>"
    return f"""
    <style>
      .leaflet-tooltip {{ font: 600 12px 'Segoe UI', Arial, sans-serif; color:#1f2933; border:0;
        border-radius:6px; padding:4px 8px; box-shadow:0 2px 8px rgba(15,23,42,.25); }}
      .leaflet-popup-content-wrapper {{ border-radius:12px; box-shadow:0 8px 24px rgba(15,23,42,.28); }}
      .leaflet-popup-content {{ margin:0; }}
      .rusbe-pin-wrap {{ background:transparent; border:0; }}
      .rusbe-pin {{ width:var(--d); height:var(--d); box-sizing:border-box; border-radius:50%; background:var(--c);
        border:2.5px solid #fff; box-shadow:0 0 0 5px var(--h), 0 2px 5px rgba(15,23,42,.35); cursor:pointer;
        display:flex; align-items:center; justify-content:center; color:var(--t);
        font:700 10px/1 'Segoe UI', Arial, sans-serif; letter-spacing:-.02em; transition:box-shadow .15s ease; }}
      .rusbe-pin-wrap:hover .rusbe-pin {{ box-shadow:0 0 0 8px var(--h), 0 2px 6px rgba(15,23,42,.45); }}
      .rusbe-home a {{ font-size:20px; line-height:30px; text-align:center; color:#1f2933; }}
      .rusbe-legenda {{ position:absolute; left:12px; bottom:64px; z-index:1000; background:rgba(255,255,255,.94);
        border:1px solid rgba(15,23,42,.12); border-radius:10px; padding:8px 12px 6px;
        font:12px 'Segoe UI', Arial, sans-serif; color:#1f2933; box-shadow:0 4px 14px rgba(15,23,42,.18); }}
      .rusbe-legenda .rl-titulo {{ font-weight:700; font-size:11px; letter-spacing:.06em; text-transform:uppercase;
        color:#52606d; margin-bottom:4px; }}
      .rusbe-legenda .rl-sub {{ color:#7b8794; font-size:10.5px; margin:-2px 0 4px; }}
      .rl-item {{ display:flex; align-items:center; gap:7px; margin:3px 0; }}
      .rl-dot {{ width:11px; height:11px; border-radius:50%; border:2px solid #fff; box-shadow:0 0 0 1px rgba(15,23,42,.25); }}
      .rl-raio {{ background:#7c3aed; width:7px; height:7px; margin:0 2px; }}
    </style>
    <div class="rusbe-legenda"><div class="rl-titulo">Risco de raios</div>
      <div class="rl-sub">{escape(rotulo_hora)} · {escape(fonte)}</div>{itens}</div>
    """


def _html_popup(linha: pd.Series, cor: str, mostra_raios: bool, raio_km: float) -> str:
    score = linha["Score"]
    score_txt = "—" if pd.isna(score) else f"{score:.1f}/100"
    seta = f" {linha['Tendência']}" if linha["Tendência"] else ""
    extras = ""
    if not pd.isna(linha["Pico 24 h"]):
        extras += (
            f"<div style='display:flex;justify-content:space-between;'><span>Pico 24 h</span>"
            f"<b>{linha['Pico 24 h']:.0f} · {escape(str(linha['Hora do pico']))}</b></div>"
        )
    if linha["Modelos"] > 0:
        extras += (
            f"<div style='display:flex;justify-content:space-between;'><span>Consenso ({int(linha['Modelos'])} modelos)</span>"
            f"<b>{_numero(linha['Score mín.'])}–{_numero(linha['Score máx.'])}</b></div>"
        )
    if mostra_raios and not pd.isna(linha.get("Raios obs.")):
        extras += (
            f"<div style='display:flex;justify-content:space-between;'><span>Raios obs. ({raio_km:.0f} km)</span>"
            f"<b>{int(linha['Raios obs.'])}</b></div>"
        )
    return f"""
    <div style="font-family:'Segoe UI',Arial,sans-serif; min-width:240px; overflow:hidden; border-radius:12px;">
        <div style="background:{cor}; color:{_cor_texto(cor)}; padding:9px 12px;">
            <div style="font-weight:700; font-size:13px; line-height:1.3;">{escape(str(linha['Unidade']))}</div>
            <div style="font-size:12px; opacity:.95; margin-top:2px;">{escape(str(linha['Risco']))} · {score_txt}{seta}</div>
        </div>
        <div style="padding:9px 12px 10px; font-size:12.5px; line-height:1.7; color:#1f2933;">
            <div style="display:flex; justify-content:space-between;"><span>CAPE</span><b>{_numero(linha['CAPE (J/kg)'])} J/kg</b></div>
            <div style="display:flex; justify-content:space-between;"><span>Lifted Index</span><b>{_numero(linha['Lifted Index (°C)'], 1)} °C</b></div>
            <div style="display:flex; justify-content:space-between;"><span>CIN</span><b>{_numero(linha['CIN (J/kg)'])} J/kg</b></div>
            {extras}
            <div style="margin-top:6px; color:#7b8794; font-size:11px;">Clique para abrir a previsão horária.</div>
        </div>
    </div>
    """


def criar_mapa(
    tabela: pd.DataFrame,
    estilo: str,
    cores: dict[str, str],
    mostrar_score: bool,
    rotulo_hora: str,
    fonte: str,
    raios: Optional[pd.DataFrame] = None,
    raio_km: float = 25.0,
) -> folium.Map:
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

    tem_raios = raios is not None and not raios.empty
    if tem_raios:
        amostra = raios if len(raios) <= 4000 else raios.sample(4000, random_state=0)
        grupo = folium.FeatureGroup(name="Raios observados", control=False)
        for lat, lon in zip(amostra["lat"], amostra["lon"]):
            folium.CircleMarker(
                [lat, lon], radius=2.5, weight=0, fill=True, fill_color="#7c3aed", fill_opacity=0.7, interactive=False
            ).add_to(grupo)
        grupo.add_to(mapa)

    for _, linha in tabela.iterrows():
        score = linha["Score"]
        cor = cores.get(linha["Risco"], cores["Sem dados"])
        # Marcador HTML (DivIcon): o tamanho é fixo em pixels, inclusive durante a
        # animação de zoom (camadas de canvas/SVG são escaladas nesse momento).
        diametro = 22 if pd.isna(score) else round(22 + min(float(score), 100) / 12)
        texto = "" if not mostrar_score else ("–" if pd.isna(score) else f"{score:.0f}")
        icone = folium.DivIcon(
            html=(
                f'<div class="rusbe-pin" style="--c:{cor};--h:{_rgba(cor, 0.30)};--t:{_cor_texto(cor)};--d:{diametro}px">'
                f"{texto}</div>"
            ),
            icon_size=(diametro, diametro),
            icon_anchor=(diametro // 2, diametro // 2),
            popup_anchor=(0, -(diametro // 2) - 2),
            class_name="rusbe-pin-wrap",
        )
        folium.Marker(
            location=[linha["Latitude"], linha["Longitude"]],
            icon=icone,
            tooltip=linha["Unidade"],
            popup=folium.Popup(_html_popup(linha, cor, tem_raios, raio_km), max_width=320, auto_pan=False),
            # Risco mais alto sempre por cima quando há sobreposição.
            z_index_offset=0 if pd.isna(score) else int(score * 10),
        ).add_to(mapa)

    mapa.add_child(AjusteBrasil(LIMITES_BRASIL))
    mapa.get_root().html.add_child(Element(_legenda_mapa(cores, rotulo_hora, fonte, tem_raios)))
    return mapa


# ----------------------------------------------------------------------------
# Detalhamento por unidade (janela): cartões, gráficos e tabela horária
# ----------------------------------------------------------------------------
def _tema_grafico(grafico: alt.Chart) -> alt.Chart:
    return (
        grafico.configure(background="transparent")
        .configure_axis(labelColor="#c9d1db", titleColor="#c9d1db", gridColor="#2b323c", domainColor="#3b4350", tickColor="#3b4350")
        .configure_view(strokeWidth=0)
        .configure_legend(labelColor="#c9d1db", titleColor="#c9d1db", orient="bottom", title=None)
    )


def _dados_grafico(nome: str, ctx: dict[str, Any]) -> pd.DataFrame:
    """Séries horárias da unidade (da hora atual até +48 h): CAPE, LI, CIN e score."""
    serie = ctx["dados"].get(nome, {})
    inicio, tempos = serie.get("idx_atual", 0), serie.get("tempos", [])
    rel = ctx["series"][nome]["rel"]
    linhas = []
    for i in range(inicio, min(len(tempos), inicio + HORIZONTE_MAX_H + 1)):
        k = i - inicio
        linhas.append(
            {
                "tempo": pd.to_datetime(tempos[i]),
                "CAPE": serie["cape"][i] if i < len(serie.get("cape", [])) else None,
                "LI": serie["li"][i] if i < len(serie.get("li", [])) else None,
                "CIN": serie["cin"][i] if i < len(serie.get("cin", [])) else None,
                "Score": rel[k] if k < len(rel) else None,
            }
        )
    return pd.DataFrame(linhas)


def _scores_por_modelo(nome: str, ctx: dict[str, Any]) -> pd.DataFrame:
    linhas = []
    for modelo_id, scores in ctx["series"][nome]["por_modelo"].items():
        d = ctx["dados_consenso"][modelo_id].get(nome, {})
        inicio, tempos = d.get("idx_atual", 0), d.get("tempos", [])
        for k, valor in enumerate(scores[: HORIZONTE_MAX_H + 1]):
            if inicio + k < len(tempos):
                linhas.append({"tempo": pd.to_datetime(tempos[inicio + k]), "Modelo": MODELOS[modelo_id][0], "Score": valor})
    return pd.DataFrame(linhas)


def _grafico_score(df: pd.DataFrame, df_modelos: pd.DataFrame, cores: dict[str, str], tempo_sel: pd.Timestamp) -> alt.Chart:
    limites = [0] + [min(limite, 100) for limite, _, _ in NIVEIS_RISCO]
    bandas = pd.DataFrame(
        [{"y0": limites[i], "y1": limites[i + 1], "Nível": rotulo} for i, (_, rotulo, _) in enumerate(NIVEIS_RISCO)]
    )
    eixo_x = alt.X("tempo:T", title=None, axis=alt.Axis(format="%d/%m %Hh", labelAngle=0, tickCount=8))
    eixo_y = alt.Y("Score:Q", scale=alt.Scale(domain=[0, 100]), title="Score")
    camadas = [
        alt.Chart(bandas)
        .mark_rect(opacity=0.17)
        .encode(
            y=alt.Y("y0:Q", scale=alt.Scale(domain=[0, 100]), title="Score"),
            y2="y1:Q",
            color=alt.Color("Nível:N", scale=alt.Scale(domain=ROTULOS, range=[cores[r] for r in ROTULOS]), legend=None),
        )
    ]
    if not df_modelos.empty:
        camadas.append(
            alt.Chart(df_modelos)
            .mark_line(strokeWidth=1.6, opacity=0.85, interpolate="monotone")
            .encode(x=eixo_x, y=eixo_y, color=alt.Color("Modelo:N"), tooltip=["Modelo:N", "tempo:T", alt.Tooltip("Score:Q", format=".1f")])
        )
    camadas.append(
        alt.Chart(df)
        .mark_line(strokeWidth=3, color="#f2f4f8", interpolate="monotone")
        .encode(x=eixo_x, y=eixo_y, tooltip=["tempo:T", alt.Tooltip("Score:Q", format=".1f")])
    )
    camadas.append(
        alt.Chart(pd.DataFrame({"tempo": [tempo_sel]}))
        .mark_rule(color="#e0b400", strokeDash=[4, 3], strokeWidth=2)
        .encode(x="tempo:T")
    )
    return _tema_grafico(alt.layer(*camadas).properties(height=230, width="container"))


def _grafico_variavel(df: pd.DataFrame, coluna: str, titulo: str, cor: str, tempo_sel: pd.Timestamp, linha_zero: bool = False) -> alt.Chart:
    base = alt.Chart(df).encode(
        x=alt.X("tempo:T", title=None, axis=alt.Axis(format="%Hh", labelAngle=0, tickCount=5)),
        y=alt.Y(f"{coluna}:Q", title=titulo),
        tooltip=["tempo:T", alt.Tooltip(f"{coluna}:Q", format=".1f")],
    )
    camadas = [base.mark_area(opacity=0.25, color=cor, line={"color": cor, "strokeWidth": 2}, interpolate="monotone")]
    if linha_zero:
        camadas.append(alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(color="#8895a7", strokeDash=[2, 3]).encode(y="y:Q"))
    camadas.append(
        alt.Chart(pd.DataFrame({"tempo": [tempo_sel]})).mark_rule(color="#e0b400", strokeDash=[4, 3], strokeWidth=1.5).encode(x="tempo:T")
    )
    return _tema_grafico(alt.layer(*camadas).properties(height=150, width="container"))


def _tabela_horaria(nome: str, ctx: dict[str, Any]) -> pd.DataFrame:
    """24 leituras a partir da hora selecionada."""
    from risco_raio import classificar_risco

    serie = ctx["dados"].get(nome, {})
    inicio, tempos = serie.get("idx_atual", 0), serie.get("tempos", [])
    info = ctx["series"][nome]
    desloc = ctx["deslocamento"]
    linhas: list[dict[str, Any]] = []
    for k in range(desloc, min(desloc + 24, len(info["rel"]))):
        i = inicio + k
        score = info["rel"][k]
        nivel = "Sem dados" if score is None else classificar_risco(score)[0]
        try:
            horario = horario_local(tempos[i]).strftime("%H:%M (%d/%m)")
        except (ValueError, IndexError):
            horario = "—"
        if k == desloc:
            horario += "  ◀ agora" if desloc == 0 else "  ◀ selecionada"
        linha = {
            "Horário": horario,
            "CAPE (J/kg)": serie["cape"][i] if i < len(serie.get("cape", [])) else None,
            "Lifted Index": serie["li"][i] if i < len(serie.get("li", [])) else None,
            "CIN (J/kg)": serie["cin"][i] if i < len(serie.get("cin", [])) else None,
            "Score": score,
            "Risco": nivel,
        }
        if info["por_modelo"]:
            vals = [s[k] for s in info["por_modelo"].values() if k < len(s) and s[k] is not None]
            linha["Mín.–máx."] = f"{min(vals):.0f}–{max(vals):.0f}" if vals else "—"
        linhas.append(linha)
    return pd.DataFrame(linhas)


def abrir_detalhamento(nome: str, ctx: dict[str, Any]) -> None:
    """Abre a janela com cartões, gráficos e tabela horária da unidade."""

    @st.dialog(nome, width="large", dismissible=False)
    def janela() -> None:
        cores = ctx["cores"]
        modelo_nome, origem, frequencia = MODELOS[ctx["modelo_id"]]
        fonte = ctx["fonte"]
        st.caption(f"Valores brutos: {modelo_nome} · Origem: {origem} · Atualização: {frequencia} · Score: {fonte}")

        linha_t = ctx["tabela"].loc[ctx["tabela"]["Unidade"] == nome]
        if linha_t.empty or not ctx["series"][nome]["rel"]:
            st.info("Não há série horária disponível para esta unidade no modelo selecionado.")
        else:
            agora = linha_t.iloc[0]
            cor_agora = cores.get(agora["Risco"], cores["Sem dados"])
            score_agora = "—" if pd.isna(agora["Score"]) else f"{agora['Score']:.1f}"
            rotulo = "Risco agora" if ctx["deslocamento"] == 0 else f"Risco em {ctx['rotulo_hora']}"
            cartoes = [
                f"<div class='dlg-card' style='--cor:{cor_agora}'><span>{escape(rotulo)}</span><b>{escape(str(agora['Risco']))}</b><small>score {score_agora}</small></div>",
                f"<div class='dlg-card'><span>CAPE</span><b>{_numero(agora['CAPE (J/kg)'])}</b><small>J/kg</small></div>",
                f"<div class='dlg-card'><span>Lifted Index</span><b>{_numero(agora['Lifted Index (°C)'], 1)}</b><small>°C</small></div>",
                f"<div class='dlg-card'><span>CIN</span><b>{_numero(agora['CIN (J/kg)'])}</b><small>J/kg</small></div>",
            ]
            pico_txt = "—" if pd.isna(agora["Pico 24 h"]) else f"{agora['Pico 24 h']:.0f}"
            delta = agora["Δ 6 h"]
            delta_txt = "" if pd.isna(delta) or not delta else f" {delta:+.0f}"
            seta_txt = agora["Tendência"] or "—"
            hora_pico = escape(str(agora["Hora do pico"]))
            cartoes.append(
                f"<div class='dlg-card'><span>Tendência (6 h)</span><b>{seta_txt}{delta_txt}</b>"
                f"<small>pico 24 h: {pico_txt} · {hora_pico}</small></div>"
            )
            if agora["Modelos"] > 0:
                cartoes.append(
                    f"<div class='dlg-card'><span>Consenso</span><b>{_numero(agora['Score mín.'])}–{_numero(agora['Score máx.'])}</b><small>{int(agora['Modelos'])} modelos</small></div>"
                )
            if ctx["raios"] is not None and not pd.isna(agora.get("Raios obs.")):
                cartoes.append(
                    f"<div class='dlg-card'><span>Raios obs.</span><b>{int(agora['Raios obs.'])}</b><small>em {ctx['raio_km']:.0f} km</small></div>"
                )
            st.markdown(f"<div class='dlg-resumo'>{''.join(cartoes)}</div>", unsafe_allow_html=True)

            df = _dados_grafico(nome, ctx)
            tempo_sel = df["tempo"].iloc[min(ctx["deslocamento"], len(df) - 1)] if not df.empty else pd.Timestamp.now()
            df_modelos = _scores_por_modelo(nome, ctx) if ctx["series"][nome]["por_modelo"] else pd.DataFrame()

            st.markdown("#### Score nas próximas 48 horas")
            st.caption("Linha branca: score usado no mapa. Faixas coloridas: níveis de risco. Linha tracejada: hora selecionada.")
            st.altair_chart(_grafico_score(df, df_modelos, cores, tempo_sel), theme=None)

            st.markdown("#### Variáveis")
            c1, c2, c3 = st.columns(3)
            c1.altair_chart(_grafico_variavel(df, "CAPE", "CAPE (J/kg)", "#e0761f", tempo_sel), theme=None)
            c2.altair_chart(_grafico_variavel(df, "LI", "Lifted Index (°C)", "#56b4e9", tempo_sel, linha_zero=True), theme=None)
            c3.altair_chart(_grafico_variavel(df, "CIN", "CIN (J/kg)", "#a78bfa", tempo_sel, linha_zero=True), theme=None)

            st.markdown("#### Previsão horária — 24 horas a partir da hora selecionada")
            horario = _tabela_horaria(nome, ctx)

            def colorir_linha(linha: pd.Series) -> list[str]:
                cor = cores.get(horario.loc[linha.name, "Risco"], cores["Sem dados"])
                return [f"background-color: {cor}; color: {_cor_texto(cor)};"] * len(linha)

            st.dataframe(
                horario.style.apply(colorir_linha, axis=1),
                hide_index=True,
                width="stretch",
                height=360,
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
            # Componente novo (esquece o clique); o mapa reabre na mesma posição/zoom.
            recriar_mapa()
            st.rerun()

    janela()


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
        [data-testid="stSidebar"] .stButton > button,
        [data-testid="stSidebar"] [data-testid^="stBaseButton-secondary"] {
            border: 1px solid #323a46 !important; background: #212731 !important; color: #f2f4f8 !important;
            border-radius: 9px; min-height: 2.25rem; justify-content: flex-start !important; text-align: left !important; transition: all .15s ease; }
        [data-testid="stSidebar"] .stButton > button *,
        [data-testid="stSidebar"] [data-testid^="stBaseButton-secondary"] * { color: #f2f4f8 !important; text-align: left !important; justify-content: flex-start !important; }
        [data-testid="stSidebar"] .stButton > button:hover,
        [data-testid="stSidebar"] [data-testid^="stBaseButton-secondary"]:hover { border-color: #e0b400 !important; background: #2b323d !important; transform: translateX(2px); }
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
        .dlg-resumo { grid-template-columns:repeat(auto-fit, minmax(150px, 1fr)) !important; }
        [data-testid="stSidebar"] [data-testid="stExpander"] { border:1px solid #2b323c; border-radius:10px; background:#1b2027; }
        [data-testid="stSidebar"] [data-testid="stExpander"] summary { font-weight:600; }
        [data-testid="stMain"] [data-testid="stSlider"] { margin-top:.5rem; }
        .nota-tab { color:#a9b3c1; font-size:.82rem; margin:.1rem 0 .5rem; }
        .rodape-sec { margin-top:.4rem; color:#8895a7; font-size:.78rem; }
        @media (max-width: 760px) {
            .kpi .kpi-v { font-size:1.45rem; }
            .rusbe-titulo { font-size:1.25rem; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _restaurar_calibracao() -> None:
    st.session_state["fator_cape"] = 1.0
    st.session_state["fator_li"] = 1.0
    st.session_state["peso_cin"] = 1.0


@st.cache_data(show_spinner=False)
def _ler_raios_cache(conteudo: bytes) -> pd.DataFrame:
    import io

    return ler_raios(io.BytesIO(conteudo))


def serie_longa(dados: dict[str, Any], series: dict[str, dict[str, Any]]) -> pd.DataFrame:
    """Série horária de todas as unidades (formato longo), para análise/calibração externa."""
    linhas: list[dict[str, Any]] = []
    for estacao in ESTACOES:
        nome = estacao["nome"]
        serie = dados.get(nome, {})
        inicio, tempos = serie.get("idx_atual", 0), serie.get("tempos", [])
        info = series[nome]
        for k, score in enumerate(info["rel"][: HORIZONTE_MAX_H + 1]):
            i = inicio + k
            if i >= len(tempos):
                break
            linha = {
                "Unidade": nome,
                "UF": estacao["uf"],
                "Horário local": tempos[i],
                "Horas à frente": k,
                "CAPE (J/kg)": serie["cape"][i] if i < len(serie.get("cape", [])) else None,
                "Lifted Index (°C)": serie["li"][i] if i < len(serie.get("li", [])) else None,
                "CIN (J/kg)": serie["cin"][i] if i < len(serie.get("cin", [])) else None,
                "Score": score,
            }
            for modelo_id, scores in info["por_modelo"].items():
                linha[f"Score {modelo_id}"] = scores[k] if k < len(scores) else None
            linhas.append(linha)
    return pd.DataFrame(linhas)


def _csv_br(df: pd.DataFrame) -> bytes:
    """CSV que abre corretamente no Excel em português (; e vírgula decimal, UTF-8 com BOM)."""
    df = df.copy()
    for coluna, casas in (("CAPE (J/kg)", 0), ("Lifted Index (°C)", 1), ("CIN (J/kg)", 0)):
        if coluna in df:
            df[coluna] = df[coluna].round(casas)
    return df.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig")


@st.fragment
def secao_mapa(tabela_vis: pd.DataFrame, ctx: dict[str, Any], estilo: str, mostrar_score: bool, altura: int) -> None:
    """Mapa + clique + janela de detalhe. Como fragmento, clicar em um marcador não recarrega o resto da página."""
    mapa = criar_mapa(
        tabela_vis,
        estilo,
        ctx["cores"],
        mostrar_score,
        ctx["rotulo_hora"],
        ctx["fonte"],
        ctx["raios"],
        ctx["raio_km"],
    )
    resultado_mapa = st_folium(
        mapa,
        height=altura,
        use_container_width=True,
        key=f"mapa_{ctx['modelo_id']}_{estilo}_{st.session_state['versao_mapa']}",
        returned_objects=["last_object_clicked_tooltip"],
    )

    clique = resultado_mapa.get("last_object_clicked_tooltip") if resultado_mapa else None
    if clique and clique in set(tabela_vis["Unidade"]) and clique != st.session_state["ultimo_clique_mapa"]:
        st.session_state["ultimo_clique_mapa"] = clique
        selecionar_estacao(clique)

    if st.session_state["abrir_popup"] and st.session_state["estacao_popup"]:
        abrir_detalhamento(st.session_state["estacao_popup"], ctx)


def main() -> None:
    _inicializar_estado()
    renderizar_estilo()

    # ------------------------------------------------------------------ barra lateral (controles)
    with st.sidebar:
        st.markdown(
            "<div class='marca-lateral'><div class='raio'>⚡</div><b>RUSBÉ</b></div>",
            unsafe_allow_html=True,
        )
        st.caption("PAINEL METEOROLÓGICO")

        with st.expander("Dados", expanded=True):
            modelo_id = st.selectbox(
                "Modelo numérico",
                options=list(MODELOS),
                format_func=lambda chave: MODELOS[chave][0],
            )
            nome_modelo, origem, frequencia = MODELOS[modelo_id]
            st.caption(f"Origem: {origem} · Atualiza: {frequencia}")
            usar_consenso = st.toggle(
                "Consenso entre modelos",
                help="O score do mapa passa a ser a média do score calculado em cada modelo escolhido.",
            )
            modelos_consenso: list[str] = []
            if usar_consenso:
                modelos_consenso = st.multiselect(
                    "Modelos do consenso",
                    options=list(MODELOS),
                    default=CONSENSO_PADRAO,
                    format_func=lambda chave: MODELOS[chave][0],
                    max_selections=5,
                )
            if st.button("Atualizar dados de todos os modelos", width="stretch"):
                limpar_cache_dados()
                st.session_state["ultimo_clique_mapa"] = None
                recriar_mapa()

        with st.expander("Mapa"):
            estilo = st.selectbox("Estilo do mapa", options=list(TILES), index=0)
            daltonismo = st.toggle("Paleta para daltonismo", help="Azul → amarelo → laranja → vinho, variando também a luminosidade.")
            mostrar_score = st.toggle("Mostrar o score dentro das bolinhas", value=True)
            altura = st.slider("Altura do mapa (px)", 420, 900, 680, step=20)

        with st.expander("Calibração da heurística"):
            st.caption("1,0 = regra original. Ajuste a sensibilidade e compare com as observações.")
            st.slider("Sensibilidade ao CAPE (×)", 0.5, 2.0, step=0.05, key="fator_cape")
            st.slider("Sensibilidade ao Lifted Index (×)", 0.5, 2.0, step=0.05, key="fator_li")
            st.slider("Peso do CIN (×)", 0.0, 2.0, step=0.05, key="peso_cin")
            st.button("Restaurar padrão", on_click=_restaurar_calibracao, width="stretch")

        with st.expander("Raios observados (opcional)"):
            st.caption("CSV com colunas lat e lon (e, opcionalmente, tempo), por exemplo exportado do GLM/GOES.")
            arquivo_raios = st.file_uploader("Arquivo de raios", type=["csv", "txt"], label_visibility="collapsed")
            raio_km = float(st.slider("Raio ao redor de cada unidade (km)", 5, 100, 25, step=5))
            limitar_janela = st.toggle("Usar só as últimas horas do arquivo")
            janela_h = float(st.number_input("Últimas horas", min_value=1, max_value=72, value=3)) if limitar_janela else None

        with st.expander("Filtros"):
            ufs_selecionadas = st.multiselect("Unidade da federação", options=UFS, placeholder="Todas")

    if modelo_id != st.session_state["modelo_anterior"]:
        st.session_state["modelo_anterior"] = modelo_id
        st.session_state["ultimo_clique_mapa"] = None
        st.session_state["abrir_popup"] = False
        recriar_mapa()

    paleta = "daltonismo" if daltonismo else "padrao"
    cores = cores_da_paleta(paleta)
    icones = ICONES[paleta]
    parametros = ParametrosRisco(st.session_state["fator_cape"], st.session_state["fator_li"], st.session_state["peso_cin"])

    # ------------------------------------------------------------------ dados
    try:
        with st.spinner(f"Buscando {nome_modelo} para {len(ESTACOES)} unidades..."):
            dados, aviso = carregar_dados(modelo_id)
    except ErroBuscaModelo as erro:
        st.error(f"Falha ao buscar o modelo selecionado: {erro}")
        st.stop()
    except Exception as erro:
        st.error(f"Ocorreu um erro inesperado ao carregar o painel: {erro}")
        st.stop()
    if aviso:
        st.warning(aviso)

    dados_consenso: Optional[dict[str, dict[str, Any]]] = None
    if usar_consenso:
        if len(modelos_consenso) < 2:
            st.sidebar.info("Escolha ao menos 2 modelos para o consenso; usando só o modelo selecionado.")
        else:
            with st.spinner(f"Buscando {len(modelos_consenso)} modelos para o consenso..."):
                brutos = _buscar_varios_cache(tuple(sorted(modelos_consenso)), CACHE_HORARIO_LOCAL)
            validos = {m: d for m, d in brutos.items() if "_erro" not in d}
            falhos = [MODELOS[m][0] for m, d in brutos.items() if "_erro" in d]
            if falhos:
                st.sidebar.warning("Sem dados de: " + ", ".join(falhos))
            if len(validos) >= 2:
                dados_consenso = validos
            else:
                st.sidebar.warning("Menos de 2 modelos disponíveis; usando só o modelo selecionado.")

    raios: Optional[pd.DataFrame] = None
    if arquivo_raios is not None:
        try:
            raios = filtrar_janela(_ler_raios_cache(arquivo_raios.getvalue()), janela_h)
        except Exception as erro:  # arquivo malformado: informa e segue sem a camada
            st.sidebar.error(f"Não foi possível ler o arquivo de raios: {erro}")

    fonte = f"consenso de {len(dados_consenso)} modelos" if dados_consenso else nome_modelo

    # ------------------------------------------------------------------ áreas da página (ordem visual)
    area_cabecalho = st.container()
    area_kpi = st.container()
    area_hora = st.container()
    area_filtro = st.container()
    area_destaque = st.container()

    limite_h = min([HORIZONTE_MAX_H, horas_a_frente(dados)] + [horas_a_frente(d) for d in (dados_consenso or {}).values()])
    with area_hora:
        if limite_h > 0:
            st.session_state["deslocamento"] = min(st.session_state.get("deslocamento", 0), limite_h)
            deslocamento = st.slider(
                "Hora da previsão exibida no mapa (horas a partir de agora)",
                0,
                limite_h,
                key="deslocamento",
                format="+%d h",
            )
        else:
            deslocamento = 0
    rotulo_hora = rotulo_horario(dados, deslocamento)

    # ------------------------------------------------------------------ cálculo
    series = series_por_unidade(dados, parametros, dados_consenso)
    tabela = consolidar(dados, series, deslocamento)
    if raios is not None:
        tabela["Raios obs."] = contar_raios(tabela, raios, raio_km)
    tabela_uf = tabela[tabela["UF"].isin(ufs_selecionadas)] if ufs_selecionadas else tabela
    contagens = tabela_uf["Risco"].value_counts()

    with area_filtro:
        niveis = list(reversed(ROTULOS))
        escolhidos = st.pills(
            "Filtrar por nível de risco",
            niveis,
            selection_mode="multi",
            format_func=lambda nivel: f"{icones[nivel]} {nivel} ({int(contagens.get(nivel, 0))})",
            label_visibility="collapsed",
            key="filtro_niveis",
        )
    tabela_vis = tabela_uf[tabela_uf["Risco"].isin(escolhidos)] if escolhidos else tabela_uf

    ctx = {
        "dados": dados,
        "series": series,
        "dados_consenso": dados_consenso or {},
        "tabela": tabela,
        "cores": cores,
        "deslocamento": deslocamento,
        "rotulo_hora": rotulo_hora,
        "modelo_id": modelo_id,
        "fonte": fonte,
        "raios": raios,
        "raio_km": raio_km,
    }

    # ------------------------------------------------------------------ barra lateral (lista de unidades)
    with st.sidebar:
        st.divider()
        st.caption(f"UNIDADES ({len(tabela_vis)} de {len(ESTACOES)})")
        termo = st.text_input("Pesquisar unidade", placeholder="Pesquisar unidade...", label_visibility="collapsed")
        ordem = st.radio("Ordenar por", ["Nome", "Maior risco", "Vai piorar"], horizontal=True, label_visibility="collapsed")
        lista = tabela_vis[tabela_vis["Unidade"].str.casefold().str.contains(termo.casefold().strip(), na=False, regex=False)]
        if ordem == "Maior risco":
            lista = lista.sort_values(["Score", "Unidade"], ascending=[False, True], na_position="last", kind="stable")
        elif ordem == "Vai piorar":
            lista = lista.sort_values(["Δ 6 h", "Score", "Unidade"], ascending=[False, False, True], na_position="last", kind="stable")
        if lista.empty:
            st.caption("Nenhuma unidade encontrada.")
        for _, linha in lista.iterrows():
            score_txt = "—" if pd.isna(linha["Score"]) else f"{linha['Score']:.0f}"
            seta = f" {linha['Tendência']}" if linha["Tendência"] else ""
            if st.button(
                f"{icones.get(linha['Risco'], '⚫')} {score_txt}{seta} · {linha['Unidade']}",
                key=f"unidade_{linha['Unidade']}",
                width="stretch",
                help=f"{linha['Risco']} — abrir previsão horária",
            ):
                selecionar_estacao(linha["Unidade"])

    # ------------------------------------------------------------------ cabeçalho, indicadores e destaque
    minutos = _minutos_desde(dados)
    sufixo_hora = " · agora" if deslocamento == 0 else f" · +{deslocamento} h"
    pilulas = [
        f"<span class='pill'>Score · <b>{escape(fonte)}</b></span>",
        f"<span class='pill'>Hora exibida · <b>{escape(rotulo_hora)}{sufixo_hora}</b></span>",
    ]
    if minutos is not None:
        pilulas.append(f"<span class='pill'>Dados · <b>há {minutos} min</b></span>")
    # HTML numa única linha por bloco: linhas em branco quebrariam o parser de Markdown.
    cabecalho_html = (
        "<div class='rusbe-cabecalho'><div class='raio'>⚡</div>"
        "<div><p class='rusbe-titulo'>RUSBÉ</p>"
        "<p class='rusbe-subtitulo'>Rastreamento e Utilização de Sistema Baseado em Eletricidade Atmosférica</p></div>"
        f"<div class='rusbe-pills'>{''.join(pilulas)}</div></div>"
    )
    with area_cabecalho:
        st.markdown(cabecalho_html, unsafe_allow_html=True)
    with area_kpi:
        for coluna, nivel in zip(st.columns(5), niveis):
            coluna.markdown(
                f"<div class='kpi' style='--cor:{cores[nivel]}'><div class='kpi-v'>{int(contagens.get(nivel, 0))}</div>"
                f"<div class='kpi-r'>{nivel}</div></div>",
                unsafe_allow_html=True,
            )

    com_score = tabela_uf.dropna(subset=["Score"])
    with area_destaque:
        if com_score.empty:
            texto, cor_destaque = "Sem dados de risco disponíveis para o modelo selecionado.", cores["Sem dados"]
        else:
            topo = com_score.sort_values(["Score", "Unidade"], ascending=[False, True]).iloc[0]
            cor_destaque = cores.get(topo["Risco"], cores["Sem dados"])
            texto = (
                f"Maior risco em {escape(rotulo_hora)}: <b>{escape(str(topo['Unidade']))}</b> — "
                f"<span style='color:{cor_destaque}; font-weight:700;'>{escape(str(topo['Risco']))} · {topo['Score']:.1f}/100</span>."
            )
            subindo = com_score[com_score["Tendência"] == "▲"].sort_values("Δ 6 h", ascending=False)
            if not subindo.empty:
                lider = subindo.iloc[0]
                texto += (
                    f" <b>{len(subindo)}</b> unidade(s) com tendência de alta nas próximas 6 h "
                    f"(maior alta: <b>{escape(str(lider['Unidade']))}</b>, {lider['Δ 6 h']:+.0f})."
                )
        sem_dados = int(contagens.get("Sem dados", 0))
        if sem_dados:
            texto += f" ({sem_dados} unidade(s) sem dados.)"
        st.markdown(f"<div class='destaque' style='--cor:{cor_destaque}'>{texto}</div>", unsafe_allow_html=True)
        st.markdown("<div class='secao'>Mapa de unidades monitoradas</div>", unsafe_allow_html=True)

    # ------------------------------------------------------------------ mapa (fragmento)
    secao_mapa(tabela_vis, ctx, estilo, mostrar_score, altura)

    # ------------------------------------------------------------------ tabela e exportação
    with st.expander("Tabela e exportação"):
        aba_tabela, aba_exportar = st.tabs(["Tabela", "Exportar"])
        with aba_tabela:
            st.markdown(
                f"<div class='nota-tab'>Leitura em {escape(rotulo_hora)} · score: {escape(fonte)}. "
                "Δ 6 h = maior variação do score nas próximas 6 h.</div>",
                unsafe_allow_html=True,
            )
            colunas = ["Unidade", "UF", "Risco", "Score", "Tendência", "Δ 6 h", "Pico 24 h", "Hora do pico",
                       "CAPE (J/kg)", "Lifted Index (°C)", "CIN (J/kg)"]
            if dados_consenso:
                colunas += ["Score mín.", "Score máx.", "Modelos"]
            if raios is not None:
                colunas += ["Raios obs."]
            exibicao = tabela_vis[colunas].sort_values("Score", ascending=False, na_position="last")

            def colorir_risco(valor: str) -> str:
                cor = cores.get(valor, cores["Sem dados"])
                return f"background-color: {cor}; color: {_cor_texto(cor)}; font-weight:700;"

            st.dataframe(
                exibicao.style.map(colorir_risco, subset=["Risco"]),
                hide_index=True,
                width="stretch",
                height=420,
                column_config={
                    "Score": st.column_config.NumberColumn(format="%.1f"),
                    "Δ 6 h": st.column_config.NumberColumn(format="%+.0f"),
                    "Pico 24 h": st.column_config.NumberColumn(format="%.0f"),
                    "CAPE (J/kg)": st.column_config.NumberColumn(format="%.0f"),
                    "Lifted Index (°C)": st.column_config.NumberColumn(format="%.1f"),
                    "CIN (J/kg)": st.column_config.NumberColumn(format="%.0f"),
                    "Score mín.": st.column_config.NumberColumn(format="%.0f"),
                    "Score máx.": st.column_config.NumberColumn(format="%.0f"),
                },
            )
        with aba_exportar:
            carimbo = datetime.now(TZ_BRASILIA).strftime("%Y%m%d_%H%M")
            c1, c2 = st.columns(2)
            c1.download_button(
                "Baixar tabela atual (CSV)",
                _csv_br(tabela.drop(columns=["Latitude", "Longitude"]).assign(**{"Horário": rotulo_hora, "Fonte do score": fonte})),
                file_name=f"rusbe_tabela_{carimbo}.csv",
                mime="text/csv",
                on_click="ignore",
                width="stretch",
            )
            c2.download_button(
                "Baixar séries horárias de 48 h (CSV)",
                _csv_br(serie_longa(dados, series)),
                file_name=f"rusbe_series_{carimbo}.csv",
                mime="text/csv",
                on_click="ignore",
                width="stretch",
                help="CAPE, LI, CIN e score hora a hora de todas as unidades — útil para calibrar com observações.",
            )
            st.markdown("<div class='rodape-sec'>Mapa estático e relatório (mapa + ranking de todas as unidades):</div>", unsafe_allow_html=True)
            if st.button("Gerar mapa PNG e relatório PDF", width="stretch"):
                titulo = "RUSBÉ — Risco de raios"
                subtitulo = f"{rotulo_hora} · score: {fonte} · gerado em {datetime.now(TZ_BRASILIA):%d/%m/%Y %H:%M}"
                with st.spinner("Gerando arquivos..."):
                    st.session_state["relatorio"] = {
                        "png": gerar_png(tabela, titulo, subtitulo, paleta),
                        "pdf": gerar_pdf(tabela, titulo, subtitulo, paleta),
                        "descricao": subtitulo,
                        "carimbo": carimbo,
                    }
            relatorio = st.session_state.get("relatorio")
            if relatorio:
                st.caption(f"Pronto: {relatorio['descricao']}")
                d1, d2 = st.columns(2)
                d1.download_button("Baixar mapa (PNG)", relatorio["png"], file_name=f"rusbe_mapa_{relatorio['carimbo']}.png",
                                   mime="image/png", on_click="ignore", width="stretch")
                d2.download_button("Baixar relatório (PDF)", relatorio["pdf"], file_name=f"rusbe_relatorio_{relatorio['carimbo']}.pdf",
                                   mime="application/pdf", on_click="ignore", width="stretch")

    with st.expander("Como interpretar o painel"):
        st.write(
            "O score é uma heurística baseada em CAPE, Lifted Index e CIN. CAPE alto e Lifted Index mais negativo "
            "elevam o risco; CIN elevado reduz a probabilidade de disparo convectivo. A seta indica a tendência do score "
            "nas próximas 6 h (▲ sobe, ▼ desce, ▬ estável). No modo consenso, o score é a média dos modelos escolhidos e a "
            "faixa mín.–máx. mostra a divergência entre eles. O painel serve ao acompanhamento meteorológico e não substitui "
            "alertas oficiais ou sistemas de detecção de descargas atmosféricas."
        )
        st.caption(f"Última renderização local: {datetime.now(TZ_BRASILIA).strftime('%d/%m/%Y %H:%M:%S')} (America/Sao_Paulo).")


if __name__ == "__main__":
    main()
