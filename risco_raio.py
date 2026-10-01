"""Heurística de risco de raios usada no dashboard RUSBÉ."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

# (limite superior do score, rótulo, cor da paleta padrão)
NIVEIS_RISCO = [
    (15, "Nenhum", "#5a6472"),
    (35, "Baixo", "#3fa34d"),
    (55, "Moderado", "#e0b400"),
    (75, "Alto", "#e0761f"),
    (101, "Severo", "#d13b3b"),
]

ROTULOS = [rotulo for _, rotulo, _ in NIVEIS_RISCO]
LIMITES = {rotulo: limite for limite, rotulo, _ in NIVEIS_RISCO}
ORDEM = {rotulo: posicao for posicao, rotulo in enumerate(ROTULOS)}  # Nenhum=0 … Severo=4
COR_SEM_DADOS = "#3a3f47"

CORES_NIVEL = {rotulo: cor for _, rotulo, cor in NIVEIS_RISCO} | {"Sem dados": COR_SEM_DADOS}
ICONES = {"Nenhum": "⚪", "Baixo": "🟢", "Moderado": "🟡", "Alto": "🟠", "Severo": "🔴", "Sem dados": "⚫"}


@dataclass(frozen=True)
class ParametrosRisco:
    """Ajustes de sensibilidade da heurística (1,0 = comportamento original).

    - ``fator_cape``: multiplica o CAPE antes de aplicar os limiares (>1 = mais sensível).
    - ``fator_li``: multiplica o Lifted Index (>1 amplifica instabilidade e estabilidade).
    - ``peso_cin``: multiplica a contribuição do CIN ao score (0 = ignora o CIN).
    - ``peso_extras``: peso da heurística ampliada (0 = desligada; 1 = ajustes na escala padrão).
    """

    fator_cape: float = 1.0
    fator_li: float = 1.0
    peso_cin: float = 1.0
    peso_extras: float = 0.0


PARAMETROS_PADRAO = ParametrosRisco()


def classificar_risco(score: float) -> tuple[str, str]:
    """Converte um escore de 0 a 100 em rótulo e cor hexadecimal (paleta padrão)."""
    for limite, rotulo, cor in NIVEIS_RISCO:
        if score < limite:
            return rotulo, cor
    return "Severo", "#d13b3b"


# ----------------------------------------------------------------------------
# Heurística ampliada: ajustes somados ao score básico (CAPE + LI + CIN).
# Os pontos são limitados e pequenos perto do score básico, e ainda NÃO foram
# calibrados com observações: use o peso para ajustá-los e valide com o histórico.
# ----------------------------------------------------------------------------
LIMITES_PRECIPITACAO = [(10.0, 10.0), (5.0, 7.0), (2.0, 4.0), (0.5, 1.0)]  # mm/h → pontos
LIMITES_RAJADA = [(70.0, 6.0), (50.0, 4.0), (35.0, 2.0)]  # km/h → pontos
LIMITES_GRADIENTE = [(29.0, 6.0), (27.0, 4.0), (25.0, 2.0)]  # T850 − T500 (°C) → pontos
NIVEL_0C_BAIXO, NIVEL_0C_ALTO = 4200.0, 5300.0  # m: abaixo = +2 (mais camada mista), acima = −2
AJUSTE_MAXIMO, AJUSTE_MINIMO = 20.0, -4.0


def _pontos(valor: Optional[float], limites: list[tuple[float, float]]) -> float:
    if valor is None:
        return 0.0
    for limite, pontos in limites:
        if valor >= limite:
            return pontos
    return 0.0


def ajuste_extras(extras: Optional[dict[str, Optional[float]]]) -> float:
    """Pontos adicionais (antes do peso) a partir de precipitação, rajada, gradiente 850–500 hPa e nível de 0 °C.

    Variáveis ausentes (``None``) simplesmente não contribuem.
    """
    if not extras:
        return 0.0
    pontos = _pontos(extras.get("precip"), LIMITES_PRECIPITACAO)
    pontos += _pontos(extras.get("rajada"), LIMITES_RAJADA)
    pontos += _pontos(extras.get("gradiente"), LIMITES_GRADIENTE)
    nivel0 = extras.get("nivel0")
    if nivel0 is not None:
        pontos += 2.0 if nivel0 < NIVEL_0C_BAIXO else (-2.0 if nivel0 > NIVEL_0C_ALTO else 0.0)
    return max(AJUSTE_MINIMO, min(AJUSTE_MAXIMO, pontos))


# Sem energia disponível (CAPE efetivo abaixo disto) não há tempestade a "disparar": o Lifted Index
# e a baixa inibição (CIN) deixam de somar pontos altos, para que ar estável não vire "Moderado".
ENERGIA_MINIMA_CAPE = 300.0  # J/kg
PONTOS_MAX_LI_SEM_ENERGIA = 5.0


def _pontos_cape(cape: float) -> float:
    if cape < 300:
        return 0.0
    if cape < 1000:
        return 10.0
    if cape < 2500:
        return 22.0
    if cape < 3500:
        return 34.0
    return 45.0


def _pontos_li(lifted_index: float) -> float:
    if lifted_index > 2:
        return 0.0
    if lifted_index > 0:
        return 5.0
    if lifted_index > -2:
        return 12.0
    if lifted_index > -6:
        return 22.0
    if lifted_index > -9:
        return 30.0
    return 35.0


def _pontos_cin(cin: float) -> float:
    cin_abs = abs(cin)
    if cin_abs < 25:
        return 20.0
    if cin_abs < 50:
        return 10.0
    if cin_abs < 100:
        return 0.0
    if cin_abs < 200:
        return -15.0
    return -30.0


def detalhar_risco(
    cape: Optional[float],
    lifted_index: Optional[float],
    cin: Optional[float],
    parametros: ParametrosRisco = PARAMETROS_PADRAO,
    extras: Optional[dict[str, Optional[float]]] = None,
    multiplicador_gate: Optional[float] = None,
) -> dict[str, Any]:
    """Score e a contribuição de cada componente (para explicar o resultado ao usuário).

    ``multiplicador_gate`` (ex.: 0,5) multiplica o score quando uma condição de disparo exigida
    (como chuva prevista) não é atendida; ``None`` = sem gate.
    """
    vazio: dict[str, Any] = {"score": None, "cape_ef": None, "li_ef": None, "pts_cape": 0.0, "pts_li": 0.0, "pts_cin": 0.0,
                              "pts_extras": 0.0, "sem_energia": False, "subtotal": None, "multiplicador": 1.0}
    if cape is None:
        return vazio

    cape_ef = cape * parametros.fator_cape
    li_ef = lifted_index * parametros.fator_li if lifted_index is not None else None
    pts_cape = _pontos_cape(cape_ef)
    pts_li = _pontos_li(li_ef) if li_ef is not None else 0.0
    pts_cin = _pontos_cin(cin) * parametros.peso_cin if cin is not None else 0.0
    sem_energia = cape_ef < ENERGIA_MINIMA_CAPE
    if sem_energia:
        pts_li = min(pts_li, PONTOS_MAX_LI_SEM_ENERGIA)
        pts_cin = min(pts_cin, 0.0)
    pts_extras = ajuste_extras(extras) * parametros.peso_extras if parametros.peso_extras > 0 else 0.0

    subtotal = pts_cape + pts_li + pts_cin + pts_extras
    multiplicador = 1.0 if multiplicador_gate is None else multiplicador_gate
    score = max(0.0, min(100.0, subtotal * multiplicador))
    return {"score": round(score, 1), "cape_ef": cape_ef, "li_ef": li_ef, "pts_cape": pts_cape, "pts_li": pts_li,
            "pts_cin": pts_cin, "pts_extras": pts_extras, "sem_energia": sem_energia, "subtotal": subtotal,
            "multiplicador": multiplicador}


def calcular_risco(
    cape: Optional[float],
    lifted_index: Optional[float],
    cin: Optional[float],
    parametros: ParametrosRisco = PARAMETROS_PADRAO,
    extras: Optional[dict[str, Optional[float]]] = None,
    multiplicador_gate: Optional[float] = None,
) -> tuple[Optional[float], str, str]:
    """Calcula um escore de risco de raio com base em CAPE, LI e CIN.

    CAPE alto favorece a convecção profunda; Lifted Index negativo representa maior instabilidade;
    e CIN alto reduz a probabilidade de disparo convectivo. Sem energia (CAPE < 300 J/kg), o LI e a
    baixa inibição não somam pontos altos. ``extras`` só entra na conta se ``parametros.peso_extras`` > 0.
    A função retorna ``(escore, nível, cor)`` (cor da paleta padrão).
    """
    detalhe = detalhar_risco(cape, lifted_index, cin, parametros, extras, multiplicador_gate)
    if detalhe["score"] is None:
        return None, "Sem dados", COR_SEM_DADOS
    rotulo, cor = classificar_risco(detalhe["score"])
    return detalhe["score"], rotulo, cor
