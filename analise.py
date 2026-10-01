"""Análise dos dados do RUSBÉ (sem dependência do Streamlit).

Concentra o cálculo de séries de score, tendência, consenso entre modelos e
contagem de raios observados, para ser reutilizado pelo app, pelos alertas e
pelo relatório.
"""

from __future__ import annotations

import math
from typing import Any, Iterable, Optional

import numpy as np
import pandas as pd

from modelos import horario_local
from risco_raio import PARAMETROS_PADRAO, ParametrosRisco, calcular_risco, classificar_risco
from unidades import ESTACOES

JANELA_TENDENCIA_H = 6  # horas à frente usadas para decidir ▲ / ▼
LIMIAR_TENDENCIA = 10.0  # variação mínima de score para indicar subida/descida
JANELA_PICO_H = 24  # horas à frente usadas para localizar o pico

SETA_SOBE, SETA_DESCE, SETA_ESTAVEL = "▲", "▼", "▬"


def _valor(serie: list[Optional[float]], indice: int) -> Optional[float]:
    return serie[indice] if 0 <= indice < len(serie) else None


def scores_relativos(serie: dict[str, Any], parametros: ParametrosRisco = PARAMETROS_PADRAO) -> list[Optional[float]]:
    """Scores horários a partir da hora atual: posição 0 = agora, 1 = +1 h, …"""
    inicio = serie.get("idx_atual", 0)
    n = len(serie.get("tempos", []))
    capes, lis, cins = serie.get("cape", []), serie.get("li", []), serie.get("cin", [])
    return [
        calcular_risco(_valor(capes, i), _valor(lis, i), _valor(cins, i), parametros)[0]
        for i in range(inicio, n)
    ]


def horas_a_frente(dados: dict[str, Any]) -> int:
    """Maior deslocamento (em horas, a partir de agora) disponível para todas as unidades."""
    restantes = [
        len(s.get("tempos", [])) - s.get("idx_atual", 0) - 1
        for nome, s in dados.items()
        if not nome.startswith("_") and isinstance(s, dict)
    ]
    return max(0, min(restantes)) if restantes else 0


def rotulo_horario(dados: dict[str, Any], deslocamento: int) -> str:
    """Horário local (HH:MM dd/mm) do deslocamento informado."""
    for nome, serie in dados.items():
        if nome.startswith("_") or not isinstance(serie, dict):
            continue
        tempos, inicio = serie.get("tempos", []), serie.get("idx_atual", 0)
        if 0 <= inicio + deslocamento < len(tempos):
            try:
                return horario_local(tempos[inicio + deslocamento]).strftime("%H:%M (%d/%m)")
            except ValueError:
                return tempos[inicio + deslocamento]
    return "—"


def series_por_unidade(
    dados: dict[str, Any],
    parametros: ParametrosRisco = PARAMETROS_PADRAO,
    dados_consenso: Optional[dict[str, dict[str, Any]]] = None,
) -> dict[str, dict[str, Any]]:
    """Séries de score por unidade.

    Retorna, por unidade: ``rel`` (série usada no mapa — o modelo selecionado ou a
    média do consenso) e ``por_modelo`` (série de cada modelo do consenso).
    """
    resultado: dict[str, dict[str, Any]] = {}
    for estacao in ESTACOES:
        nome = estacao["nome"]
        if dados_consenso:
            por_modelo = {
                modelo: scores_relativos(d.get(nome, {}), parametros) for modelo, d in dados_consenso.items()
            }
            tamanho = min((len(s) for s in por_modelo.values()), default=0)
            media: list[Optional[float]] = []
            for i in range(tamanho):
                valores = [s[i] for s in por_modelo.values() if s[i] is not None]
                media.append(round(sum(valores) / len(valores), 1) if valores else None)
            resultado[nome] = {"rel": media, "por_modelo": por_modelo, "consenso": True}
        else:
            resultado[nome] = {"rel": scores_relativos(dados.get(nome, {}), parametros), "por_modelo": {}, "consenso": False}
    return resultado


def tendencia(rel: list[Optional[float]], deslocamento: int = 0) -> dict[str, Any]:
    """Seta de tendência (próximas 6 h), variação e pico (próximas 24 h) a partir do deslocamento."""
    agora = rel[deslocamento] if 0 <= deslocamento < len(rel) else None
    vazio = {"seta": "", "delta6h": np.nan, "pico": np.nan, "desloc_pico": None}
    if agora is None:
        return vazio

    def janela(horas: int) -> list[tuple[int, float]]:
        fim = min(len(rel), deslocamento + horas + 1)
        return [(i, rel[i]) for i in range(deslocamento + 1, fim) if rel[i] is not None]

    proximas = janela(JANELA_TENDENCIA_H)
    delta_alta = max((v for _, v in proximas), default=agora) - agora
    delta_baixa = min((v for _, v in proximas), default=agora) - agora
    if delta_alta >= LIMIAR_TENDENCIA:
        seta, delta = SETA_SOBE, delta_alta
    elif delta_baixa <= -LIMIAR_TENDENCIA:
        seta, delta = SETA_DESCE, delta_baixa
    else:
        seta, delta = SETA_ESTAVEL, 0.0

    candidatos = [(deslocamento, agora)] + janela(JANELA_PICO_H)
    desloc_pico, pico = max(candidatos, key=lambda par: (par[1], -par[0]))
    return {"seta": seta, "delta6h": round(delta, 1), "pico": pico, "desloc_pico": desloc_pico}


