# =============== INICIO ARCHIVO: main.py (MODIFICADO) ===============
"""
Punto de Entrada Principal del Bot de Trading (v18.0 - Arquitectura Limpia).

Este archivo es el lanzador de la aplicación. Utiliza la librería `click`
a través del nuevo paquete `core.menu` para gestionar los modos de operación.

v18.0:
- Refactorizado para usar el nuevo paquete `core.menu` para toda la lógica de UI.
- La importación de la CLI ahora apunta al nuevo paquete.
- Modificado para presentar un menú de selección al ejecutar sin argumentos.
"""
import sys
import time
import traceback
import os

# --- Importaciones de Configuración y Utilidades ---
try:
    import config
    from core import utils
    # La CLI se importa desde el paquete `core.menu`
    from core.menu import main_cli
except ImportError as e:
    print(f"ERROR CRÍTICO: No se pudo importar un módulo de configuración esencial: {e}")
    sys.exit(1)

# --- Importaciones de Componentes Core y Strategy ---
try:
    from core import live_operations
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
        
        try:
            from core import menu as menu_package_ref
        except ImportError:
            menu_package_ref = None

        # Selecciona el runner apropiado y le pasa todas las dependencias.
        if mode == "live_interactive":
            live_interactive_runner.run_live_interactive_mode(
                final_summary=final_summary,
                operation_mode=mode,
                config_module=config,
                utils_module=utils,
                menu_module=menu_package_ref,
                live_operations_module=live_operations,
                position_manager_module=position_manager,
                balance_manager_module=balance_manager,
                position_state_module=position_state,
                open_snapshot_logger_module=open_snapshot_logger,
                event_processor_module=event_processor,
                ta_manager_module=ta_manager
            )
        elif mode == "backtest_interactive":
            backtest_runner.run_backtest_mode(
                final_summary=final_summary,
                operation_mode=mode,
                config_module=config,
                utils_module=utils,
                menu_module=menu_package_ref,
                position_manager_module=position_manager,
                event_processor_module=event_processor,
                open_snapshot_logger_module=open_snapshot_logger,
                results_reporter_module=results_reporter,
                balance_manager_module=balance_manager,
                position_state_module=position_state,
                ta_manager_module=ta_manager
            )
        elif mode == "automatic":
            automatic_runner.run_automatic_mode(
                final_summary=final_summary,
                operation_mode=mode,
                config_module=config,
                utils_module=utils,
                menu_module=menu_package_ref,
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
                menu_module=menu_package_ref,
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
        os._exit(0)

# <<< INICIO DE LA MODIFICACIÓN: Bloque de ejecución principal >>>
if __name__ == "__main__":
    # Si se pasan argumentos en la línea de comandos (ej: python main.py live),
    # se usa la CLI de Click como antes.
    if len(sys.argv) > 1:
        if main_cli:
            main_cli()
        else:
            print("ERROR CRITICO: La interfaz de línea de comandos (main_cli) no pudo ser cargada.")
    else:
        # Si NO se pasan argumentos, se muestra un menú de selección de modo.
        try:
            from simple_term_menu import TerminalMenu
            from core.menu._helpers import clear_screen, print_tui_header, MENU_STYLE

            clear_screen()
            print_tui_header("Bienvenido al Asistente de Trading")

            menu_items = [
                "[1] Iniciar en Modo Live Interactivo",
                None,
                "[2] Modo Backtest (No funcional)",
                "[3] Modo Automático (No funcional)",
                None,
                "[4] Salir"
            ]
            terminal_menu = TerminalMenu(
                menu_items,
                title="Por favor, selecciona un modo de operación:",
                **MENU_STYLE
            )
            choice_index = terminal_menu.show()

            if choice_index == 0:
                # El usuario seleccionó Iniciar en Modo Live
                run_selected_mode("live_interactive")
            elif choice_index in [2, 3]:
                # Opciones no funcionales
                clear_screen()
                print("\nEsta opción no está habilitada en la versión actual.")
                print("El programa se cerrará.")
                time.sleep(3)
                sys.exit(0)
            else:
                # El usuario seleccionó Salir o presionó ESC
                print("\nSaliendo del programa.")
                sys.exit(0)

        except ImportError:
            print("ERROR: 'simple-term-menu' no está instalado. No se puede mostrar el menú.")
            print("Por favor, ejecuta 'pip install simple-term-menu' o inicia con un argumento, ej: 'python main.py live'")
            sys.exit(1)
# <<< FIN DE LA MODIFICACIÓN >>>

# =============== FIN ARCHIVO: main.py (MODIFICADO) ===============