# =============== INICIO ARCHIVO: main.py (CORREGIDO Y ABSOLUTAMENTE COMPLETO) ===============
"""
Punto de Entrada Principal del Bot de Trading (v18.0 - Arquitectura Limpia).

Este archivo es el lanzador de la aplicación. Utiliza la librería `click`
a través del módulo `core.menu` para gestionar los modos de operación.

v18.0:
- Eliminado el archivo puente `live/live_runner.py`.
- `main.py` ahora llama directamente a `runners/live_interactive_runner.py`
  para el modo interactivo, simplificando el flujo de ejecución.

Uso:
- python main.py live: Inicia el modo Live Interactivo.
- python main.py backtest: Inicia el modo Backtest Interactivo.
- python main.py auto: Inicia el modo Automático en vivo.
- python main.py backtest-auto: Inicia el modo Backtest Automático.
- python main.py --help: Muestra todos los comandos disponibles.
"""
import sys
import traceback
import os

# --- Importaciones de Configuración y Utilidades ---
try:
    import config
    from core import utils
    from core.menu import main_cli
except ImportError as e:
    print(f"ERROR CRÍTICO: No se pudo importar un módulo de configuración esencial: {e}")
    sys.exit(1)

# --- Importaciones de Componentes Core y Strategy ---
try:
    from core import live_operations
    # La corrección del alias se mantiene para consistencia
    from core.logging import signal_logger, closed_position_logger, open_position_snapshot_logger as open_snapshot_logger
    from core.reporting import results_reporter
    from core.visualization import plotter
    from core.strategy import (
        pm_facade as position_manager,
        balance_manager,
        position_state,
        event_processor,
        ta_manager,
        market_regime_controller,
        _position_helpers,
        position_calculations
    )
except ImportError as e:
    print(f"ERROR CRÍTICO: No se pudo importar un componente CORE o STRATEGY: {e}")
    sys.exit(1)

# --- Importaciones de Conexión (Live/Backtest) ---
try:
    from live.connection import manager as live_connection_manager
    from live.connection import ticker as connection_ticker
    from backtest.connection import data_feeder
except ImportError as e:
    print(f"ERROR CRÍTICO: No se pudo importar un módulo de CONEXIÓN: {e}")
    sys.exit(1)

# --- Importaciones de Runners (Orquestadores de modo) ---
try:
    # from live import live_runner  # <<< LÍNEA ELIMINADA SEGÚN INSTRUCCIONES >>>
    from runners import live_interactive_runner, automatic_runner, automatic_backtest_runner
    from backtest import backtest_runner
except ImportError as e:
    print(f"ERROR CRÍTICO: No se pudo importar un módulo RUNNER: {e}")
    sys.exit(1)

def run_selected_mode(mode: str):
    """
    Función central que es llamada por los comandos de la CLI para ejecutar
    el modo de operación correspondiente, inyectando todas las dependencias.
    """
    final_summary = {}

    try:
        config.print_initial_config(operation_mode=mode)
        
        # Inyectar dependencias a _position_helpers (se usa en muchos sitios)
        _position_helpers.set_config_dependency(config)
        _position_helpers.set_utils_dependency(utils)
        _position_helpers.set_live_operations_dependency(live_operations)
        
        # --- Pre-Start para modos LIVE ---
        is_live_mode = mode.startswith("live") or mode == "automatic"
        if is_live_mode:
            print("\nInicializando conexiones en vivo...")
            live_connection_manager.initialize_all_clients()
            if not live_connection_manager.get_initialized_accounts():
                print("ERROR CRITICO: No se pudo inicializar ninguna cuenta API. Saliendo.")
                return

        # Selecciona el runner apropiado y le pasa todas las dependencias.
        if mode == "live_interactive":
            # <<< MODIFICACIÓN DE LA LLAMADA SEGÚN INSTRUCCIONES >>>
            live_interactive_runner.run_live_interactive_mode(
                final_summary=final_summary,
                operation_mode=mode,
                config_module=config,
                utils_module=utils,
                menu_module=sys.modules.get('core.menu'),
                live_operations_module=live_operations,
                position_manager_module=position_manager,
                balance_manager_module=balance_manager,
                position_state_module=position_state,
                open_snapshot_logger_module=open_snapshot_logger,
                event_processor_module=event_processor,
                ta_manager_module=ta_manager
            )
        elif mode == "backtest_interactive":
            # El runner de backtest interactivo no fue proporcionado, así que asumimos que es el backtest_runner general.
            # Si tienes un archivo específico, ajusta el nombre de la función aquí.
            backtest_runner.run_backtest_mode(
                final_summary=final_summary,
                operation_mode=mode,
                config_module=config,
                utils_module=utils,
                menu_module=sys.modules.get('core.menu'),
                position_manager_module=position_manager,
                event_processor_module=event_processor,
                open_snapshot_logger_module=open_snapshot_logger,
                results_reporter_module=results_reporter,
                balance_manager_module=balance_manager,
                position_state_module=position_state,
                ta_manager_module=ta_manager,
                plotter_module=plotter # Añadido para que el reporte pueda llamar al plotter
            )
        elif mode == "automatic":
            automatic_runner.run_automatic_mode(
                final_summary=final_summary,
                operation_mode=mode,
                config_module=config,
                utils_module=utils,
                menu_module=sys.modules.get('core.menu'),
                live_operations_module=live_operations,
                position_manager_module=position_manager,
                balance_manager_module=balance_manager,
                position_state_module=position_state,
                open_snapshot_logger_module=open_snapshot_logger,
                event_processor_module=event_processor,
                ta_manager_module=ta_manager,
                market_regime_controller_module=market_regime_controller,
                connection_ticker_module=connection_ticker,
                plotter_module=plotter,
                results_reporter_module=results_reporter
            )
        elif mode == "automatic_backtest":
            automatic_backtest_runner.run_automatic_backtest_mode(
                final_summary=final_summary,
                operation_mode=mode,
                config_module=config,
                utils_module=utils,
                menu_module=sys.modules.get('core.menu'),
                position_manager_module=position_manager,
                balance_manager_module=balance_manager,
                position_state_module=position_state,
                event_processor_module=event_processor,
                ta_manager_module=ta_manager,
                market_regime_controller_module=market_regime_controller,
                open_snapshot_logger_module=open_snapshot_logger,
                results_reporter_module=results_reporter,
                data_feeder_module=data_feeder,
                plotter_module=plotter
            )
        else:
            print(f"Error: Modo '{mode}' no reconocido. Usa --help para ver las opciones.")

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
        # Usamos os._exit(0) para forzar la salida y terminar los hilos daemon.
        # sys.exit(0) a veces puede dejar hilos colgados.
        os._exit(0)

if __name__ == "__main__":
    # Este es el punto de entrada real de la aplicación.
    # Llama al grupo de comandos 'main_cli' definido en `core/menu.py`.
    # Click se encargará de parsear los argumentos de la línea de comandos
    # y llamar a la función de comando correspondiente (ej: run_live_interactive_command),
    # la cual a su vez llama a nuestra función `run_selected_mode` con el modo correcto.
    main_cli()
# =============== FIN ARCHIVO: main.py (CORREGIDO Y ABSOLUTAMENTE COMPLETO) ===============