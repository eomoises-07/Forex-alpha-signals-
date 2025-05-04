# worker_all_markets.py - Forex Alpha Signals 2.0 (Background Worker - All Markets)

import yfinance as yf
import pandas as pd
import numpy as np
import pytz
from ta.trend import EMAIndicator, MACD
from ta.momentum import RSIIndicator
from ta.volatility import BollingerBands
from sklearn.tree import DecisionTreeClassifier
import requests
from datetime import datetime
import time
import logging
import traceback
import os

# --- Configuração do Logging ---
log_formatter = logging.Formatter("%(asctime)s - %(levelname)s - TF:%(timeframe)s - %(message)s")
# Define o caminho do log (pode ser configurado via env var se necessário)
log_file_path = os.environ.get("WORKER_LOG_PATH", "/home/ubuntu/forex_worker.log") # Railway pode usar stdout/stderr
log_handler = logging.FileHandler(log_file_path)
log_handler.setFormatter(log_formatter)

logger = logging.getLogger("forex_worker_logger")
logger.setLevel(logging.INFO)
if logger.hasHandlers():
    logger.handlers.clear()
logger.addHandler(log_handler)
# Adiciona também um handler para o console para ver a saída imediatamente nos logs da plataforma
console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)
logger.addHandler(console_handler)
logger.propagate = False
# -------------------------------

# --- Leitura das Configurações via Variáveis de Ambiente ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
# Timeframe é a configuração principal para esta instância do worker
WORKER_TIMEFRAME = os.environ.get("WORKER_TIMEFRAME", "15m") # ESSENCIAL: Define o TF desta instância
# Configurações de risco (podem ser globais ou específicas por worker)
DEFAULT_STOP_DEV = float(os.environ.get("DEFAULT_STOP_DEV", 0.003))
DEFAULT_TAKE_DEV = float(os.environ.get("DEFAULT_TAKE_DEV", 0.003))
ANALYSIS_INTERVAL_MINUTES = int(os.environ.get("ANALYSIS_INTERVAL_MINUTES", 15)) # Aumentado padrão devido a mais ativos
# ---------------------------------------------------------

# Adiciona o timeframe ao logger para diferenciar instâncias
logger = logging.LoggerAdapter(logger, {"timeframe": WORKER_TIMEFRAME})

# Definição de ativos (pode ser movido para config ou env vars se complexo)
ativos = {
    "Câmbio (Forex)": ["EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X", "USDCAD=X"],
    "Criptomoedas": ["BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD"],
    "Ações": ["AAPL", "MSFT", "AMZN", "PETR4.SA", "VALE3.SA"],
    "Commodities": ["GC=F", "CL=F", "SI=F"]
}

# Telegram
def enviar_telegram(mensagem):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logger.error("[TELEGRAM] Token ou Chat ID não configurados nas variáveis de ambiente.")
        return

    logger.info(f"[TELEGRAM] Tentando enviar mensagem...")
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    # Adiciona o Timeframe à mensagem
    mensagem_com_tf = f"[{WORKER_TIMEFRAME}] {mensagem}"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": mensagem_com_tf}
    try:
        response = requests.post(url, data=data, timeout=20)
        logger.info(f"[TELEGRAM] Status Code: {response.status_code}")
        # logger.info(f"[TELEGRAM] Response Body: {response.text[:500]}...") # Log truncado
        response.raise_for_status()
        logger.info("[TELEGRAM] Notificação enviada com sucesso.")
    except requests.exceptions.Timeout:
        logger.error("[TELEGRAM] ALERTA: Timeout ao enviar notificação.")
    except requests.exceptions.RequestException as e:
        logger.error(f"[TELEGRAM] ALERTA: Falha na requisição: {e}")
        if e.response is not None:
             logger.error(f"[TELEGRAM] Response Status: {e.response.status_code}")
             logger.error(f"[TELEGRAM] Response Body: {e.response.text[:500]}...")
    except Exception as e:
        logger.error(f"[TELEGRAM] ALERTA: Erro inesperado ao enviar notificação: {e}\n{traceback.format_exc()}")

