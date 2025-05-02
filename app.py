# app.py - Forex Alpha Signals 2.0 (Streamlit UI)

import streamlit as st
import pandas as pd
import os # <<< ADICIONADO OS
import time

# --- Leitura das Configurações via Variáveis de Ambiente ---
# Senha para acesso à interface Streamlit
SENHA_APP = os.environ.get("SENHA_APP", "default_password") # Use uma senha padrão segura ou exija a variável
# Caminho para o arquivo de log do worker (para exibição opcional)
log_file_path = os.environ.get("WORKER_LOG_PATH", "/home/ubuntu/forex_worker.log")
# ---------------------------------------------------------

# CONFIGURAÇÕES INICIAIS DA PÁGINA
st.set_page_config(page_title="Forex Alpha Signals 2.0 UI", layout="wide")
st.title("📊 Forex Alpha Signals 2.0 - Interface")

# Autenticação Simples para a Interface
if "autenticado" not in st.session_state:
    st.session_state.autenticado = False

if not st.session_state.autenticado:
    senha = st.text_input("Digite a senha para acessar a interface:", type="password")
    if not senha:
        st.stop()
    elif senha != SENHA_APP:
        st.error("Senha incorreta.")
        st.stop()
    else:
        st.session_state.autenticado = True
        st.rerun()

# --- Interface Principal ---

st.sidebar.header("Status do Sistema")
st.sidebar.info("""
Esta é a interface de visualização do Forex Alpha Signals 2.0.

A análise dos sinais e o envio de notificações ocorrem em um processo separado (Background Worker no Render).

As configurações de análise (Mercado, Timeframe, Risco) são definidas por variáveis de ambiente no Background Worker.
""")

# Layout Principal
col1, col2 = st.columns([3, 1])

with col1:
    st.markdown("""Bem-vindo à interface do **Forex Alpha Signals 2.0**!

    *   A análise dos ativos e o envio de sinais para o Telegram estão sendo executados em **segundo plano**.
    *   Para alterar as configurações de análise (mercado, timeframe, risco) ou o intervalo, ajuste as **variáveis de ambiente** do serviço Background Worker no Render.
    *   Use o botão na barra lateral para ver os logs recentes do processo de análise.
    """)

    # Exemplo: Exibir histórico lido de um arquivo/DB (NÃO IMPLEMENTADO AQUI)
    # Substitua esta seção pela leitura do seu banco de dados ou arquivo compartilhado
    with st.expander("📑 Ver/Ocultar Histórico de Sinais (Exemplo - Requer Implementação)"):
        st.info("Funcionalidade de exibição de histórico não implementada neste exemplo. Requer integração com banco de dados ou disco compartilhado entre o Worker e a App.")
        # Exemplo (se lendo de um CSV):
        # try:
        #     df_hist = pd.read_csv("/path/to/shared/historico_sinais.csv")
        #     st.dataframe(df_hist)
        # except FileNotFoundError:
        #     st.info("Nenhum histórico encontrado.")
        # except Exception as e:
        #     st.error(f"Erro ao ler histórico: {e}")

with col2:
    st.write(" ") # Espaçamento

# Botão para ver logs na sidebar
st.sidebar.header("Logs do Worker")
if st.sidebar.button("Ver Logs Recentes do Worker"):
    try:
        with open(log_file_path, "r") as f:
            # Lê as últimas N linhas (ajuste N conforme necessário)
            log_lines = f.readlines()
            log_content = "".join(log_lines[-50:]) # Exibe as últimas 50 linhas
        st.sidebar.text_area("Log Recente (forex_worker.log)", log_content, height=400)
        st.sidebar.success("Logs carregados.")
    except FileNotFoundError:
        st.sidebar.warning(f"Arquivo de log ({log_file_path}) não encontrado. Verifique o caminho ou se o worker já executou.")
    except Exception as e:
         st.sidebar.error(f"Erro ao ler o log: {e}")

# Nota sobre o estado da aplicação
st.sidebar.caption(f"Interface atualizada em: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


