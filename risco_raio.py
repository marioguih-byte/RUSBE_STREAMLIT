"""Heurística de risco de raios usada no dashboard RUSBÉ."""

from __future__ import annotations

from typing import Optional

NIVEIS_RISCO = [
    (15, "Nenhum", "#5a6472"),
    (35, "Baixo", "#3fa34d"),
    (55, "Moderado", "#e0b400"),
    (75, "Alto", "#e0761f"),
    (101, "Severo", "#d13b3b"),
]


def classificar_risco(score: float) -> tuple[str, str]:
    """Converte um escore de 0 a 100 em rótulo e cor hexadecimal."""
    for limite, rotulo, cor in NIVEIS_RISCO:
        if score < limite:
            return rotulo, cor
    return "Severo", "#d13b3b"


def calcular_risco(
    cape: Optional[float],
    lifted_index: Optional[float],
    cin: Optional[float],
) -> tuple[Optional[float], str, str]:
    """Calcula um escore de risco de raio com base em CAPE, LI e CIN.

    CAPE alto favorece a convecção profunda; Lifted Index negativo representa
    maior instabilidade; e CIN muito negativo reduz a probabilidade de disparo
    convectivo. A função retorna ``(escore, nível, cor)``.
    """
    if cape is None:
        return None, "Sem dados", "#3a3f47"

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
            score += 20
        elif cin_abs < 50:
            score += 10
        elif cin_abs < 100:
            score += 0
        elif cin_abs < 200:
            score -= 15
        else:
            score -= 30

    score = max(0, min(100, score))
    rotulo, cor = classificar_risco(score)
    return round(score, 1), rotulo, cor
