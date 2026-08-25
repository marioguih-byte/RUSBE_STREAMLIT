"""Verificação funcional mínima da aplicação RUSBÉ."""

from modelos import buscar_modelo
from risco_raio import calcular_risco
from unidades import ESTACOES


def main() -> None:
    score, nivel, _ = calcular_risco(3000, -7, -20)
    assert score == 84.0 and nivel == "Severo", (score, nivel)

    dados = buscar_modelo("best_match")
    assert len([nome for nome in dados if not nome.startswith("_")]) == len(ESTACOES)
    for estacao in ESTACOES:
        assert estacao["nome"] in dados
    print(f"Consulta funcional validada para {len(ESTACOES)} estações. Referência: {dados['_hora_referencia']}")


if __name__ == "__main__":
    main()
