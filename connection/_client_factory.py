# connection/_client_factory.py

"""
Módulo Fábrica de Clientes API.

Su única responsabilidad es crear, configurar y verificar una instancia de cliente
de la API de Bybit (pybit.HTTP). Esto incluye la configuración inicial
específica de la cuenta, como el modo de posición (Hedge Mode).
"""
import sys
import traceback
from typing import Dict, Optional
from pybit.unified_trading import HTTP

# Dependencias del proyecto
import config
from core.logging import memory_logger

# Importar excepciones específicas con fallbacks
try:
    from pybit.exceptions import InvalidRequestError, FailedRequestError
except ImportError:
    class InvalidRequestError(Exception): pass
    class FailedRequestError(Exception):
        def __init__(self, message, status_code=None):
            super().__init__(message)
            self.status_code = status_code

def create_client(account_name: str, api_creds: Dict[str, str]) -> Optional[HTTP]:
    """
    Crea y verifica una única sesión de cliente HTTP.

    Args:
        account_name (str): El nombre de la cuenta para logging.
        api_creds (dict): Un diccionario con "key" y "secret".

    Returns:
        Un objeto de sesión HTTP si la conexión es exitosa, de lo contrario None.
    """
    memory_logger.log(f"Creando cliente API para '{account_name}'...", level="INFO")
    try:
        session = HTTP(
            testnet=getattr(config, 'UNIVERSAL_TESTNET_MODE', True),
            api_key=api_creds["key"],
            api_secret=api_creds["secret"],
            recv_window=getattr(config, 'DEFAULT_RECV_WINDOW', 10000)
        )
        # Verificar la conexión obteniendo la hora del servidor
        server_time = session.get_server_time()
        if server_time and server_time.get('retCode') == 0:
            memory_logger.log(f" -> Conexión exitosa para '{account_name}'.", level="INFO")
            return session
        else:
            msg = server_time.get('retMsg', 'Error desconocido')
            code = server_time.get('retCode', -1)
            memory_logger.log(f" -> ERROR de conexión para '{account_name}': {msg} (Code: {code})", level="ERROR")
            return None
    except Exception as e:
        memory_logger.log(f" -> ERROR crítico creando cliente '{account_name}': {e}", level="ERROR")
        memory_logger.log(traceback.format_exc(), level="ERROR")
        return None

def configure_account_mode(session: HTTP, account_name: str) -> bool:
    """
    Configura el modo de la cuenta (ej. Hedge Mode) si es necesario.

    Args:
        session (HTTP): La sesión de cliente a configurar.
        account_name (str): El nombre de la cuenta para logging.

    Returns:
        True si la configuración es exitosa o no es necesaria, False si falla.
    """
    if getattr(config, 'POSITION_TRADING_MODE', None) != "LONG_SHORT":
        return True # No se necesita configuración si no es Hedge Mode

    symbol = getattr(config, 'TICKER_SYMBOL', None)
    if not symbol:
        memory_logger.log("WARN [Account Mode]: Falta TICKER_SYMBOL en config para verificar modo.", level="WARN")
        return False

    category = getattr(config, 'CATEGORY_LINEAR', 'linear')
    target_mode = 3  # 3 para Hedge Mode

    memory_logger.log(f"Verificando/Estableciendo Hedge Mode para cuenta '{account_name}'...", level="INFO")
    
    try:
        response = session.switch_position_mode(category=category, symbol=symbol, mode=target_mode)
        
        # Códigos de éxito: 0 (cambiado) o 110021 (ya estaba en ese modo)
        if response and response.get('retCode') in [0, 110021]:
            memory_logger.log(f" -> ÉXITO: Modo Hedge confirmado para '{account_name}'.", level="INFO")
            return True
        elif response:
            code = response.get('retCode', -1)
            msg = response.get('retMsg', 'Error desconocido')
            memory_logger.log(f" -> ERROR API al configurar modo para '{account_name}': {msg} (Code: {code})", level="ERROR")
            return False
        else:
            memory_logger.log(f" -> ERROR: No se recibió respuesta de la API para '{account_name}'.", level="ERROR")
            return False

    except InvalidRequestError as e:
        if "110021" in str(e): # El modo no fue modificado, ya era el correcto
            memory_logger.log(f" -> ÉXITO: Modo Hedge ya estaba activo para '{account_name}' (110021).", level="INFO")
            return True
        else:
            memory_logger.log(f" -> ERROR API [Invalid Request] para '{account_name}': {e}", level="ERROR")
            return False
    except FailedRequestError as e:
        memory_logger.log(f" -> ERROR HTTP para '{account_name}': {e} (Status: {e.status_code})", level="ERROR")
        return False
    except Exception as e:
        memory_logger.log(f" -> ERROR Inesperado configurando modo para '{account_name}': {e}", level="ERROR")
        memory_logger.log(traceback.format_exc(), level="ERROR")
        return False