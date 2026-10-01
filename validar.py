"""Verificações do RUSBÉ.

Sem argumentos roda só os testes offline (cálculo, séries, tendência, heurística ampliada,
regiões, histórico, alertas, relatório).

Com ``--online`` consulta a API de verdade e imprime um relatório de sanidade dos dados
(cobertura, faixas de valores, horizonte, variáveis extras, camada GOES).
Com ``--online --modelos`` repete a checagem para todos os modelos (12 requisições) e mostra
quais devolvem CAPE, Lifted Index e CIN.
"""

from __future__ import annotations

import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from analise import consolidar, horas_a_frente, series_por_unidade, tendencia
from modelos import MODELOS, TZ_BRASILIA, VARIAVEIS_HOURLY, buscar_modelo, horario_local
from risco_raio import ParametrosRisco, ajuste_extras, calcular_risco
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

    png = gerar_png(tab, "Teste", "sub")
    pdf = gerar_pdf(tab, "Teste", "sub")
    assert png[:8] == b"\x89PNG\r\n\x1a\n" and pdf[:5] == b"%PDF-"
    print("Testes offline: OK")


class _ClienteFalso:
    """Cliente HTTP de mentira: responde à consulta principal e à de variáveis extras."""

    def __init__(self, extras: str = "ok") -> None:
        self.extras = extras  # "ok" | "erro400" | "tempo_diferente"
        self.chamadas: list[str] = []

    class _Resp:
        def __init__(self, codigo: int, payload=None) -> None:
            self.status_code, self._payload, self.text = codigo, payload, "x"

        def json(self):
            return self._payload

    def get(self, url, params=None, timeout=None):
        self.chamadas.append(params["hourly"])
        n = 6
        tempos = [f"2026-08-25T{h:02d}:00" for h in range(n)]
        if params["hourly"] == VARIAVEIS_HOURLY:
            bloco = {"hourly": {"time": tempos, "cape": [100.0 * h for h in range(n)], "lifted_index": [1.0] * n,
                                "convective_inhibition": [-10.0] * n}}
        elif self.extras == "erro400":
            return self._Resp(400)
        else:
            m = n if self.extras == "ok" else n - 1
            bloco = {"hourly": {"time": tempos[:m], "precipitation": [1.0] * m, "wind_gusts_10m": [40.0] * m,
                                "freezing_level_height": [4800.0] * m, "temperature_850hPa": [18.0] * m,
                                "temperature_500hPa": [-8.0] * m}}
        return self._Resp(200, [bloco] * len(ESTACOES))


