"""
Módulo Ensamblador de Dependencias.

v4.0 (Arquitectura de Controladores):
- Este módulo ya no es responsable de la inicialización de los componentes.
- Su única responsabilidad ahora es importar todas las clases y módulos del
  sistema y ensamblarlos en un único diccionario de dependencias.
- Este diccionario se inyecta en los controladores de alto nivel (como el
  BotController), que son los que realmente gestionan la instanciación y el
  ciclo de vida de los objetos.
"""
from typing import Dict, Any

def assemble_dependencies() -> Dict[str, Any]:
    """
    Importa y ensambla todas las clases y módulos del sistema en un diccionario
    para su posterior inyección en los controladores.

    No instancia ningún objeto, solo provee las "plantillas" (clases) y los
    módulos de soporte.
    """
    print("Ensamblando diccionario de dependencias del sistema...")
    
    dependencies = {}
    
    try:
        # --- Módulos Base y Utilidades ---
        import config
        from core import utils
        dependencies["config_module"] = config
        dependencies["utils_module"] = utils

        # --- Paquete de Logging ---
        from core import logging as logging_package
        from core.logging import memory_logger, open_position_logger, closed_position_logger, signal_logger
        dependencies["logging_package"] = logging_package
        dependencies["memory_logger_module"] = memory_logger
        dependencies["open_snapshot_logger_module"] = open_position_logger
        dependencies["closed_position_logger_module"] = closed_position_logger
        dependencies["signal_logger_module"] = signal_logger

        # --- Paquete de Conexión ---
        from connection import manager as connection_manager
        from connection import ticker as connection_ticker
        dependencies["connection_manager_module"] = connection_manager
        dependencies["connection_ticker_module"] = connection_ticker
        
        # --- Paquete de API de Exchange (bajo nivel) ---
        from core.api import trading as trading_api
        dependencies["trading_api"] = trading_api
        
        # --- Capa de Abstracción de Exchange ---
        from core.exchange._bybit_adapter import BybitAdapter
        dependencies["BybitAdapter"] = BybitAdapter

        # --- Componentes de Estrategia (TA, Señal, Procesador) ---
        from core.strategy import ta, signal, event_processor
        dependencies["ta_manager_module"] = ta
        dependencies["signal_generator_module"] = signal
        dependencies["event_processor_module"] = event_processor

        # --- NUEVOS CONTROLADORES Y SUS APIs ---
        # BotController
        from core.bot_controller import api as bc_api
        from core.bot_controller._manager import BotController
        dependencies["bot_controller_api_module"] = bc_api
        dependencies["BotController"] = BotController

        # SessionManager
        from core.strategy.sm import api as sm_api
        from core.strategy.sm._manager import SessionManager
        dependencies["session_manager_api_module"] = sm_api
        dependencies["SessionManager"] = SessionManager

        # --- Componentes de Gestión (OM y PM) ---
        # OperationManager (OM)
        from core.strategy.om import api as om_api
        from core.strategy.om._manager import OperationManager
        dependencies["operation_manager_api_module"] = om_api
        dependencies["OperationManager"] = OperationManager
        
        # PositionManager (PM) y sus componentes
        from core.strategy.pm import api as pm_api
        from core.strategy.pm import PositionManager, BalanceManager, PositionState, PositionExecutor
        from core.strategy.pm import _helpers as pm_helpers
        from core.strategy.pm import _calculations as pm_calculations
        dependencies["position_manager_api_module"] = pm_api
        dependencies["PositionManager"] = PositionManager
        dependencies["BalanceManager"] = BalanceManager
        dependencies["PositionState"] = PositionState
        dependencies["PositionExecutor"] = PositionExecutor
        dependencies["pm_helpers_module"] = pm_helpers
        dependencies["pm_calculations_module"] = pm_calculations

        print("Diccionario de dependencias ensamblado con éxito.")
        return dependencies

    except ImportError as e:
        # Un error de importación aquí es fatal y debe detener el bot.
        print(f"\n!!! ERROR FATAL: No se pudo importar una dependencia esencial: {e} !!!")
        import traceback
        traceback.print_exc()
        # Devolvemos un diccionario vacío para que el lanzador principal falle limpiamente.
        return {}