def consolidar(
    dados: dict[str, Any],
    series: dict[str, dict[str, Any]],
    deslocamento: int = 0,
) -> pd.DataFrame:
    """Tabela com a leitura de todas as unidades no deslocamento (horas a partir de agora)."""
    linhas: list[dict[str, Any]] = []
    for estacao in ESTACOES:
        nome = estacao["nome"]
        serie = dados.get(nome, {})
        i = serie.get("idx_atual", 0) + deslocamento
        info = series[nome]
        rel = info["rel"]
        score = rel[deslocamento] if 0 <= deslocamento < len(rel) else None
        if score is None:
            nivel = "Sem dados"
        else:
            nivel = classificar_risco(score)[0]

        por_modelo = [
            s[deslocamento] for s in info["por_modelo"].values() if 0 <= deslocamento < len(s) and s[deslocamento] is not None
        ]
        tend = tendencia(rel, deslocamento)
        pico_hora = rotulo_horario({nome: serie}, tend["desloc_pico"]) if tend["desloc_pico"] is not None else "—"

        linhas.append(
            {
                "Unidade": nome,
                "UF": estacao["uf"],
                "CAPE (J/kg)": _valor(serie.get("cape", []), i),
                "Lifted Index (°C)": _valor(serie.get("li", []), i),
                "CIN (J/kg)": _valor(serie.get("cin", []), i),
                "Risco": nivel,
                "Score": score,
                "Tendência": tend["seta"],
                "Δ 6 h": tend["delta6h"],
                "Pico 24 h": tend["pico"],
                "Hora do pico": pico_hora,
                "Score mín.": min(por_modelo) if por_modelo else np.nan,
                "Score máx.": max(por_modelo) if por_modelo else np.nan,
                "Modelos": len(por_modelo),
                "Latitude": estacao["lat"],
                "Longitude": estacao["lon"],
            }
        )
    return pd.DataFrame(linhas).sort_values("Unidade", kind="stable").reset_index(drop=True)


# ----------------------------------------------------------------------------
# Raios observados (arquivo opcional, por exemplo exportado do GLM/GOES)
# ----------------------------------------------------------------------------
_NOMES_LAT = ("lat", "latitude", "lat_deg", "event_lat", "flash_lat")
_NOMES_LON = ("lon", "lng", "long", "longitude", "lon_deg", "event_lon", "flash_lon")
_NOMES_TEMPO = ("time", "datetime", "timestamp", "data_hora", "datahora", "data", "flash_time_offset_of_first_event", "t")


def ler_raios(origem: Any) -> pd.DataFrame:
    """Lê um CSV de raios e devolve colunas ``lat``, ``lon`` e (se existir) ``tempo``."""
    bruto = pd.read_csv(origem, sep=None, engine="python")
    minusculas = {c: str(c).strip().lower() for c in bruto.columns}

    def achar(nomes: Iterable[str]) -> Optional[str]:
        for coluna, nome in minusculas.items():
            if nome in nomes:
                return coluna
        return None

    c_lat, c_lon, c_tempo = achar(_NOMES_LAT), achar(_NOMES_LON), achar(_NOMES_TEMPO)
    if c_lat is None or c_lon is None:
        raise ValueError("O arquivo precisa ter colunas de latitude e longitude (ex.: lat, lon).")

    saida = pd.DataFrame(
        {"lat": pd.to_numeric(bruto[c_lat], errors="coerce"), "lon": pd.to_numeric(bruto[c_lon], errors="coerce")}
    )
    if c_tempo is not None:
        saida["tempo"] = pd.to_datetime(bruto[c_tempo], errors="coerce", utc=True)
    saida = saida.dropna(subset=["lat", "lon"])
    return saida[(saida["lat"].between(-90, 90)) & (saida["lon"].between(-180, 180))].reset_index(drop=True)


def filtrar_janela(raios: pd.DataFrame, ultimas_horas: Optional[float]) -> pd.DataFrame:
    """Mantém só as últimas ``ultimas_horas`` do arquivo (relativas ao raio mais recente)."""
    if ultimas_horas is None or "tempo" not in raios or raios["tempo"].isna().all():
        return raios
    limite = raios["tempo"].max() - pd.Timedelta(hours=ultimas_horas)
    return raios[raios["tempo"] >= limite].reset_index(drop=True)


def contar_raios(tabela: pd.DataFrame, raios: pd.DataFrame, raio_km: float) -> pd.Series:
    """Quantidade de raios a até ``raio_km`` de cada unidade (distância de haversine)."""
    if raios.empty:
        return pd.Series(0, index=tabela.index, dtype=int)
    lat_r = np.radians(raios["lat"].to_numpy())
    lon_r = np.radians(raios["lon"].to_numpy())
    contagens = []
    for lat, lon in zip(tabela["Latitude"], tabela["Longitude"]):
        la, lo = math.radians(lat), math.radians(lon)
        a = np.sin((lat_r - la) / 2) ** 2 + math.cos(la) * np.cos(lat_r) * np.sin((lon_r - lo) / 2) ** 2
        distancia = 2 * 6371.0088 * np.arcsin(np.sqrt(a))
        contagens.append(int((distancia <= raio_km).sum()))
    return pd.Series(contagens, index=tabela.index, dtype=int)