# Funções de análise (sem modificações na lógica interna, apenas logging)
def obter_dados(ticker, tf):
    logger.info(f"[OBTER_DADOS] Iniciando para {ticker}")
    if tf in ["15m", "30m"]:
        periodo = "60d"
    elif tf in ["1h", "4h"]:
        periodo = "730d"
    elif tf == "1d":
        periodo = "5y"
    elif tf == "1wk":
        periodo = "10y"
    elif tf == "1mo":
        periodo = "max"
    else:
        logger.warning(f"[OBTER_DADOS] Timeframe inválido: {tf}. Usando '1mo'.")
        periodo = "1mo"
        tf = "1mo" # Corrige o tf para o intervalo usado
    intervalo = tf
    logger.info(f"[OBTER_DADOS] Baixando para {ticker} | Intervalo: {intervalo} | Período: {periodo}")
    try:
        df = yf.download(ticker, period=periodo, interval=intervalo, progress=False, timeout=30) # Adicionado timeout
        if df.empty:
            logger.error(f"[OBTER_DADOS] Erro: Nenhum dado retornado por yfinance para {ticker} com intervalo {tf} e período {periodo}.")
            return None
        df = df.dropna()
        if df.empty:
            logger.error(f"[OBTER_DADOS] Erro: Dados retornados, mas vazios após dropna para {ticker} com intervalo {tf}.")
            return None
        try:
            if isinstance(df.index, pd.DatetimeIndex):
                if df.index.tz is None:
                    df.index = df.index.tz_localize("UTC")
                df.index = df.index.tz_convert("America/Sao_Paulo")
            else:
                logger.warning(f"[OBTER_DADOS] Aviso: Índice não é DatetimeIndex para {ticker}. Conversão de fuso pulada.")
        except Exception as e:
            logger.warning(f"[OBTER_DADOS] Aviso: Falha ao converter fuso horário para {ticker}: {e}. Usando dados como estão.")
        logger.info(f"[OBTER_DADOS] Dados para {ticker} baixados e processados com sucesso. Shape: {df.shape}")
        return df
    except Exception as e:
        logger.error(f"[OBTER_DADOS] Erro GERAL ao baixar/processar dados para {ticker} com intervalo {tf}: {e}\n{traceback.format_exc()}")
        return None

