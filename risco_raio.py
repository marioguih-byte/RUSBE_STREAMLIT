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

# Paletas por nível. A paleta "daltonismo" varia também a luminosidade (claro → escuro),
# e não apenas o matiz, para continuar legível com deuteranopia/protanopia.
PALETAS = {
    "padrao": {
        "Nenhum": "#5a6472",
        "Baixo": "#3fa34d",
        "Moderado": "#e0b400",
        "Alto": "#e0761f",
        "Severo": "#d13b3b",
        "Sem dados": COR_SEM_DADOS,
    },
    "daltonismo": {
        "Nenhum": "#9aa5b1",
        "Baixo": "#56b4e9",
        "Moderado": "#f0e442",
        "Alto": "#e69f00",
        "Severo": "#8b0000",
        "Sem dados": COR_SEM_DADOS,
    },
}
ICONES = {
    "padrao": {"Nenhum": "⚪", "Baixo": "🟢", "Moderado": "🟡", "Alto": "🟠", "Severo": "🔴", "Sem dados": "⚫"},
    "daltonismo": {"Nenhum": "⚪", "Baixo": "🔵", "Moderado": "🟡", "Alto": "🟠", "Severo": "🟥", "Sem dados": "⚫"},
}


@dataclass(frozen=True)
class ParametrosRisco:
    """Ajustes de sensibilidade da heurística (1,0 = comportamento original).

    - ``fator_cape``: multiplica o CAPE antes de aplicar os limiares (>1 = mais sensível).
    - ``fator_li``: multiplica o Lifted Index (>1 amplifica instabilidade e estabilidade).
    - ``peso_cin``: multiplica a contribuição do CIN ao score (0 = ignora o CIN).
    """

    fator_cape: float = 1.0
    fator_li: float = 1.0
    peso_cin: float = 1.0


PARAMETROS_PADRAO = ParametrosRisco()


def cores_da_paleta(paleta: str = "padrao") -> dict[str, str]:
    return PALETAS.get(paleta, PALETAS["padrao"])


def classificar_risco(score: float) -> tuple[str, str]:
    """Converte um escore de 0 a 100 em rótulo e cor hexadecimal (paleta padrão)."""
    for limite, rotulo, cor in NIVEIS_RISCO:
        if score < limite:
            return rotulo, cor
    return "Severo", "#d13b3b"


def calcular_risco(
    cape: Optional[float],
    lifted_index: Optional[float],
    cin: Optional[float],
    parametros: ParametrosRisco = PARAMETROS_PADRAO,
) -> tuple[Optional[float], str, str]:
    """Calcula um escore de risco de raio com base em CAPE, LI e CIN.

    CAPE alto favorece a convecção profunda; Lifted Index negativo representa
    maior instabilidade; e CIN muito negativo reduz a probabilidade de disparo
    convectivo. A função retorna ``(escore, nível, cor)`` (cor da paleta padrão).
    Com ``parametros`` padrão o resultado é idêntico ao da versão original.
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

    score = max(0, min(100, score))
    rotulo, cor = classificar_risco(score)
    return round(score, 1), rotulo, cor
