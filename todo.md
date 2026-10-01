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
- [x] Filtros por nível, UF e nome; ordenação "Vai piorar".
- [x] Consenso entre modelos (média, mín.–máx. e uma linha por modelo).
- [x] Calibração da heurística (CAPE, LI, peso do CIN) e camada de raios observados via CSV.
- [x] Tentativas na API, último dado válido e indicador de idade dos dados; mapa em fragmento.
- [x] Alertas por e-mail/webhook (`alertas.py`) e agendamento no GitHub Actions.
- [x] Exportação em CSV, PNG e PDF.
- [x] Paleta para daltonismo, score dentro das bolinhas e altura do mapa ajustável.

