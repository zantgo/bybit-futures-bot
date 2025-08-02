# connection/_credentials.py

"""
Módulo para la Carga y Validación de Credenciales.

Su única responsabilidad es interactuar con el archivo .env para cargar y validar
las claves API y los UIDs necesarios para la operación del bot, basándose en la
configuración definida en config.py.
"""
import os
from typing import Dict
from dotenv import load_dotenv, find_dotenv

# Dependencias del proyecto
import config
from core.logging import memory_logger

def load_api_credentials() -> Dict[str, Dict[str, str]]:
    """
    Carga las credenciales API desde el archivo .env.

    Returns:
        Un diccionario con las credenciales API encontradas, con el formato
        { "account_name": {"key": "...", "secret": "..."} }.
    """
    _find_and_load_env()

    api_credentials = {}
    api_map = config.BOT_CONFIG["API_KEYS_ENV_MAP"]
    accounts_to_check = config.BOT_CONFIG["ACCOUNTS"].values()

    for account_name in accounts_to_check:
        if account_name in api_map:
            key_env_var, secret_env_var = api_map[account_name]
            api_key = os.getenv(key_env_var)
            api_secret = os.getenv(secret_env_var)

            if not api_key or not api_secret or api_key.startswith("YOUR_"):
                memory_logger.log(f"WARN [Credentials]: Claves API no encontradas o sin configurar para '{account_name}'.", level="WARN")
            else:
                api_credentials[account_name] = {"key": api_key, "secret": api_secret}
    
    return api_credentials

def load_and_validate_uids():
    """
    Carga y valida los UIDs desde el .env y los almacena en config.LOADED_UIDS.
    """
    _find_and_load_env()
    
    uid_map = config.BOT_CONFIG["UID_ENV_VAR_MAP"]
    if not uid_map:
        memory_logger.log("Info [Credentials]: No hay mapeo de UIDs en config.", level="INFO")
        return

    memory_logger.log("Validando UIDs desde .env...", level="INFO")
    
    loaded_uids_temp = {}
    all_uids_valid = True
    for account_name, env_var_name in uid_map.items():
        uid_value = os.getenv(env_var_name)
        if uid_value and uid_value.strip().isdigit():
            loaded_uids_temp[account_name] = uid_value.strip()
        else:
            memory_logger.log(f"ERROR [Credentials]: UID inválido/faltante para '{account_name}' (Variable: {env_var_name}).", level="ERROR")
            all_uids_valid = False

    if all_uids_valid:
        config.LOADED_UIDS = loaded_uids_temp
        memory_logger.log(f"  -> UIDs validados y cargados para: {list(config.LOADED_UIDS.keys())}", level="INFO")
    else:
        config.LOADED_UIDS = {}
        memory_logger.log("ERROR Crítico [Credentials]: Faltan UIDs. Las transferencias entre cuentas fallarán.", level="ERROR")

def _find_and_load_env():
    """Función de ayuda para encontrar y cargar el archivo .env una sola vez."""
    env_path = find_dotenv(filename='.env', raise_error_if_not_found=False, usecwd=True)
    if env_path:
        load_dotenv(dotenv_path=env_path, override=True)
    else:
        memory_logger.log("Advertencia [Credentials]: archivo .env no encontrado.", level="WARN")