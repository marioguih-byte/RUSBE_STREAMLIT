# RUSBÉ — Dashboard de Risco de Raios

Esta é a versão em **Streamlit** do notebook `RUSBÉ—RastreamentoeUtilizaçãodeSistemaBaseadoemEletricidade(atmosférica).ipynb`. A interface consulta previsões horárias de CAPE, Lifted Index e CIN para 40 unidades, calcula um escore heurístico de risco de raios e apresenta os resultados em mapa, tabela e detalhe por estação.

> O escore meteorológico é um recurso de acompanhamento. Ele não substitui alertas oficiais, decisões operacionais de segurança ou sistemas dedicados de detecção de descargas atmosféricas.

## Funcionalidades

| Área | Implementação |
|---|---|
| Modelos meteorológicos | Seleção entre Best Match e os modelos globais disponíveis no notebook. |
| Atualização de dados | Consulta à API de previsão com cache de 10 minutos e botão de atualização manual. |
| Mapa | Marcadores dimensionados e coloridos conforme o escore de risco por unidade, com leitura breve no próprio mapa. |
| Visão operacional | Barra lateral com modelo, estilo do mapa, centralização, pesquisa, legenda e lista clicável das 40 unidades. |
| Detalhamento | Janela escura equivalente ao pop-up do notebook, com 24 leituras horárias de CAPE, Lifted Index, CIN, score e risco. |

## Estrutura do projeto

| Arquivo | Finalidade |
|---|---|
| `app.py` | Ponto de entrada do dashboard Streamlit. |
| `unidades.py` | Lista completa das 40 unidades e respectivas coordenadas. |
| `modelos.py` | Consulta dos modelos e normalização da resposta meteorológica. |
| `risco_raio.py` | Heurística de classificação de risco. |
| `requirements.txt` | Dependências de execução. |
| `validar.py` | Verificação funcional mínima da consulta e do cálculo. |

## Como executar

Crie e ative um ambiente virtual opcionalmente. Em seguida, instale as dependências e inicie o Streamlit no diretório do projeto:

```bash
pip install -r requirements.txt
streamlit run app.py
```

A aplicação estará disponível normalmente em `http://localhost:8501`.

## Interação com as unidades

Use a pesquisa ou clique em qualquer unidade da barra lateral. O mapa aproxima a localização e abre o detalhamento. A primeira linha da tabela representa a hora de referência atual; as demais linhas mostram as 23 horas seguintes, com cores coerentes com o nível de risco. Os marcadores do mapa também mantêm um pop-up resumido e acionam o mesmo fluxo de detalhe quando selecionados.

## Publicação no Streamlit Community Cloud

Envie esta pasta para um repositório GitHub. Na criação do aplicativo no [Streamlit Community Cloud](https://share.streamlit.io/), indique o repositório, a branch desejada e o arquivo principal `app.py`. A plataforma instalará automaticamente as dependências listadas em `requirements.txt`.

## Fonte de dados

As previsões são consultadas da API [Open-Meteo](https://open-meteo.com/), utilizando as variáveis horárias `cape`, `lifted_index` e `convective_inhibition`.
