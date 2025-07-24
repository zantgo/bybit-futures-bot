"""
Punto de Entrada Principal del Bot de Trading.

Este archivo es el lanzador de la aplicación. Su responsabilidad es:
1. Importar todos los componentes y dependencias necesarios del bot.
2. Ensamblar un diccionario de dependencias (Clases y Módulos).
3. Inyectar estas dependencias en el orquestador principal (la TUI).
4. Ceder el control total del ciclo de vida de la aplicación al paquete 'core.menu'.
"""
import sys
import os
import traceback

# --- Importaciones de Componentes y Dependencias ---
try:
    # Configuración y Utilidades
    import config
    from core import utils
    
    # Paquete del Menú (TUI)
    from core.menu import launch_bot
    
    # Paquete de la API (capa de bajo nivel para Bybit)
    from core import api as live_operations
    
    # Paquete de Logging
    from core import logging as logging_package
    from core.logging import open_position_logger, closed_position_logger, signal_logger, memory_logger
    
    # Componentes de Estrategia
    from core.strategy import ta
    from core.strategy import event_processor
    
    # Clases y Módulos del PM refactorizado
    from core.strategy.pm import api as pm_api_module
    from core.strategy.pm import PositionManager, BalanceManager, PositionState, PositionExecutor
    from core.strategy.pm import _helpers as pm_helpers_module
    from core.strategy.pm import _calculations as pm_calculations_module

    # Paquete de Conexión
    from connection import manager as connection_manager
    from connection import ticker as connection_ticker
    
    # Paquete Runner
    from runner import initialize_bot_backend, shutdown_bot_backend
    
    # Capa de Abstracción de Exchange
    from core.exchange import AbstractExchange
    from core.exchange._bybit_adapter import BybitAdapter

except ImportError as e:
    print("="*80)
    print("!!! ERROR CRÍTICO DE IMPORTACIÓN !!!")
    print(f"No se pudo importar un módulo esencial: {e}")
    traceback.print_exc()
    sys.exit(1)


# --- Punto de Entrada Principal ---
if __name__ == "__main__":
    """
    Ensambla el diccionario de dependencias y lanza el controlador principal de la TUI.
    """
    
    # Inicializar el sistema de logging asíncrono de archivos ANTES que cualquier otra cosa.
    logging_package.initialize_loggers()

    dependencies = {
        # Módulos base
        "config_module": config,
        "utils_module": utils,
        
        # Módulos de bajo nivel (API y Conexión)
        "connection_manager_module": connection_manager,
        "connection_ticker_module": connection_ticker,
        "live_operations_module": live_operations,
        
        # --- INICIO DE LA MODIFICACIÓN ---
        # Módulos de logging (se añade el paquete completo para el apagado)
        "logging_package": logging_package,
        # --- FIN DE LA MODIFICACIÓN ---
        "memory_logger_module": memory_logger,
        "open_snapshot_logger_module": open_position_logger,
        "closed_position_logger_module": closed_position_logger,
        "signal_logger_module": signal_logger,
        
        # Módulos de estrategia (los que no son del PM)
        "ta_manager_module": ta,
        "event_processor_module": event_processor,
        
        # Fachada de la API del PM (para la TUI y otros consumidores)
        "position_manager_api_module": pm_api_module,
        
        # Clases del PM (para que el runner las instancie)
        "PositionManager": PositionManager,
        "BalanceManager": BalanceManager,
        "PositionState": PositionState,
        "PositionExecutor": PositionExecutor,
        
        # Módulos de soporte del PM
        "pm_helpers_module": pm_helpers_module,
        "pm_calculations_module": pm_calculations_module,

        # Funciones del Runner
        "initialize_bot_backend": initialize_bot_backend,
        "shutdown_bot_backend": shutdown_bot_backend,

        # Clases de la capa de Exchange
        "AbstractExchange": AbstractExchange,
        "BybitAdapter": BybitAdapter,
    }

    try:
        # Ceder el control total al lanzador del menú, inyectando todas las dependencias.
        launch_bot(dependencies)
    except Exception as e:
        print("\n" + "="*80)
        print("!!! ERROR FATAL EN EL LANZADOR PRINCIPAL !!!")
        print(f"  Tipo de Error: {type(e).__name__}")
        print(f"  Mensaje: {e}")
        print("-" * 80)
        traceback.print_exc()
        print("=" * 80)
        print("El bot no pudo iniciarse. Saliendo.")
        sys.exit(1)