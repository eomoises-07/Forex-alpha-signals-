# worker.py - Forex Alpha Signals 2.0 (Background Analysis Worker)

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
import threading
import time
import logging
import traceback
import os # <<< ADICIONADO OS

# --- Configuração do Logging ---
log_formatter = logging.Formatter("%(asctime)s - %(levelname)s - Thread: %(threadName)s - %(message)s")
# Define o caminho do log (pode ser configurado via env var se necessário)
log_file_path = os.environ.get("WORKER_LOG_PATH", "/home/ubuntu/forex_worker.log")
log_handler = logging.FileHandler(log_file_path)
log_handler.setFormatter(log_formatter)

logger = logging.getLogger("forex_worker_logger")
logger.setLevel(logging.INFO)
if logger.hasHandlers():
    logger.handlers.clear()
logger.addHandler(log_handler)
# Adiciona também um handler para o console para ver a saída imediatamente no Render logs
console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)
logger.addHandler(console_handler)
logger.propagate = False
# -------------------------------

# --- Leitura das Configurações via Variáveis de Ambiente ---
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
# Lê configurações de análise ou usa defaults
DEFAULT_MARKET = os.environ.get("DEFAULT_MARKET", "Câmbio (Forex)")
DEFAULT_TIMEFRAME = os.environ.get("DEFAULT_TIMEFRAME", "15m")
DEFAULT_STOP_DEV = float(os.environ.get("DEFAULT_STOP_DEV", 0.003))
DEFAULT_TAKE_DEV = float(os.environ.get("DEFAULT_TAKE_DEV", 0.003))
ANALYSIS_INTERVAL_MINUTES = int(os.environ.get("ANALYSIS_INTERVAL_MINUTES", 10))
# ---------------------------------------------------------

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
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": mensagem}
    try:
        response = requests.post(url, data=data, timeout=20)
        logger.info(f"[TELEGRAM] Status Code: {response.status_code}")
        logger.info(f"[TELEGRAM] Response Body: {response.text[:500]}...") # Log truncado
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
    logger.info(f"[OBTER_DADOS] Iniciando para {ticker} | TF: {tf}")
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
        periodo = "1mo"
    intervalo = tf
    logger.info(f"[OBTER_DADOS] Baixando para {ticker} | Intervalo: {intervalo} | Período: {periodo}")
    try:
        df = yf.download(ticker, period=periodo, interval=intervalo, progress=False)
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
                    df.index = df.index.tz_localize("UTC") # Assume UTC se não tiver TZ
                # Converte para SP para consistência, mas o horário final será UTC
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
    logger.info(f"[ANALISAR] Iniciando para {ativo}")
    if df is None or df.empty:
        logger.error(f"[ANALISAR] Erro: DataFrame vazio ou None recebido para {ativo}.")
        return None
    try:
        close = df["Close"].squeeze()
        # Verifica se há dados suficientes após remover NaNs potenciais dos indicadores
        required_length = 21 # Max window size (EMA21, BB20)
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

        # Treinamento do Modelo IA
        df["Alvo"] = (df["Close"].shift(-1) > df["Close"]).astype(int)
        df_train = df.iloc[:-1].copy()
        df_train = df_train.dropna() # Garante que não há NaNs no treino

        if df_train.empty or df_train.shape[0] < 10:
            logger.warning(f"[ANALISAR] Dados insuficientes para treinar modelo para {ativo} após ajustes. Shape: {df_train.shape}")
            return None

        features = ["EMA9", "EMA21", "MACD", "RSI", "BB_High", "BB_Mid", "BB_Low"]
        X_train = df_train[features]
        y_train = df_train["Alvo"]
        X_predict = df[features].iloc[-1:]

        # Verifica se há NaNs nos dados de previsão
        if X_predict.isnull().values.any():
            logger.warning(f"[ANALISAR] NaN encontrado nos dados de previsão para {ativo}. Pulando.")
            return None

        modelo = DecisionTreeClassifier(random_state=42)
        modelo.fit(X_train, y_train)
        previsao_ult = modelo.predict(X_predict)[0]

        # Geração do Sinal
        ult = df.iloc[-1]
        tipo = "📈 Compra" if previsao_ult == 1 else "📉 Venda"
        entrada = ult["Close"]
        stop = entrada * (1 - stop_dev) if tipo == "📈 Compra" else entrada * (1 + stop_dev)
        alvo = entrada * (1 + take_dev) if tipo == "📈 Compra" else entrada * (1 - take_dev)

        # Garante que o índice é DatetimeIndex antes de converter TZ
        horario_local = ult.name
        if isinstance(horario_local, pd.Timestamp):
            try:
                horario_utc = horario_local.tz_convert("UTC")
                horario_str = horario_utc.strftime("%d/%m/%Y %H:%M UTC")
            except TypeError:
                 logger.warning(f"[ANALISAR] Falha ao converter horário para UTC para {ativo} (talvez já seja ingênuo?). Usando horário local.")
                 horario_str = horario_local.strftime("%d/%m/%Y %H:%M Local")
        else:
            logger.warning(f"[ANALISAR] Índice do último dado não é Timestamp para {ativo}. Usando 'N/A' para horário.")
            horario_str = "N/A"

        mensagem = f"""🔔 Sinal gerado ({mercado})\n\nAtivo: {ativo}\nSinal: {tipo}\nEntrada: {entrada:.5f}\nStop: {stop:.5f}\nTake: {alvo:.5f}\nHorário: {horario_str}\nBase: EMA + MACD + RSI + BB + IA"""
        sinal_info = {
            "Data/Hora": horario_str,
            "Mercado": mercado,
            "Ativo": ativo,
            "Sinal": tipo,
            "Entrada": round(entrada, 5),
            "Stop": round(stop, 5),
            "Alvo": round(alvo, 5),
            "Mensagem": mensagem
        }
        logger.info(f"[ANALISAR] Sinal gerado para {ativo}: {tipo}")
        # Aqui você poderia salvar o sinal_info em um banco de dados ou arquivo
        # Ex: salvar_sinal_db(sinal_info)
        return sinal_info
    except Exception as e:
        logger.error(f"[ANALISAR] Erro inesperado durante análise de {ativo}: {e}\n{traceback.format_exc()}")
        return None

