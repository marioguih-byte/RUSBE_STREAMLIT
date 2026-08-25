# Validação da interação equivalente ao notebook

A interface Streamlit foi verificada no navegador com dados reais do modelo Best Match. A barra lateral apresentou os controles de modelo, estilo de mapa, centralização, busca e as 40 unidades monitoradas.

Foi selecionada a unidade **Porto Belém** na barra lateral. O mapa foi aproximado para a localização correspondente e abriu uma janela de detalhe com a previsão horária. A tabela apresentou as colunas equivalentes ao notebook: horário, CAPE, Lifted Index, CIN, score e risco, com a primeira linha marcada como “agora” e linhas coloridas pelo nível de risco.

O clique de marcador está implementado pelo retorno do tooltip do mapa e foi incluído no fluxo de seleção da aplicação. A atualização do tema da janela foi aplicada e conferida: o painel de detalhe agora usa fundo escuro, linhas por nível de risco e ação de fechamento em amarelo, mantendo coerência com a aparência do notebook.
