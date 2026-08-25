"""Consulta de modelos numéricos na API de previsão meteorológica."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

import requests

from unidades import ESTACOES

API_URL = "https://api.open-meteo.com/v1/forecast"
TIMEOUT = 25
VARIAVEIS_HOURLY = "cape,lifted_index,convective_inhibition"

MODELOS = {
    "best_match": ("Best Match (automático)", "—", "Automática"),
    "ecmwf_ifs025": ("ECMWF IFS 0,25°", "União Europeia", "A cada 6 horas"),
    "ecmwf_aifs025": ("ECMWF AIFS 0,25° (IA)", "União Europeia", "A cada 6 horas"),
    "gfs_seamless": ("NOAA GFS Seamless", "Estados Unidos", "A cada 1 hora"),
    "icon_seamless": ("DWD ICON Seamless", "Alemanha", "A cada 3 horas"),
    "gem_seamless": ("GEM Seamless", "Canadá", "A cada 6 horas"),
    "meteofrance_seamless": ("Météo-France Seamless", "França", "A cada 1 hora"),
    "jma_seamless": ("JMA Seamless (GSM)", "Japão", "A cada 6 horas"),
    "kma_seamless": ("KMA Seamless (GDPS)", "Coreia do Sul", "A cada 6 horas"),
    "ukmo_seamless": ("UK Met Office Seamless", "Reino Unido", "A cada 1 hora"),
    "bom_access_global": ("BOM ACCESS-G", "Austrália", "A cada 6 horas"),
    "cma_grapes_global": ("CMA GRAPES Global", "China", "A cada 6 horas"),
}


class ErroBuscaModelo(RuntimeError):
    """Erro tratado durante a obtenção de previsão de um modelo."""


def _indice_hora_atual(tempos: list[str]) -> int:
    """Localiza, na série horária, a previsão mais próxima do horário atual."""
    if not tempos:
        return 0

    agora = datetime.now().astimezone()
    alvos: list[datetime] = []
    for tempo in tempos:
        try:
            alvos.append(datetime.fromisoformat(tempo).astimezone())
        except ValueError:
            alvos.append(agora)
    return min(range(len(alvos)), key=lambda indice: abs(alvos[indice] - agora))


def _como_numero(valor: Any) -> Optional[float]:
    """Normaliza valores ausentes devolvidos pela API."""
    if valor is None:
        return None
    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def buscar_modelo(model_id: str, session: Optional[requests.Session] = None) -> dict[str, Any]:
    """Busca CAPE, Lifted Index e CIN horários para todas as estações.

    A API recebe coordenadas separadas por vírgula e retorna uma série por
    localização. O resultado é indexado pelo nome da estação e inclui uma
    referência temporal, permitindo que a interface represente a situação
    atual e o horizonte de previsão.
    """
    if model_id not in MODELOS:
        raise ErroBuscaModelo(f"Modelo inválido: {model_id}")

    lats = ",".join(str(estacao["lat"]) for estacao in ESTACOES)
    lons = ",".join(str(estacao["lon"]) for estacao in ESTACOES)
    params = {
        "latitude": lats,
        "longitude": lons,
        "hourly": VARIAVEIS_HOURLY,
        "forecast_days": 2,
        "timezone": "America/Sao_Paulo",
        "cell_selection": "nearest",
    }
    if model_id != "best_match":
        params["models"] = model_id

    cliente = session or requests.Session()
    try:
        resposta = cliente.get(API_URL, params=params, timeout=TIMEOUT)
    except requests.RequestException as exc:
        raise ErroBuscaModelo(f"Não foi possível conectar ao serviço de previsão: {exc}") from exc

    if resposta.status_code != 200:
        detalhe = resposta.text[:300].replace("\n", " ")
        raise ErroBuscaModelo(f"O serviço retornou HTTP {resposta.status_code}: {detalhe}")

    try:
        payload = resposta.json()
    except ValueError as exc:
        raise ErroBuscaModelo("O serviço retornou uma resposta inválida.") from exc

    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list) or len(payload) != len(ESTACOES):
        quantidade = len(payload) if isinstance(payload, list) else 0
        raise ErroBuscaModelo(
            f"Foram recebidas {quantidade} localidades, mas eram esperadas {len(ESTACOES)}."
        )

    resultado: dict[str, Any] = {}
    hora_referencia = "—"

    for estacao, bloco in zip(ESTACOES, payload):
        hourly = bloco.get("hourly", {}) if isinstance(bloco, dict) else {}
        tempos = hourly.get("time", []) or []
        capes = hourly.get("cape", []) or []
        lis = hourly.get("lifted_index", []) or []
        cins = hourly.get("convective_inhibition", []) or []
        indice = _indice_hora_atual(tempos)

        resultado[estacao["nome"]] = {
            "tempos": tempos,
            "cape": [_como_numero(valor) for valor in capes],
            "li": [_como_numero(valor) for valor in lis],
            "cin": [_como_numero(valor) for valor in cins],
            "idx_atual": indice,
        }

        if hora_referencia == "—" and tempos:
            try:
                hora_referencia = datetime.fromisoformat(tempos[indice]).strftime("%H:%M (%d/%m)")
            except (ValueError, IndexError):
                hora_referencia = tempos[indice] if indice < len(tempos) else "—"

    resultado["_hora_referencia"] = hora_referencia
    return resultado
