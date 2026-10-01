# RUSBÉ — Dashboard de Risco de Raios

Versão em **Streamlit** do notebook `RUSBÉ—RastreamentoeUtilizaçãodeSistemaBaseadoemEletricidade(atmosférica).ipynb`. A interface consulta previsões horárias de CAPE, Lifted Index e CIN para 40 unidades, calcula um escore heurístico de risco de raios (0–100) e mostra o resultado em mapa, tabela, gráficos e alertas.

> O escore é um recurso de acompanhamento. Não substitui alertas oficiais, decisões operacionais de segurança ou sistemas dedicados de detecção de descargas atmosféricas.

## Funcionalidades

| Área | O que faz |
|---|---|
| **Mapa** | OpenStreetMap (padrão) ou Satélite, travado no Brasil (contorno + véu no entorno), botão ⌂ para recentralizar. Bolinhas de tamanho fixo (inclusive durante o zoom) com o score escrito dentro (opcional); a de maior risco fica por cima. A posição e o zoom são preservados ao fechar o painel. |
| **Hora da previsão** | Controle deslizante de +0 h a +48 h: o mapa, os cartões e a tabela passam a mostrar a hora escolhida. |
| **Tendência** | Seta ▲ ▼ ▬ por unidade (variação do score nas próximas 6 h), pico das próximas 24 h e horário do pico. A lista lateral pode ser ordenada por *Nome* ou *Maior risco*. |
| **Detalhe da unidade** | Cartões (risco, CAPE, LI, CIN, tendência e variáveis extras), gráfico de 48 h do score sobre as faixas de risco, gráficos de CAPE/LI/CIN e das variáveis extras e tabela horária. |
| **Regiões e variáveis extras** | O score usa CAPE, Lifted Index e CIN (regra original). Fatores de CAPE/LI por UF podem ser definidos em `config_regioes.json` (todos 1,0 por padrão). Precipitação, rajada, gradiente 850–500 hPa e nível de 0 °C aparecem como cartões e gráficos no detalhe da unidade e no histórico; para incluí-los no score há a opção `--heuristica-ampliada` do `alertas.py` (ainda não calibrada com observações). |
| **Como o score foi calculado** | No detalhe de cada unidade, uma tabela mostra os pontos de CAPE, Lifted Index e CIN, a soma, o ajuste de chuva (se houver) e o score final. |
| **Ajuste do Nordeste** | Em BA, CE, PE, RN e SE (`gate_precipitacao` em `config_regioes.json`), o score só vale integralmente se o modelo prevê chuva (≥ 0,1 mm/h) entre a hora atual e +3 h; senão é multiplicado por 0,5. Sem dado de precipitação o ajuste não é aplicado e o painel avisa. **Valores provisórios**, ainda não calibrados com observações; para desligar, esvazie `ufs`. |
| **Camadas do mapa** | Divisas estaduais (ligadas por padrão) e topos de nuvem do GOES-East, infravermelho banda 13, via NASA GIBS (opcional, com controle de opacidade). |
| **Histórico** | Grava em SQLite, uma vez por hora e por modelo, CAPE, LI, CIN e variáveis extras das próximas 48 h. O painel mostra o score realizado e os gráficos de CAPE, LI, CIN e variáveis extras no período, como a previsão para um horário mudou entre execuções, e exporta CSV com score recalculado. |
| **Exportação** | Tabela atual e séries horárias de 48 h em CSV (abre no Excel em português); mapa estático em PNG e relatório em PDF (mapa + ranking). |
| **Acessibilidade** | Score escrito dentro da bolinha e barra lateral recolhida em telas pequenas. |
| **Robustez** | 3 tentativas com espera crescente na API; se ela falhar, usa o último dado válido e avisa quantos minutos ele tem. Indicador "Dados · há N min" no cabeçalho. |
| **Alertas** | `alertas.py` envia e-mail e/ou webhook (Teams, Slack, Discord, gateway de WhatsApp) quando uma unidade atinge, ou deve atingir em poucas horas, o nível configurado. |

## Estrutura

