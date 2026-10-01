"""Unidades operacionais monitoradas pelo dashboard RUSBÉ."""

from __future__ import annotations

import unicodedata


def _normalizar(texto: str) -> str:
    """Remove acentos para obter uma ordenação alfabética estável."""
    nfkd = unicodedata.normalize("NFKD", texto)
    sem_acento = "".join(c for c in nfkd if not unicodedata.combining(c))
    return sem_acento.lower()


_ESTACOES_BRUTO = [
    {"nome": "UTE Termocamaçari - UTE TCA", "lat": -12.66686802, "lon": -38.31468743},
    {"nome": "UTE Termobahia - UTE TBA", "lat": -12.70323522, "lon": -38.5649039},
    {"nome": "UTE Termoceará - UTE TCE", "lat": -3.692456132, "lon": -38.87060505},
    {"nome": "UTE Vale do Açu - UTE VLA", "lat": -5.381685305, "lon": -36.81975448},
    {"nome": "Refinaria Abreu e Lima - RNEST", "lat": -8.379660515, "lon": -35.01019801},
    {"nome": "Unidade de Tratamento de Gás Sul Capixaba - UTGSUL", "lat": -20.79446397, "lon": -40.62091015},
    {"nome": "Unidade de Tratamento de Gás de Cacimbas - UTGC", "lat": -19.46309747, "lon": -39.76060306},
    {"nome": "Refinaria Duque de Caxias - REDUC", "lat": -22.7151, "lon": -43.28400758},
    {"nome": "UTE Termorio - UTE TRI", "lat": -22.71488207, "lon": -43.25434814},
    {"nome": "BOAVENTURA, Itaboraí-RJ", "lat": -22.66071368, "lon": -42.85362881},
    {"nome": "Unidade de Tratamento de Gás de Cabiúnas - UTGCAB", "lat": -22.28532675, "lon": -41.71790456},
    {"nome": "UTE Termomacaé - UTE TMA", "lat": -22.30616415, "lon": -41.87670153},
    {"nome": "UTE Seropédica/Baixada Fluminense - UTE SRP/BF", "lat": -22.72329157, "lon": -43.64771896},
    {"nome": "Refinaria Gabriel Passos - REGAP", "lat": -19.96428142, "lon": -44.09513766},
    {"nome": "UTE Ibirité - UTE IBT", "lat": -19.98857868, "lon": -44.09820657},
    {"nome": "UTE Juiz de Fora - UTE JF", "lat": -21.69061921, "lon": -43.45671968},
    {"nome": "UTE Três Lagoas - UTE TLG", "lat": -20.7455, "lon": -51.66459},
    {"nome": "Unidade de Tratamento de Gás de Caraguatatuba - UTGCA", "lat": -23.65419134, "lon": -45.50120878},
    {"nome": "Refinaria Presidente Bernardes - RPBC", "lat": -23.87332565, "lon": -46.42757169},
    {"nome": "UTE Cubatão - UTE CBT", "lat": -23.87573454, "lon": -46.43138719},
    {"nome": "Refinaria Henrique Lage - REVAP", "lat": -23.18479615, "lon": -45.81580644},
    {"nome": "Refinaria de Capuava - RECAP", "lat": -23.65668068, "lon": -46.48088344},
    {"nome": "Refinaria de Paulínia - REPLAN", "lat": -22.72958869, "lon": -47.14771246},
    {"nome": "UTE Nova Piratininga - UTE NPI", "lat": -23.69941367, "lon": -46.67388058},
    {"nome": "Refinaria Presidente Getúlio Vargas - REPAR", "lat": -25.56613966, "lon": -49.36942343},
    {"nome": "Refinaria Alberto Pasqualini - REFAP", "lat": -29.86990149, "lon": -51.17819535},
    {"nome": "UTE Canoas - UTE CAN", "lat": -29.87507086, "lon": -51.14544477},
    {"nome": "Armazém Rio de Janeiro", "lat": -22.81097281, "lon": -43.28187584},
    {"nome": "CILEP - CENPES", "lat": -22.85419803, "lon": -43.23383006},
    {"nome": "Porto Baia de Guanabara", "lat": -22.87894224, "lon": -43.20933012},
    {"nome": "ARM Macaé - Armazém Macaé", "lat": -22.4153173, "lon": -41.86135335},
    {"nome": "Porto de Imbetiba - Macaé", "lat": -22.38682534, "lon": -41.76874101},
    {"nome": "Porto Açu", "lat": -21.86473705, "lon": -41.01644432},
    {"nome": "Porto Aratu", "lat": -12.78013207, "lon": -38.49676426},
    {"nome": "Porto TMIB", "lat": -10.82412899, "lon": -36.94630067},
    {"nome": "Porto Belém", "lat": -1.439900918, "lon": -48.49492002},
    {"nome": "Porto Valença", "lat": -13.36936887, "lon": -39.07125244},
    {"nome": "Porto Guamaré", "lat": -5.10669199, "lon": -36.31959173},
    {"nome": "Porto Mucuripe", "lat": -3.713117425, "lon": -38.47403692},
    {"nome": "Porto Paracuru", "lat": -3.401146142, "lon": -39.01089596},
]

