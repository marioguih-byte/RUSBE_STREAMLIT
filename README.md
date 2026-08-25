# RUSBÉ — Dashboard de Risco de Raios

Esta é a versão em **Streamlit** do notebook `RUSBÉ—RastreamentoeUtilizaçãodeSistemaBaseadoemEletricidade(atmosférica).ipynb`. A interface consulta previsões horárias de CAPE, Lifted Index e CIN para 40 unidades, calcula um escore heurístico de risco de raios e apresenta os resultados em mapa, tabela e detalhe por estação.

> O escore meteorológico é um recurso de acompanhamento. Ele não substitui alertas oficiais, decisões operacionais de segurança ou sistemas dedicados de detecção de descargas atmosféricas.

## Funcionalidades

| Área | Implementação |
|---|---|
| Modelos meteorológicos | Seleção entre Best Match e os modelos globais disponíveis no notebook. |
| Atualização de dados | Consulta à API de previsão com cache de 10 minutos e botão de atualização manual. |
| Mapa | Marcadores dimensionados e coloridos conforme o escore de risco por unidade. |
| Visão operacional | Indicadores por nível de risco e lista filtrável das unidades. |
| Detalhamento | Métricas atuais e série de previsão de 24 horas para a unidade selecionada. |

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

## Publicação no Streamlit Community Cloud

Envie esta pasta para um repositório GitHub. Na criação do aplicativo no [Streamlit Community Cloud](https://share.streamlit.io/), indique o repositório, a branch desejada e o arquivo principal `app.py`. A plataforma instalará automaticamente as dependências listadas em `requirements.txt`.

## Fonte de dados

As previsões são consultadas da API [Open-Meteo](https://open-meteo.com/), utilizando as variáveis horárias `cape`, `lifted_index` e `convective_inhibition`.
