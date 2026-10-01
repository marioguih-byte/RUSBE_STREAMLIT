"""Heurística de risco de raios usada no dashboard RUSBÉ."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

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


def calcular_risco(
    cape: Optional[float],
    lifted_index: Optional[float],
    cin: Optional[float],
    parametros: ParametrosRisco = PARAMETROS_PADRAO,
    extras: Optional[dict[str, Optional[float]]] = None,
) -> tuple[Optional[float], str, str]:
    """Calcula um escore de risco de raio com base em CAPE, LI e CIN.

    CAPE alto favorece a convecção profunda; Lifted Index negativo representa
    maior instabilidade; e CIN muito negativo reduz a probabilidade de disparo
    convectivo. A função retorna ``(escore, nível, cor)`` (cor da paleta padrão).
    Com ``parametros`` padrão o resultado é idêntico ao da versão original; ``extras`` só
    entra na conta se ``parametros.peso_extras`` > 0.
    """
    if cape is None:
        return None, "Sem dados", COR_SEM_DADOS

    cape = cape * parametros.fator_cape
    if lifted_index is not None:
        lifted_index = lifted_index * parametros.fator_li

    score = 0.0

    if cape < 300:
        score += 0
    elif cape < 1000:
        score += 10
    elif cape < 2500:
        score += 22
    elif cape < 3500:
        score += 34
    else:
        score += 45

    if lifted_index is None:
        pass
    elif lifted_index > 2:
        score += 0
    elif lifted_index > 0:
        score += 5
    elif lifted_index > -2:
        score += 12
    elif lifted_index > -6:
        score += 22
    elif lifted_index > -9:
        score += 30
    else:
        score += 35

    if cin is None:
        pass
    else:
        cin_abs = abs(cin)
        if cin_abs < 25:
            contribuicao = 20
        elif cin_abs < 50:
            contribuicao = 10
        elif cin_abs < 100:
            contribuicao = 0
        elif cin_abs < 200:
            contribuicao = -15
        else:
            contribuicao = -30
        score += contribuicao * parametros.peso_cin

    if parametros.peso_extras > 0:
        score += ajuste_extras(extras) * parametros.peso_extras

    score = max(0, min(100, score))
    rotulo, cor = classificar_risco(score)
    return round(score, 1), rotulo, cor