def testes_ampliados() -> None:
    # Heurística ampliada: pontos limitados, sem efeito com peso 0 ou sem dados extras.
    assert ajuste_extras(None) == 0 and ajuste_extras({}) == 0
    assert ajuste_extras({"precip": 6.0}) == 7.0 and ajuste_extras({"rajada": 55.0}) == 4.0
    assert ajuste_extras({"gradiente": 28.0}) == 4.0 and ajuste_extras({"nivel0": 3800.0}) == 2.0
    assert ajuste_extras({"nivel0": 5600.0}) == -2.0
    assert ajuste_extras({"precip": 20.0, "rajada": 90.0, "gradiente": 35.0, "nivel0": 3000.0}) == 20.0  # limite superior
    extras = {"precip": 6.0, "rajada": 55.0, "gradiente": 28.0, "nivel0": 4800.0}
    base = calcular_risco(1500, -3, -20)[0]
    assert calcular_risco(1500, -3, -20, ParametrosRisco(), extras)[0] == base  # peso 0: ignora os extras
    ampliada = calcular_risco(1500, -3, -20, ParametrosRisco(peso_extras=1.0), extras)[0]
    assert ampliada == min(100, base + 15.0), (base, ampliada)
    assert calcular_risco(1500, -3, -20, ParametrosRisco(peso_extras=1.0), None)[0] == base  # sem extras: igual
    assert calcular_risco(1500, -3, -20, ParametrosRisco(peso_extras=2.0), extras)[0] > ampliada

    # Fatores regionais (config_regioes.json é neutro) e extras dentro das séries.
    from analise import carregar_regioes, consolidar, series_por_unidade

    regioes = carregar_regioes()
    assert len(regioes) == 13 and all(v == (1.0, 1.0) for v in regioes.values())
    dados = _dados_sinteticos()
    neutro = series_por_unidade(dados, ParametrosRisco(), regioes)
    forte = series_por_unidade(dados, ParametrosRisco(), {**regioes, "RJ": (2.0, 1.0)})
    reduc = next(e["nome"] for e in ESTACOES if e["nome"].endswith("REDUC"))
    assert sum(v for v in forte[reduc]["rel"] if v is not None) > sum(v for v in neutro[reduc]["rel"] if v is not None)
    sp = next(e["nome"] for e in ESTACOES if e["uf"] == "SP")
    assert forte[sp]["rel"] == neutro[sp]["rel"]  # UF sem ajuste não muda

    # Consulta com extras: sucesso, erro 400 (não derruba o núcleo) e eixo de tempo diferente.
    ok = buscar_modelo("best_match", _ClienteFalso("ok"))
    assert ok["_extras"] is True and ok[ESTACOES[0]["nome"]]["precip"] == [1.0] * 6
    ruim = buscar_modelo("best_match", _ClienteFalso("erro400"))
    assert ruim["_extras"] is False and "400" in ruim["_erro_extras"] and ruim[ESTACOES[0]["nome"]]["cape"][5] == 500.0
    desalinhado = buscar_modelo("best_match", _ClienteFalso("tempo_diferente"))
    assert desalinhado["_extras"] is False and "precip" not in desalinhado[ESTACOES[0]["nome"]]
    assert buscar_modelo("best_match", _ClienteFalso(), extras=False)["_erro_extras"] == "desligadas"
    tab = consolidar(ok, series_por_unidade(ok, ParametrosRisco(peso_extras=1.0)), 0)
    assert tab["Precip. (mm/h)"].iloc[0] == 1.0 and abs(tab["Gradiente 850–500 (°C)"].iloc[0] - 26.0) < 1e-9

    # Histórico: grava uma vez por hora cheia, consulta, exporta e limpa.
    import historico

    with tempfile.TemporaryDirectory() as pasta:
        banco = Path(pasta) / "h.sqlite"
        agora = datetime.now(TZ_BRASILIA)
        h = _dados_sinteticos(horas=60, atual=3)
        h["_obtido_em"] = agora.isoformat()
        assert historico.registrar(h, "best_match", banco) is True
        assert historico.registrar(h, "best_match", banco) is False  # mesma hora cheia
        h2 = {**h, "_obtido_em": (agora + timedelta(hours=1)).isoformat()}
        assert historico.registrar(h2, "best_match", banco) is True
        info = historico.status(banco)
        assert info["execucoes"] == 2 and info["linhas"] == 2 * len(ESTACOES) * 49, info
        assert historico.registrar(h, "gfs_seamless", banco) is True and historico.status(banco)["modelos"] == ["best_match", "gfs_seamless"]
        # linhas de "valido" no passado distante não existem (dados sintéticos de 2026-08-25): consulta por período amplo
        saida = Path(pasta) / "x.csv"
        assert historico.exportar_csv(saida, "best_match", caminho=banco) == 2 * len(ESTACOES) * 49
        cabecalho = saida.read_text(encoding="utf-8-sig").splitlines()[0]
        assert cabecalho.startswith("modelo;execucao;unidade;valido;horas") and cabecalho.endswith("score")
        assert len(historico.evolucao_previsao(reduc, "best_match", "2026-08-26T00:00", caminho=banco)) == 2
        assert historico.limpar(0, banco) > 0 and historico.status(banco)["linhas"] == 0

    # Camadas do mapa: divisas e URL do GOES.
    import json

    estados = json.loads((Path(__file__).resolve().parent / "dados" / "brasil_estados.geojson").read_text(encoding="utf-8"))
    assert len(estados["features"]) == 27
    import app_camadas

    assert app_camadas.url_goes("GOES-East_ABI_Band13_Clean_Infrared").endswith("/{z}/{y}/{x}.png")
    print("Testes da heurística ampliada, regiões, histórico e camadas: OK")


def _cobertura(dados: dict) -> dict:
    """% de valores não nulos por variável e faixas de valores (ignora as chaves que começam com _)."""
    resumo: dict = {}
    for campo, rotulo in (("cape", "CAPE"), ("li", "LI"), ("cin", "CIN"), ("precip", "precip"), ("rajada", "rajada"),
                          ("nivel0", "nível 0°C"), ("t850", "T850"), ("t500", "T500")):
        valores = [v for nome, s in dados.items() if not nome.startswith("_") for v in s.get(campo, [])]
        if not valores:
            continue
        validos = [v for v in valores if v is not None]
        resumo[rotulo] = {
            "validos_pct": round(100 * len(validos) / len(valores), 1),
            "min": min(validos) if validos else None,
            "max": max(validos) if validos else None,
        }
    return resumo