| Arquivo | Finalidade |
|---|---|
| `app.py` | Interface Streamlit. |
| `analise.py` | Séries de score, tendência, extras e fatores por UF (sem dependência do Streamlit). |
| `historico.py` | Histórico das previsões em SQLite (módulo e linha de comando). |
| `app_camadas.py` | Endereço e atribuição da camada GOES. |
| `config_regioes.json` | Fatores de CAPE e LI por UF (neutros por padrão). |
| `risco_raio.py` | Heurística de risco, parâmetros de calibração e cores dos níveis. |
| `modelos.py` | Consulta dos modelos (com tentativas) e normalização da resposta. |
| `unidades.py` | As 40 unidades, coordenadas e UF. |
| `relatorio.py` | Geração do mapa PNG e do relatório PDF. |
| `alertas.py` | Verificação e envio de alertas (linha de comando). |
| `dados/` | Contorno, máscara e divisas estaduais simplificados (Natural Earth, domínio público). |
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
python validar.py                    # testes offline
python validar.py --online           # relatório de sanidade com dados reais (cobertura, faixas, horizonte, extras, GOES)
python validar.py --online --modelos # idem para os 12 modelos: mostra quais devolvem CAPE, LI e CIN
```

## Sobre o score

- Pontos: CAPE (0–45), Lifted Index (0–35) e CIN (−30 a +20), somados e limitados a 0–100.
- **Sem energia** (CAPE < 300 J/kg), o Lifted Index soma no máximo 5 pontos e a baixa inibição (CIN) não soma: ar estável não vira "Moderado".
- CAPE, LI e CIN medem *potencial*; não medem o disparo da convecção nem a umidade. Em regiões tropicais com CAPE quase sempre alto, o score tende a exagerar. Por isso existe o ajuste por chuva prevista (Nordeste) e os fatores por UF em `config_regioes.json`.

## Histórico

O painel grava automaticamente uma execução por modelo e por hora cheia quando os dados são buscados com sucesso. O arquivo fica em `historico/rusbe.sqlite` (mude com a variável `RUSBE_HISTORICO`; use `desligado` para não gravar).

```bash
python historico.py registrar                      # busca o modelo e grava (agende a cada hora)
python historico.py status
python historico.py exportar --saida historico.csv --dias 30
python historico.py limpar --manter-dias 90
```

> No Streamlit Community Cloud o disco é apagado quando o app reinicia, então o histórico lá não é permanente. Para um histórico de verdade, agende `python historico.py registrar` em uma máquina sua (cron/Agendador de Tarefas) ou use um volume persistente.

O histórico guarda as variáveis **brutas** (não o score), então dá para recalcular o score com outra calibração e compará-lo depois com observações.

## Alertas

```bash
python alertas.py --dry-run                                  # só imprime
python alertas.py --nivel Alto --antecedencia 3              # avisa em Alto+ ou previsto em até 3 h
python alertas.py --heuristica-ampliada                      # inclui precipitação, rajada etc. no score
```

Cada unidade é avisada **uma vez**; ela só é avisada de novo depois de voltar a ficar abaixo do nível. O estado fica em `estado_alertas.json`. Os canais são configurados por variáveis de ambiente (nenhuma é obrigatória, mas sem elas o script apenas imprime):

| Variável | Uso |
|---|---|
| `ALERTA_WEBHOOK_URL` | Webhook (recebe JSON com `text` e `content`). |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS` | Servidor de e-mail. |
| `ALERTA_EMAIL_DE`, `ALERTA_EMAIL_PARA` | Remetente e destinatários (separados por vírgula). |

Para rodar a cada 30 minutos sem servidor próprio, use o workflow `.github/workflows/alertas.yml` (cadastre as variáveis como *secrets* do repositório). O GitHub pode atrasar execuções agendadas em alguns minutos.

## Publicação no Streamlit Community Cloud

Envie esta pasta para um repositório GitHub. Na criação do aplicativo no [Streamlit Community Cloud](https://share.streamlit.io/), indique o repositório, a branch e o arquivo principal `app.py`. As dependências são instaladas a partir de `requirements.txt`.

## Fonte de dados

Previsões da API [Open-Meteo](https://open-meteo.com/), com as variáveis horárias `cape`, `lifted_index` e `convective_inhibition` (3 dias a partir de 00:00 de hoje) e, para a heurística ampliada, `precipitation`, `wind_gusts_10m`, `freezing_level_height`, `temperature_850hPa` e `temperature_500hPa`. Imagem de satélite: GOES-East via [NASA GIBS](https://nasa-gibs.github.io/gibs-api-docs/). Confira os termos de uso da Open-Meteo para o seu caso (o plano gratuito é voltado a uso não comercial).
