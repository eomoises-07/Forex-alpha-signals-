# Forex Alpha Signals

Forex Alpha Signals é um sistema de análise técnica automatizada para o mercado Forex. Ele analisa múltiplos pares de moedas e múltiplos timeframes, identifica oportunidades de entrada com base em indicadores e envia alertas em tempo real por Telegram e pela interface web.

## Funcionalidades

- Análise técnica automática com execução periódica em segundo plano
- Suporte a múltiplos pares de moedas e múltiplos timeframes (selecionáveis no frontend)
- Interface web desenvolvida com Streamlit
- Envio de alertas de sinais via Telegram
- Exibição dos sinais diretamente no app
- Histórico completo de sinais gerados
- Painel de controle com botão de atualização manual
- Sistema de login com proteção por senha

## Tecnologias utilizadas

- Python 3.10+
- Streamlit (frontend)
- Pandas, TA-Lib, yfinance (análise técnica)
- APScheduler (execução periódica)
- Telegram Bot API (alertas)
- Railway (hospedagem backend e worker)

## Estrutura do Projeto

- `app.py`: Interface principal do usuário (frontend Streamlit)
- `worker.py`: Analisador automático em segundo plano
- `analyzer.py`: Módulo central de análise técnica
- `telegram_alert.py`: Integração com Telegram
- `utils/`: Utilitários e suporte para a aplicação

## Como rodar localmente

1. Clone o repositório:
   ```bash
   git clone https://github.com/seu-usuario/Forex-alpha-signals.git
   cd Forex-alpha-signals

2. Instale as dependências:

pip install -r requirements.txt


3. Configure variáveis de ambiente (como o token do bot Telegram) via .env.


4. Execute a interface:

streamlit run app.py


5. (Opcional) Execute o worker em segundo plano:

python worker.py



Deploy

Este projeto é hospedado gratuitamente no Railway, utilizando dois serviços:

Serviço 1: Interface web (Streamlit)

Serviço 2: Worker backend (Python puro)


Ambos compartilham o mesmo repositório e requerem variáveis de ambiente apropriadas para funcionar corretamente.

Licença

Este projeto está licenciado sob a MIT License.
