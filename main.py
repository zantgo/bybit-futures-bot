# main.py

"""
Punto de Entrada Principal del Bot de Trading.

Este archivo es el lanzador de la aplicación. Su responsabilidad es:
1. Importar todos los componentes necesarios del bot.
2. Llamar al lanzador del menú para iniciar el bot.
3. Orquestar la ejecución del modo de operación, inyectando las dependencias.
"""
import sys
import time
import traceback
import os

# --- INICIO DE CAMBIOS: Importaciones Adaptadas y Limpieza ---

# --- Importaciones de Configuración y Utilidades ---
try:
    import config
    from core import utils
    # --- CORRECCIÓN CLAVE ---
    # Importamos el paquete 'menu' en sí mismo y la función 'launch_bot'.
    from core import menu
    from core.menu import launch_bot
except ImportError as e:
    print(f"ERROR CRÍTICO: No se pudo importar un módulo de configuración esencial: {e}")
    sys.exit(1)

# --- Importaciones de Componentes Core y Strategy ---
try:
    # Paquetes refactorizados con sus nuevas rutas
    from core import api as live_operations
    from core.logging import open_position_logger as open_snapshot_logger
    from core.strategy import pm as position_manager
    from core.strategy import ta
    from core.strategy import event_processor
    
    # Módulos internos del PM (necesarios para la inyección de dependencias)
    from core.strategy.pm import _balance as balance_manager
    from core.strategy.pm import _position_state as position_state
    from core.strategy.pm import _helpers as position_helpers

except ImportError as e:
    print(f"ERROR CRÍTICO: No se pudo importar un componente CORE o STRATEGY: {e}")
    traceback.print_exc()
    sys.exit(1)

# --- Importaciones de Conexión ---
try:
    from connection import manager as connection_manager
    from connection import ticker as connection_ticker
    
except ImportError as e:
    print(f"ERROR CRÍTICO: No se pudo importar un módulo de CONEXIÓN: {e}")
    sys.exit(1)

# --- Importación de Runner ---
try:
    from runner import run_live_interactive_mode
except ImportError as e:
    print(f"ERROR CRÍTICO: No se pudo importar el RUNNER: {e}")
    sys.exit(1)

# --- FIN DE CAMBIOS: Importaciones Adaptadas y Limpieza ---


def run_selected_mode(mode: str):
    """
    Función central que es llamada para ejecutar el modo de operación
    correspondiente, inyectando todas las dependencias.
    """
    final_summary = {}

    try:
        config.print_initial_config(operation_mode=mode)
        
        position_helpers.set_config_dependency(config)
        position_helpers.set_utils_dependency(utils)
        position_helpers.set_live_operations_dependency(live_operations)
        
        print("\nInicializando conexiones en vivo...")
        connection_manager.initialize_all_clients()
        if not connection_manager.get_initialized_accounts():
            print("ERROR CRITICO: No se pudo inicializar ninguna cuenta API. Saliendo.")
            return

        # Selecciona el runner apropiado y le pasa todas las dependencias.
        if mode == "live_interactive":
            run_live_interactive_mode(
                final_summary=final_summary,
                operation_mode=mode,
                config_module=config,
                utils_module=utils,
                # --- CORRECCIÓN CLAVE ---
                # Pasamos el paquete 'menu' completo como dependencia.
                menu_module=menu,
                live_operations_module=live_operations,
                position_manager_module=position_manager,
                balance_manager_module=balance_manager,
                position_state_module=position_state,
                open_snapshot_logger_module=open_snapshot_logger,
                event_processor_module=event_processor,
                ta_manager_module=ta
            )
        else:
            print(f"Error: Modo '{mode}' no reconocido.")

    except KeyboardInterrupt:
        print("\n\nINFO: Proceso interrumpido por el usuario (Ctrl+C). Saliendo de forma ordenada.")
    except Exception as e:
        print("\n" + "="*80)
        print("!!! ERROR CRÍTICO INESPERADO EN LA EJECUCIÓN PRINCIPAL !!!")
        print(f"  Tipo de Error: {type(e).__name__}")
        print(f"  Mensaje: {e}")
        print("-" * 80)
        traceback.print_exc()
        print("=" * 80)
        print("El bot ha encontrado un error fatal y se detendrá.")
    finally:
        print("\n[main] La ejecución ha finalizado.")
        os._exit(0)


if __name__ == "__main__":
    # En esta versión refactorizada, el bot siempre se inicia directamente
    # en modo live interactivo llamando a la función de lanzamiento.
    launch_bot()