def teste_online(todos_os_modelos: bool = False) -> int:
    """Relatório de sanidade com dados reais. Devolve o número de problemas encontrados."""
    from analise import horas_a_frente, series_por_unidade
    import requests

    problemas = 0
    dados = buscar_modelo("best_match")
    nomes = [n for n in dados if not n.startswith("_")]
    print(f"\n[best_match] {len(nomes)} unidades · referência {dados['_hora_referencia']} · obtido em {dados['_obtido_em']}")
    if len(nomes) != len(ESTACOES) or any(e["nome"] not in dados for e in ESTACOES):
        print("  PROBLEMA: nem todas as unidades vieram na resposta.")
        problemas += 1
    horizonte = horas_a_frente(dados)
    print(f"  horizonte disponível a partir de agora: +{horizonte} h" + ("" if horizonte >= 48 else "  (PROBLEMA: esperado ≥ 48 h)"))
    problemas += int(horizonte < 48)
    serie = dados[ESTACOES[0]["nome"]]
    ref = horario_local(serie["tempos"][serie["idx_atual"]])
    desvio = abs((datetime.now(TZ_BRASILIA) - ref).total_seconds()) / 3600
    print(f"  hora de referência vs. relógio: {desvio:.1f} h de diferença" + ("" if desvio <= 1.5 else "  (PROBLEMA: fuso/horário?)"))
    problemas += int(desvio > 1.5)
    for rotulo, r in _cobertura(dados).items():
        aviso = "" if r["validos_pct"] >= 50 else "  <-- poucos dados"
        print(f"  {rotulo:9s} válidos {r['validos_pct']:5.1f}%  faixa [{r['min']}, {r['max']}]{aviso}")
        problemas += int(rotulo in ("CAPE", "LI", "CIN") and r["validos_pct"] < 50)
    print(f"  variáveis extras: {'OK' if dados['_extras'] else 'INDISPONÍVEIS — ' + str(dados.get('_erro_extras'))}")
    niveis = consolidar_resumo(dados, series_por_unidade)
    print(f"  níveis agora: {niveis}")

    if todos_os_modelos:
        print("\nCobertura por modelo (CAPE / LI / CIN / extras / horas à frente):")
        for modelo_id, (nome, _, _) in MODELOS.items():
            try:
                d = buscar_modelo(modelo_id)
            except Exception as erro:  # um modelo fora do ar não deve impedir o relatório dos demais
                print(f"  {nome:28s} ERRO: {str(erro)[:80]}")
                continue
            c = _cobertura(d)
            def pct(k):
                return f"{c[k]['validos_pct']:5.1f}%" if k in c else "   — "
            print(f"  {nome:28s} {pct('CAPE')} {pct('LI')} {pct('CIN')}  extras {'sim' if d['_extras'] else 'não'}  +{horas_a_frente(d)} h")

    print("\nCamada GOES (NASA GIBS):")
    import app_camadas

    url = app_camadas.url_goes().format(z=3, y=3, x=2)
    try:
        r = requests.get(url, timeout=20)
        tipo = r.headers.get("content-type", "")
        ok = r.status_code == 200 and tipo.startswith("image/")
        print(f"  {r.status_code} {tipo} {len(r.content)} bytes" + ("" if ok else "  <-- PROBLEMA: confira o nome da camada em app_camadas.GOES_CAMADA"))
        problemas += int(not ok)
    except requests.RequestException as erro:
        print(f"  não foi possível consultar: {erro}")
        problemas += 1
    print(f"\n{'Tudo certo.' if problemas == 0 else f'{problemas} ponto(s) de atenção acima.'}")
    return problemas


def consolidar_resumo(dados: dict, series_por_unidade) -> dict:
    from analise import consolidar

    tabela = consolidar(dados, series_por_unidade(dados), 0)
    return tabela["Risco"].value_counts().to_dict()


if __name__ == "__main__":
    pd.set_option("display.width", 160)
    testes_offline()
    testes_ampliados()
    if "--online" in sys.argv:
        from modelos import ErroBuscaModelo

        try:
            sys.exit(1 if teste_online(todos_os_modelos="--modelos" in sys.argv) else 0)
        except ErroBuscaModelo as erro:
            print(f"\nNão foi possível consultar a API: {erro}")
            sys.exit(2)
