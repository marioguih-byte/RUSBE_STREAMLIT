# Tarefas da adaptação ao notebook

- [x] Corrigir a referência horária que permanece em UTC na versão publicada, invalidando também a entrada de cache anterior.
- [x] Converter a referência e a tabela horária explicitamente para America/Sao_Paulo.
- [x] Comparar os controles, a seleção de unidade e a janela detalhada do notebook com a aplicação Streamlit entregue.
- [x] Fazer o clique no marcador do mapa selecionar a unidade correspondente no estado da sessão.
- [x] Abrir um painel detalhado por unidade com medidas atuais e tabela de previsão horária.
- [x] Reorganizar a barra lateral para espelhar os controles operacionais do notebook.
- [x] Validar o fluxo de clique, seleção e atualização de dados no navegador. A barra lateral, os controles e os 40 cartões de unidades foram carregados; a seleção lateral abriu o pop-up de Porto Belém com a tabela colorida das próximas 24 horas. O tema escuro da janela também foi conferido.
- [x] Empacotar e entregar a versão Streamlit atualizada.

## Melhorias (fase 2)

- [x] Seletor de hora (+0 h a +48 h) e tendência ▲▼▬ com pico em 24 h.
- [x] Gráficos de score (com faixas de risco), CAPE, LI e CIN no detalhe da unidade.
- [x] Busca por nome e ordenação por nome ou maior risco.
- [x] Calibração da heurística (CAPE, LI, peso do CIN).
- [x] Tentativas na API, último dado válido e indicador de idade dos dados; mapa em fragmento.
- [x] Alertas por e-mail/webhook (`alertas.py`) e agendamento no GitHub Actions.
- [x] Exportação em CSV, PNG e PDF.
- [x] Score dentro das bolinhas.
- [x] Removidos a pedido: "Vai piorar", consenso entre modelos, paleta para daltonismo, altura do mapa, raios observados e filtros.

## Fase 3

- [x] Heurística ampliada opcional (precipitação, rajada, gradiente 850–500 hPa, nível de 0 °C), com consulta extra tolerante a falhas.
- [x] Ajuste por região (UF) com tabela editável e `config_regioes.json`.
- [x] Histórico das previsões em SQLite, com painel, exportação e linha de comando.
- [x] Divisas estaduais e camada de topos de nuvem (GOES-East via NASA GIBS).
- [x] `python validar.py --online [--modelos]`: relatório de sanidade com dados reais.
- [ ] Rodar `validar.py --online` no ambiente de produção e conferir a camada GOES (o ambiente de desenvolvimento não alcança a Open-Meteo nem a NASA GIBS).
- [ ] Calibrar os pesos da heurística ampliada e os fatores por UF com observações (o histórico já guarda o necessário).

- [x] Removida a aba "Calibração da heurística" (padrões mantidos); gráficos das variáveis extras no detalhe e no histórico.
- [x] Revisão de falsos alarmes no Nordeste: explicação do score por unidade, regra de baixa energia e ajuste por chuva prevista (BA, CE, PE, RN, SE; provisório).
- [ ] Calibrar o multiplicador e a janela do ajuste do Nordeste com observações de raios (o histórico guarda o necessário).