# UF de cada unidade (usada nos filtros e nos relatórios).
_UF_POR_UNIDADE = {
    "UTE Termocamaçari - UTE TCA": "BA",
    "UTE Termobahia - UTE TBA": "BA",
    "UTE Termoceará - UTE TCE": "CE",
    "UTE Vale do Açu - UTE VLA": "RN",
    "Refinaria Abreu e Lima - RNEST": "PE",
    "Unidade de Tratamento de Gás Sul Capixaba - UTGSUL": "ES",
    "Unidade de Tratamento de Gás de Cacimbas - UTGC": "ES",
    "Refinaria Duque de Caxias - REDUC": "RJ",
    "UTE Termorio - UTE TRI": "RJ",
    "BOAVENTURA, Itaboraí-RJ": "RJ",
    "Unidade de Tratamento de Gás de Cabiúnas - UTGCAB": "RJ",
    "UTE Termomacaé - UTE TMA": "RJ",
    "UTE Seropédica/Baixada Fluminense - UTE SRP/BF": "RJ",
    "Refinaria Gabriel Passos - REGAP": "MG",
    "UTE Ibirité - UTE IBT": "MG",
    "UTE Juiz de Fora - UTE JF": "MG",
    "UTE Três Lagoas - UTE TLG": "MS",
    "Unidade de Tratamento de Gás de Caraguatatuba - UTGCA": "SP",
    "Refinaria Presidente Bernardes - RPBC": "SP",
    "UTE Cubatão - UTE CBT": "SP",
    "Refinaria Henrique Lage - REVAP": "SP",
    "Refinaria de Capuava - RECAP": "SP",
    "Refinaria de Paulínia - REPLAN": "SP",
    "UTE Nova Piratininga - UTE NPI": "SP",
    "Refinaria Presidente Getúlio Vargas - REPAR": "PR",
    "Refinaria Alberto Pasqualini - REFAP": "RS",
    "UTE Canoas - UTE CAN": "RS",
    "Armazém Rio de Janeiro": "RJ",
    "CILEP - CENPES": "RJ",
    "Porto Baia de Guanabara": "RJ",
    "ARM Macaé - Armazém Macaé": "RJ",
    "Porto de Imbetiba - Macaé": "RJ",
    "Porto Açu": "RJ",
    "Porto Aratu": "BA",
    "Porto TMIB": "SE",
    "Porto Belém": "PA",
    "Porto Valença": "BA",
    "Porto Guamaré": "RN",
    "Porto Mucuripe": "CE",
    "Porto Paracuru": "CE",
}

ESTACOES = sorted(
    ({**estacao, "uf": _UF_POR_UNIDADE[estacao["nome"]]} for estacao in _ESTACOES_BRUTO),
    key=lambda estacao: _normalizar(estacao["nome"]),
)
UFS = sorted({estacao["uf"] for estacao in ESTACOES})


def sigla(nome: str) -> str:
    """Sigla curta da unidade (trecho após o último ' - ', ou o próprio nome)."""
    return nome.rsplit(" - ", 1)[-1] if " - " in nome else nome
