"""
Módulo Ensamblador de Dependencias.

v6.0 (Capital Lógico por Operación):
- Se elimina la importación y el registro de la dependencia `BalanceManager`,
  ya que la clase ha sido eliminada del sistema.

v5.0 (Refactor Connection a OOP):
- Se actualizan las importaciones del paquete 'connection' para registrar las
  clases 'ConnectionManager' y 'Ticker'.
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
        from connection import ConnectionManager, Ticker
        dependencies["ConnectionManager"] = ConnectionManager
        dependencies["Ticker"] = Ticker
        
        # --- Paquete de API de Exchange (bajo nivel) ---
        from core.api import trading as trading_api
        dependencies["trading_api"] = trading_api
        
        # --- Capa de Abstracción de Exchange ---
        from core.exchange._bybit_adapter import BybitAdapter
        dependencies["BybitAdapter"] = BybitAdapter

        # --- Componentes de Estrategia (Clases) ---
        from core.strategy.ta import TAManager
        from core.strategy.signal import SignalGenerator
        from core.strategy._event_processor import EventProcessor 
        
        dependencies["TAManager"] = TAManager
        dependencies["SignalGenerator"] = SignalGenerator
        dependencies["EventProcessor"] = EventProcessor

        # --- Controladores y sus APIs ---
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
        
        # --- INICIO DE LA MODIFICACIÓN ---
        # PositionManager (PM) y sus componentes
        # Se elimina `BalanceManager` de la importación y del diccionario de dependencias.
        from core.strategy.pm import api as pm_api
        # from core.strategy.pm import PositionManager, BalanceManager, PositionState, PositionExecutor
        from core.strategy.pm import PositionManager, PositionState, PositionExecutor
        from core.strategy.pm import _helpers as pm_helpers
        from core.strategy.pm import _calculations as pm_calculations
        dependencies["position_manager_api_module"] = pm_api
        dependencies["PositionManager"] = PositionManager
        # dependencies["BalanceManager"] = BalanceManager # Comentado/Eliminado
        dependencies["PositionState"] = PositionState
        dependencies["PositionExecutor"] = PositionExecutor
        dependencies["pm_helpers_module"] = pm_helpers
        dependencies["pm_calculations_module"] = pm_calculations
        # --- FIN DE LA MODIFICACIÓN ---

        print("Diccionario de dependencias ensamblado con éxito.")
        return dependencies

    except ImportError as e:
        # Un error de importación aquí es fatal y debe detener el bot.
        print(f"\n!!! ERROR FATAL: No se pudo importar una dependencia esencial: {e} !!!")
        import traceback
        traceback.print_exc()
        # Devolvemos un diccionario vacío para que el lanzador principal falle limpiamente.
        return {}