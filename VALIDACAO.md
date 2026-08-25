# Validação da Aplicação RUSBÉ

A versão Streamlit foi iniciada localmente e respondeu com sucesso no endpoint de saúde em 25/08/2026. A validação visual confirmou o carregamento do painel com os controles laterais, indicadores de risco, mapa interativo, tabela de unidades e detalhamento da estação selecionada.

A consulta ao modelo **Best Match (automático)** retornou dados para as 40 estações. Na verificação, havia 3 unidades classificadas como risco moderado, 37 como baixo ou nenhum e nenhuma unidade sem dados.

A visualização exibiu corretamente a série horária de CAPE, Lifted Index, CIN e escore de risco para a unidade selecionada, além de marcadores coloridos no mapa. Não foram identificados erros de inicialização no log do servidor.