def analisar(df, ativo, mercado, stop_dev, take_dev):
    logger.info(f"[ANALISAR] Iniciando para {ativo} ({mercado})")
    if df is None or df.empty:
        logger.error(f"[ANALISAR] Erro: DataFrame vazio ou None recebido para {ativo}.")
        return None
    try:
        close = df["Close"].squeeze()
        required_length = 21
        if len(close) < required_length:
             logger.warning(f"[ANALISAR] Dados insuficientes para {ativo} antes dos indicadores ({len(close)} < {required_length}).")
             return None

        df["EMA9"] = EMAIndicator(close, window=9).ema_indicator()
        df["EMA21"] = EMAIndicator(close, window=21).ema_indicator()
        df["MACD"] = MACD(close).macd()
        df["RSI"] = RSIIndicator(close).rsi()
        bb = BollingerBands(close, window=20, window_dev=2)
        df["BB_High"] = bb.bollinger_hband()
        df["BB_Mid"] = bb.bollinger_mavg()
        df["BB_Low"] = bb.bollinger_lband()
        df = df.dropna()

        if df.empty or df.shape[0] < 10:
            logger.warning(f"[ANALISAR] Dados insuficientes para {ativo} após cálculo de indicadores. Shape: {df.shape}")
            return None

        df["Alvo"] = (df["Close"].shift(-1) > df["Close"]).astype(int)
        df_train = df.iloc[:-1].copy()
        df_train = df_train.dropna()

        if df_train.empty or df_train.shape[0] < 10:
            logger.warning(f"[ANALISAR] Dados insuficientes para treinar modelo para {ativo} após ajustes. Shape: {df_train.shape}")
            return None

        features = ["EMA9", "EMA21", "MACD", "RSI", "BB_High", "BB_Mid", "BB_Low"]
        X_train = df_train[features]
        y_train = df_train["Alvo"]
        X_predict = df[features].iloc[-1:]

        if X_predict.isnull().values.any():
            logger.warning(f"[ANALISAR] NaN encontrado nos dados de previsão para {ativo}. Pulando.")
            return None

        modelo = DecisionTreeClassifier(random_state=42)
        modelo.fit(X_train, y_train)
        previsao_ult = modelo.predict(X_predict)[0]

        ult = df.iloc[-1]
        tipo = "📈 Compra" if previsao_ult == 1 else "📉 Venda"
        entrada = ult["Close"]
        stop = entrada * (1 - stop_dev) if tipo == "📈 Compra" else entrada * (1 + stop_dev)
        alvo = entrada * (1 + take_dev) if tipo == "📈 Compra" else entrada * (1 - take_dev)

        horario_local = ult.name
        if isinstance(horario_local, pd.Timestamp):
            try:
                horario_utc = horario_local.tz_convert("UTC")
                horario_str = horario_utc.strftime("%d/%m/%Y %H:%M UTC")
            except TypeError:
                 logger.warning(f"[ANALISAR] Falha ao converter horário para UTC para {ativo}. Usando horário local.")
                 horario_str = horario_local.strftime("%d/%m/%Y %H:%M Local")
        else:
            logger.warning(f"[ANALISAR] Índice do último dado não é Timestamp para {ativo}. Usando 'N/A' para horário.")
            horario_str = "N/A"

        # Mensagem original (sem o TF, que será adicionado pela função enviar_telegram)
        mensagem_base = f"""🔔 Sinal gerado ({mercado})\n\nAtivo: {ativo}\nSinal: {tipo}\nEntrada: {entrada:.5f}\nStop: {stop:.5f}\nTake: {alvo:.5f}\nHorário: {horario_str}\nBase: EMA + MACD + RSI + BB + IA"""
        sinal_info = {
            "Data/Hora": horario_str,
            "Mercado": mercado,
            "Ativo": ativo,
            "Sinal": tipo,
            "Entrada": round(entrada, 5),
            "Stop": round(stop, 5),
            "Alvo": round(alvo, 5),
            "Mensagem": mensagem_base # Salva a mensagem base
        }
        logger.info(f"[ANALISAR] Sinal gerado para {ativo}: {tipo}")
        return sinal_info
    except Exception as e:
        logger.error(f"[ANALISAR] Erro inesperado durante análise de {ativo}: {e}\n{traceback.format_exc()}")
        return None

# --- Funções para Análise em Background ---
def analisar_ativo(ativo, mercado, timeframe, stop_dev, take_dev):
    logger.info(f"[BG_ATIVO] Iniciando análise para {ativo} ({mercado})")
    df = obter_dados(ativo, timeframe)
    if df is not None:
        sinal_info = analisar(df, ativo, mercado, stop_dev, take_dev)
        if sinal_info:
             logger.info(f"[BG_ATIVO] Sinal encontrado para {ativo}.")
        else:
             logger.info(f"[BG_ATIVO] Nenhum sinal encontrado para {ativo}.")
        return sinal_info
    else:
        logger.warning(f"[BG_ATIVO] Falha ao obter dados para {ativo}. Pulando análise.")
        return None

