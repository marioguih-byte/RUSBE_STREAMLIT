# Diagnóstico da versão pública

Em 25/08/2026, a aplicação publicada em `rusbe-raios.streamlit.app` exibiu no cabeçalho a referência **20:00 (25/08)**. A versão corrigida no ambiente de trabalho retorna a referência em `America/Sao_Paulo`, validada como **17:00 (25/08)** no mesmo momento.

Portanto, a implantação pública ainda está executando o código anterior. É necessário enviar a versão atualizada de `modelos.py` e `app.py` ao repositório conectado ao Streamlit Community Cloud e acionar novo deploy/reboot.
