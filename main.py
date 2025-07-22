# main.py

"""
Punto de Entrada Principal del Bot de Trading.

Este archivo es el lanzador de la aplicación. Su responsabilidad es:
1. Importar todos los componentes y dependencias necesarios del bot.
2. Inyectar estas dependencias en el orquestador principal de la TUI.
3. Ceder el control total del ciclo de vida de la aplicación al paquete 'core.menu'.
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
    # --- INICIO DE LA SOLUCIÓN ---
    # Se importa 'launch_bot' que es la única función necesaria.
    # La importación de '__init__LEGACY' se elimina por ser incorrecta y obsoleta.
    from core.menu import launch_bot
    # --- FIN DE LA SOLUCIÓN ---
    
    # Paquete de la API
    from core import api as live_operations
    
    # Paquete de Logging
    from core.logging import open_position_logger, closed_position_logger, signal_logger, memory_logger
    
    # Componentes de Estrategia
    from core.strategy import pm as position_manager
    from core.strategy import ta
    from core.strategy import event_processor
    
    # Módulos internos del PM para inyección de dependencias
    from core.strategy.pm import _balance as balance_manager
    from core.strategy.pm import _position_state as position_state
    from core.strategy.pm import _helpers as position_helpers
    from core.strategy.pm import _calculations as position_calculations
    from core.strategy.pm._executor import PositionExecutor

    # Paquete de Conexión
    from connection import manager as connection_manager
    from connection import ticker as connection_ticker
    
    # Paquete Runner
    from runner import initialize_bot_backend, shutdown_bot_backend

except ImportError as e:
    print("="*80)
    print("!!! ERROR CRÍTICO DE IMPORTACIÓN !!!")
    print(f"No se pudo importar un módulo esencial: {e}")
    print("Asegúrate de haber instalado todas las dependencias (pip install -r requirements.txt)")
    print("y de que la estructura de directorios del proyecto es correcta.")
    print("="*80)
    traceback.print_exc()
    sys.exit(1)


# --- Punto de Entrada Principal ---
if __name__ == "__main__":
    """
    Ensambla el diccionario de dependencias y lanza el controlador principal de la TUI.
    """
    
    # 1. Crear un diccionario que contenga todos los módulos y componentes importados.
    dependencies = {
        # Módulos base
        "config": config,
        "utils": utils,
        
        # Módulos de bajo nivel
        "connection_manager": connection_manager,
        "connection_ticker": connection_ticker,
        "live_operations": live_operations,
        
        # Módulos de logging
        "memory_logger": memory_logger,
        "open_snapshot_logger": open_position_logger,
        "closed_position_logger": closed_position_logger,
        "signal_logger": signal_logger,
        
        # Módulos de estrategia y PM
        "position_manager": position_manager,
        "ta_manager": ta,
        "event_processor": event_processor,
        
        # Módulos internos del PM (para inyección más profunda)
        "pm_balance_manager": balance_manager,
        "pm_position_state": position_state,
        "pm_helpers": position_helpers,
        "pm_calculations": position_calculations,
        "pm_executor_class": PositionExecutor,

        # Funciones del Runner
        "initialize_bot_backend": initialize_bot_backend,
        "shutdown_bot_backend": shutdown_bot_backend,
    }

    try:
        # 2. Ceder el control total al lanzador del menú, inyectando todas las dependencias.
        # El módulo 'menu' no se pasa como dependencia porque es el que está controlando el flujo.
        launch_bot(dependencies)
    except Exception as e:
        # Captura de errores catastróficos que puedan ocurrir antes de que el menú se inicie
        print("\n" + "="*80)
        print("!!! ERROR FATAL EN EL LANZADOR PRINCIPAL !!!")
        print(f"  Tipo de Error: {type(e).__name__}")
        print(f"  Mensaje: {e}")
        print("-" * 80)
        traceback.print_exc()
        print("=" * 80)
        print("El bot no pudo iniciarse. Saliendo.")
        sys.exit(1)