# --- Funções para Análise em Background ---
def analisar_ativo(ativo, mercado, timeframe, stop_dev, take_dev):
    logger.info(f"[BG_ATIVO] Iniciando análise para {ativo} ({mercado}) - {timeframe}")
    df = obter_dados(ativo, timeframe)
    if df is not None:
        sinal_info = analisar(df, ativo, mercado, stop_dev, take_dev)
        if sinal_info:
             logger.info(f"[BG_ATIVO] Sinal encontrado para {ativo}.")
        else:
             logger.info(f"[BG_ATIVO] Nenhum sinal encontrado para {ativo}.")
        return sinal_info
    else:
        logger.warning(f"[BG_ATIVO] Falha ao obter dados para {ativo} - {timeframe}. Pulando análise.")
        return None

def analisar_todos_ativos_background(ativos_dict, mercado_selecionado, timeframe, stop_dev, take_dev):
    logger.info(f"[BG_TODOS] Iniciando análise para mercado: {mercado_selecionado} | Timeframe: {timeframe}")

    lista_ativos_para_analisar = ativos_dict.get(mercado_selecionado, [])

    if not lista_ativos_para_analisar:
        logger.warning(f"[BG_TODOS] Nenhum ativo encontrado para o mercado selecionado: {mercado_selecionado}")
        return []

    novos_sinais = []
    for ativo in lista_ativos_para_analisar:
        logger.info(f"[BG_TODOS] Processando ativo: {ativo}")
        try:
            sinal = analisar_ativo(ativo, mercado_selecionado, timeframe, stop_dev, take_dev)
            if sinal:
                novos_sinais.append(sinal)
                try:
                    enviar_telegram(sinal["Mensagem"])
                    logger.info(f"[BG_TODOS] Notificação enviada para {ativo}.")
                except Exception as e_telegram:
                    logger.error(f"[BG_TODOS] Erro ao tentar enviar notificação para {ativo}: {e_telegram}")
            # Pausa curta entre ativos para evitar sobrecarga da API yfinance
            time.sleep(3)
        except Exception as e_ativo:
             logger.error(f"[BG_TODOS] Erro ao processar ativo {ativo}: {e_ativo}\n{traceback.format_exc()}")
             time.sleep(3) # Evita loop rápido em caso de erro repetido

    logger.info(f"[BG_TODOS] Análise concluída para {mercado_selecionado}. {len(novos_sinais)} sinais gerados.")
    # Aqui você poderia salvar a lista novos_sinais em um DB/arquivo
    return novos_sinais

def loop_automatico(ativos_dict, tempo_espera_minutos):
    logger.info(f"[AGENDADOR] ***** WORKER INICIADO ***** Intervalo: {tempo_espera_minutos} min")
    try:
        while True:
            logger.info("[AGENDADOR] --- Iniciando novo ciclo de análise --- ")
            # Usa as configurações lidas das variáveis de ambiente ou defaults
            mercado_atual = DEFAULT_MARKET
            tf = DEFAULT_TIMEFRAME
            sd = DEFAULT_STOP_DEV
            td = DEFAULT_TAKE_DEV
            logger.info(f"[AGENDADOR] Configurações: Mercado={mercado_atual}, TF={tf}, Stop={sd}, Take={td}")

            logger.info(f"[AGENDADOR] Chamando analisar_todos_ativos_background...")
            try:
                analisar_todos_ativos_background(ativos_dict, mercado_atual, tf, sd, td)
            except Exception as e_analise:
                logger.error(f"[AGENDADOR] Erro DENTRO de analisar_todos_ativos_background: {e_analise}\n{traceback.format_exc()}")

            logger.info(f"[AGENDADOR] Ciclo concluído. Aguardando {tempo_espera_minutos} minutos...")
            time.sleep(tempo_espera_minutos * 60)

    except Exception as e_loop:
        logger.error(f"[AGENDADOR] !!!!! ERRO FATAL NO LOOP PRINCIPAL DO WORKER !!!!!: {e_loop}\n{traceback.format_exc()}")
    finally:
        logger.critical("[AGENDADOR] !!!!! WORKER ENCERRADO INESPERADAMENTE !!!!!")

if __name__ == "__main__":
    logger.info("[MAIN] Iniciando Forex Alpha Signals Worker...")
    # Verifica se as credenciais essenciais estão presentes
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logger.critical("[MAIN] ERRO CRÍTICO: TELEGRAM_TOKEN ou TELEGRAM_CHAT_ID não definidos nas variáveis de ambiente. Encerrando.")
    else:
        # Inicia o loop principal diretamente (sem thread extra necessária aqui)
        loop_automatico(ativos, ANALYSIS_INTERVAL_MINUTES)

