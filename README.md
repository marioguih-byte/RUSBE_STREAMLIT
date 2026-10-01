# RUSBÉ — Dashboard de Risco de Raios

Versão em **Streamlit** do notebook `RUSBÉ—RastreamentoeUtilizaçãodeSistemaBaseadoemEletricidade(atmosférica).ipynb`. A interface consulta previsões horárias de CAPE, Lifted Index e CIN para 40 unidades, calcula um escore heurístico de risco de raios (0–100) e mostra o resultado em mapa, tabela, gráficos e alertas.

> O escore é um recurso de acompanhamento. Não substitui alertas oficiais, decisões operacionais de segurança ou sistemas dedicados de detecção de descargas atmosféricas.

## Funcionalidades

| Área | O que faz |
|---|---|
| **Mapa** | OpenStreetMap (padrão) ou Satélite, travado no Brasil (contorno + véu no entorno), botão ⌂ para recentralizar. Bolinhas de tamanho fixo (inclusive durante o zoom) com o score escrito dentro; a de maior risco fica por cima. A posição e o zoom são preservados ao fechar o painel. |
| **Hora da previsão** | Controle deslizante de +0 h a +48 h: o mapa, os cartões e a tabela passam a mostrar a hora escolhida. |
| **Tendência** | Seta ▲ ▼ ▬ por unidade (variação do score nas próximas 6 h), pico das próximas 24 h e horário do pico. A lista lateral pode ser ordenada por *Nome*, *Maior risco* ou *Vai piorar*. |
| **Detalhe da unidade** | Cartões (risco, CAPE, LI, CIN, tendência, consenso, raios), gráfico de 48 h do score sobre as faixas de risco, gráficos de CAPE/LI/CIN e tabela horária. |
| **Filtros** | Por nível de risco (botões com contagem), por UF e por nome. |
| **Consenso entre modelos** | Média do score calculado em 2 a 5 modelos (padrão: ECMWF IFS, GFS, ICON), com faixa mín.–máx. e uma linha por modelo no gráfico. |
| **Calibração** | Sensibilidade ao CAPE, sensibilidade ao Lifted Index e peso do CIN (1,0 = regra original). |
| **Raios observados** | Carregue um CSV (`lat`, `lon` e, opcionalmente, `tempo`; por exemplo exportado do GLM/GOES) para ver os raios no mapa e a contagem em torno de cada unidade (raio de 5 a 100 km). |
| **Exportação** | Tabela atual e séries horárias de 48 h em CSV (abre no Excel em português); mapa estático em PNG e relatório em PDF (mapa + ranking). |
| **Acessibilidade** | Paleta para daltonismo, score dentro da bolinha, altura do mapa ajustável, barra lateral recolhida em telas pequenas. |
| **Robustez** | 3 tentativas com espera crescente na API; se ela falhar, usa o último dado válido e avisa quantos minutos ele tem. Indicador "Dados · há N min" no cabeçalho. |
| **Alertas** | `alertas.py` envia e-mail e/ou webhook (Teams, Slack, Discord, gateway de WhatsApp) quando uma unidade atinge, ou deve atingir em poucas horas, o nível configurado. |

## Estrutura

| Arquivo | Finalidade |
|---|---|
| `app.py` | Interface Streamlit. |
| `analise.py` | Séries de score, tendência, consenso e contagem de raios (sem dependência do Streamlit). |
| `risco_raio.py` | Heurística de risco, parâmetros de calibração e paletas. |
| `modelos.py` | Consulta dos modelos (com tentativas) e normalização da resposta. |
| `unidades.py` | As 40 unidades, coordenadas e UF. |
| `relatorio.py` | Geração do mapa PNG e do relatório PDF. |
| `alertas.py` | Verificação e envio de alertas (linha de comando). |
| `dados/` | Contorno e máscara simplificados do Brasil (Natural Earth, domínio público). |
| `.streamlit/config.toml` | Tema escuro fixo. |
| `.github/workflows/alertas.yml` | Agendamento dos alertas a cada 30 min. |
| `validar.py` | Testes (offline por padrão; `--online` consulta a API). |

## Como executar

```bash
pip install -r requirements.txt
streamlit run app.py
```

A aplicação abre normalmente em `http://localhost:8501`. Para validar:

```bash
python validar.py            # testes offline
python validar.py --online   # inclui a consulta real à API
```

## Alertas

```bash
python alertas.py --dry-run                                  # só imprime
python alertas.py --nivel Alto --antecedencia 3              # avisa em Alto+ ou previsto em até 3 h
python alertas.py --consenso ecmwf_ifs025 gfs_seamless icon_seamless
```

Cada unidade é avisada **uma vez**; ela só é avisada de novo depois de voltar a ficar abaixo do nível. O estado fica em `estado_alertas.json`. Os canais são configurados por variáveis de ambiente (nenhuma é obrigatória, mas sem elas o script apenas imprime):

| Variável | Uso |
|---|---|
| `ALERTA_WEBHOOK_URL` | Webhook (recebe JSON com `text` e `content`). |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS` | Servidor de e-mail. |
| `ALERTA_EMAIL_DE`, `ALERTA_EMAIL_PARA` | Remetente e destinatários (separados por vírgula). |

Para rodar a cada 30 minutos sem servidor próprio, use o workflow `.github/workflows/alertas.yml` (cadastre as variáveis como *secrets* do repositório). O GitHub pode atrasar execuções agendadas em alguns minutos.

## Formato do CSV de raios

```csv
lat,lon,tempo
-22.71,-43.28,2026-09-30T21:05:00Z
```

Aceita também `latitude`/`longitude` e `datetime`/`timestamp`/`data_hora`. O separador (`,` ou `;`) é detectado automaticamente. Com a coluna de tempo, é possível limitar às últimas horas do arquivo.

## Publicação no Streamlit Community Cloud

Envie esta pasta para um repositório GitHub. Na criação do aplicativo no [Streamlit Community Cloud](https://share.streamlit.io/), indique o repositório, a branch e o arquivo principal `app.py`. As dependências são instaladas a partir de `requirements.txt`.

## Fonte de dados

Previsões da API [Open-Meteo](https://open-meteo.com/), com as variáveis horárias `cape`, `lifted_index` e `convective_inhibition` (3 dias a partir de 00:00 de hoje).