# <<< MODIFICADO: Esta função agora só processa um mercado por vez >>>
def analisar_um_mercado(ativos_dict, mercado_nome, timeframe, stop_dev, take_dev):
    logger.info(f"[BG_MERCADO] Iniciando análise para mercado: {mercado_nome}")

    lista_ativos_para_analisar = ativos_dict.get(mercado_nome, [])

    if not lista_ativos_para_analisar:
        logger.warning(f"[BG_MERCADO] Nenhum ativo encontrado para o mercado: {mercado_nome}")
        return

    sinais_mercado = 0
    for ativo in lista_ativos_para_analisar:
        logger.info(f"[BG_MERCADO] Processando ativo: {ativo}")
        try:
            sinal = analisar_ativo(ativo, mercado_nome, timeframe, stop_dev, take_dev)
            if sinal:
                sinais_mercado += 1
                try:
                    # Envia a mensagem base, o TF será adicionado pela função de envio
                    enviar_telegram(sinal["Mensagem"])
                    logger.info(f"[BG_MERCADO] Notificação enviada para {ativo}.")
                except Exception as e_telegram:
                    logger.error(f"[BG_MERCADO] Erro ao tentar enviar notificação para {ativo}: {e_telegram}")
            # Pausa curta entre ativos para evitar sobrecarga da API yfinance
            time.sleep(5) # Aumentado um pouco
        except Exception as e_ativo:
             logger.error(f"[BG_MERCADO] Erro ao processar ativo {ativo}: {e_ativo}\n{traceback.format_exc()}")
             time.sleep(5)

    logger.info(f"[BG_MERCADO] Análise concluída para {mercado_nome}. {sinais_mercado} sinais gerados.")

# <<< MODIFICADO: Loop principal agora itera por todos os mercados >>>
def loop_automatico(ativos_dict, timeframe, stop_dev, take_dev, tempo_espera_minutos):
    logger.info(f"[AGENDADOR] ***** WORKER INICIADO ***** Timeframe: {timeframe} | Intervalo Ciclo: {tempo_espera_minutos} min")
    try:
        while True:
            logger.info("[AGENDADOR] --- Iniciando novo ciclo de análise (todos os mercados) --- ")
            ciclo_inicio_tempo = time.time()

            # Itera por cada mercado definido no dicionário 'ativos'
            for nome_mercado in ativos_dict.keys():
                logger.info(f"[AGENDADOR] Chamando análise para o mercado: {nome_mercado}...")
                try:
                    analisar_um_mercado(ativos_dict, nome_mercado, timeframe, stop_dev, take_dev)
                except Exception as e_analise_mercado:
                    logger.error(f"[AGENDADOR] Erro DENTRO da análise do mercado {nome_mercado}: {e_analise_mercado}\n{traceback.format_exc()}")
                logger.info(f"[AGENDADOR] Análise do mercado {nome_mercado} concluída.")
                time.sleep(10) # Pausa entre mercados

            ciclo_fim_tempo = time.time()
            duracao_ciclo = ciclo_fim_tempo - ciclo_inicio_tempo
            logger.info(f"[AGENDADOR] Ciclo completo (todos os mercados) concluído em {duracao_ciclo:.2f} segundos.")

            # Calcula o tempo de espera restante para completar o intervalo definido
            tempo_espera_segundos = max(0, (tempo_espera_minutos * 60) - duracao_ciclo)
            logger.info(f"[AGENDADOR] Aguardando {tempo_espera_segundos:.2f} segundos para o próximo ciclo...")
            time.sleep(tempo_espera_segundos)

    except Exception as e_loop:
        logger.error(f"[AGENDADOR] !!!!! ERRO FATAL NO LOOP PRINCIPAL DO WORKER !!!!!: {e_loop}\n{traceback.format_exc()}")
    finally:
        logger.critical("[AGENDADOR] !!!!! WORKER ENCERRADO INESPERADAMENTE !!!!!")

if __name__ == "__main__":
    logger.info("[MAIN] Iniciando Forex Alpha Signals Worker (All Markets)...")
    # Verifica se as credenciais essenciais estão presentes
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logger.critical("[MAIN] ERRO CRÍTICO: TELEGRAM_TOKEN ou TELEGRAM_CHAT_ID não definidos nas variáveis de ambiente. Encerrando.")
    else:
        # Inicia o loop principal diretamente, passando as configurações lidas
        loop_automatico(ativos, WORKER_TIMEFRAME, DEFAULT_STOP_DEV, DEFAULT_TAKE_DEV, ANALYSIS_INTERVAL_MINUTES)

