"""Verificações do RUSBÉ.

Sem argumentos roda só os testes offline (cálculo, séries, consenso, alertas, relatório).
Com ``--online`` consulta a API de previsão para as 40 unidades.
"""

from __future__ import annotations

import io
import sys

import pandas as pd

from analise import (
    consolidar,
    contar_raios,
    filtrar_janela,
    horas_a_frente,
    ler_raios,
    series_por_unidade,
    tendencia,
)
from modelos import TZ_BRASILIA, buscar_modelo, horario_local
from risco_raio import ParametrosRisco, calcular_risco
from unidades import ESTACOES


def _dados_sinteticos(horas: int = 72, atual: int = 3) -> dict:
    """Série sintética: instabilidade crescente ao longo do dia, igual para todas as unidades."""
    tempos = [f"2026-08-25T{h % 24:02d}:00" if h < 24 else f"2026-08-{25 + h // 24}T{h % 24:02d}:00" for h in range(horas)]
    capes = [max(0, 4200 * (1 - abs(h - 30) / 30)) for h in range(horas)]
    lis = [4 - h * 0.25 if h < 30 else -3.5 + (h - 30) * 0.25 for h in range(horas)]
    cins = [-20.0] * horas
    serie = {"tempos": tempos, "cape": capes, "li": lis, "cin": cins, "idx_atual": atual}
    dados = {e["nome"]: serie for e in ESTACOES}
    dados["_hora_referencia"] = "03:00 (25/08)"
    return dados


def testes_offline() -> None:
    # Heurística original (resultado de referência) e parâmetros neutros.
    score, nivel, _ = calcular_risco(3000, -7, -20)
    assert score == 84.0 and nivel == "Severo", (score, nivel)
    assert calcular_risco(3000, -7, -20, ParametrosRisco())[0] == 84.0
    # Peso do CIN = 0 ignora a contribuição do CIN (CIN forte deixa de reduzir o score).
    assert calcular_risco(3000, -7, -250, ParametrosRisco(peso_cin=0))[0] == 64.0
    assert calcular_risco(3000, -7, -250)[0] == 34.0
    # Sensibilidade ao CAPE aumenta o score.
    assert calcular_risco(900, -7, -20, ParametrosRisco(fator_cape=2.0))[0] > calcular_risco(900, -7, -20)[0]
    assert calcular_risco(None, -7, -20)[1] == "Sem dados"

    horario = horario_local("2026-08-25T20:00")
    assert horario.tzinfo == TZ_BRASILIA
    assert horario.strftime("%H:%M (%d/%m)") == "20:00 (25/08)"

    # Séries, tendência e consolidação.
    dados = _dados_sinteticos()
    assert horas_a_frente(dados) == 68
    series = series_por_unidade(dados)
    assert len(series) == len(ESTACOES)
    tabela = consolidar(dados, series, 0)
    assert len(tabela) == len(ESTACOES) and set(tabela["UF"]) >= {"RJ", "SP", "BA"}
    assert tendencia([10, 30, 50, 60, 20, 10, 5], 0)["seta"] == "▲"
    assert tendencia([60, 40, 30, 20, 10, 5, 0], 0)["seta"] == "▼"
    assert tendencia([30, 31, 32, 31, 30, 29, 30], 0)["seta"] == "▬"
    assert tendencia([None, 1], 0)["seta"] == ""
    alto = consolidar(dados, series, 27)  # perto do pico sintético
    assert alto["Score"].max() > tabela["Score"].max()

    # Consenso: média de modelos com séries diferentes.
    outro = _dados_sinteticos()
    for nome in list(outro):
        if not nome.startswith("_"):
            outro[nome] = {**outro[nome], "cape": [c * 0.5 for c in outro[nome]["cape"]]}
    cons = series_por_unidade(dados, ParametrosRisco(), {"a": dados, "b": outro})
    unidade = ESTACOES[0]["nome"]
    meio = cons[unidade]["rel"][27]
    pa, pb = cons[unidade]["por_modelo"]["a"][27], cons[unidade]["por_modelo"]["b"][27]
    assert abs(meio - (pa + pb) / 2) <= 0.06, (meio, pa, pb)
    tab_cons = consolidar(dados, cons, 27)
    assert (tab_cons["Modelos"] == 2).all() and (tab_cons["Score mín."] <= tab_cons["Score máx."]).all()

    # Raios observados: contagem por raio em torno da unidade.
    reduc = next(e for e in ESTACOES if e["nome"].endswith("REDUC"))
    csv = "Latitude,Longitude,Data\n" + "\n".join(
        [f"{reduc['lat'] + d},{reduc['lon']},2026-08-25T0{i}:00:00Z" for i, d in enumerate([0.0, 0.05, 0.1])]
        + ["-3.7,-38.4,2026-08-25T09:00:00Z"]
    )
    raios = ler_raios(io.StringIO(csv))
    assert len(raios) == 4 and "tempo" in raios
    contagem = contar_raios(tabela, raios, 25)
    assert int(contagem[tabela["Unidade"] == reduc["nome"]].iloc[0]) == 3
    assert len(filtrar_janela(raios, 2)) == 1  # só o último, relativo ao raio mais recente

    # Alertas: alerta uma vez, não repete, rearma depois de cair.
    import alertas

    tab = consolidar(dados, series, 27)
    primeiro, estado = alertas.avaliar(tab, {}, "Alto", 0, series)
    segundo, estado2 = alertas.avaliar(tab, estado, "Alto", 0, series)
    assert primeiro and not segundo
    tab_baixa = tab.assign(Risco="Baixo")
    _, estado3 = alertas.avaliar(tab_baixa, estado2, "Alto", 0, series)
    de_novo, _ = alertas.avaliar(tab, estado3, "Alto", 0, series)
    assert len(de_novo) == len(primeiro)

    # Relatório: PNG e PDF válidos.
    from relatorio import gerar_pdf, gerar_png

    png = gerar_png(tab, "Teste", "sub", "daltonismo")
    pdf = gerar_pdf(tab, "Teste", "sub", "padrao")
    assert png[:8] == b"\x89PNG\r\n\x1a\n" and pdf[:5] == b"%PDF-"
    print("Testes offline: OK")


def teste_online() -> None:
    dados = buscar_modelo("best_match")
    assert len([nome for nome in dados if not nome.startswith("_")]) == len(ESTACOES)
    for estacao in ESTACOES:
        assert estacao["nome"] in dados
    print(f"Consulta funcional validada para {len(ESTACOES)} estações. Referência: {dados['_hora_referencia']}")


if __name__ == "__main__":
    pd.set_option("display.width", 160)
    testes_offline()
    if "--online" in sys.argv:
        teste_online()
