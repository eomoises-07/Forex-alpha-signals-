Forex Alpha Signals 2.0

Sistema de análise automática de sinais para o mercado financeiro com IA, indicadores técnicos e envio de alertas via Telegram. Desenvolvido em Python com Streamlit.

Funcionalidades

Análise de pares de moedas (Forex), ações, criptomoedas e commodities.

Indicadores: EMA, MACD, RSI e Bandas de Bollinger.

Classificação com árvore de decisão (IA).

Geração automática de sinais de Compra/Venda.

Envio de alertas para o Telegram.

Histórico de sinais com exportação CSV.

Interface web com Streamlit.

Execução contínua em segundo plano com worker agendado (Render).


Estrutura

app.py: interface principal com Streamlit.

worker.py: agendador automático que realiza análises a cada 10 minutos.

config.py: armazena o token e chat_id do Telegram e a senha do app.

requirements.txt: dependências do projeto.


Como executar localmente

1. Clone o repositório:



git clone https://github.com/eomoises-07/Forex-alpha-signals-.git
cd Forex-alpha-signals-

2. Instale os pacotes:



pip install -r requirements.txt

3. Crie o arquivo config.py com:



TELEGRAM_TOKEN = 7721305430:AAG1f_3Ne79H3vPkrgPIaJ6VtrM4o0z62ws
TELEGRAM_CHAT_ID = 201011370
SENHA_APP = Deuséfiel

4. Inicie a interface web:



streamlit run app.py

(O worker será executado no Render como serviço separado)

Deploy (Render)

Crie um Web Service apontando para app.py

Crie um Background Worker apontando para worker.py

Certifique-se de que o config.py está no repositório (evite expor dados sensíveis em projetos públicos)
