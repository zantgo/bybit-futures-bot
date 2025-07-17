# =============== INICIO ARCHIVO: main.py (v13.3 - Llamadas a Runner Corregidas Completamente) ===============
"""
Punto de entrada principal.

v13.3:
- CORREGIDO: Añadidos todos los módulos de dependencia que faltaban en las llamadas a
  `automatic_runner.run_automatic_mode` y `automatic_backtest_runner.run_automatic_backtest_mode`
  para solucionar los `NameError` y `TypeError`.
v13.1:
- Añadido el "Modo Automático (Backtest)" como opción en el menú principal.
"""
import sys
import os
import traceback
import time
import json
from typing import Optional, Dict, Any, List, Tuple
from dotenv import load_dotenv, find_dotenv
import config

# --- Añadir raíz del proyecto ---
try:
    project_root = os.path.dirname(os.path.abspath(__file__))
except NameError:
    project_root = os.path.abspath(os.path.join(os.getcwd()))
    print(f"WARN [main]: __file__ no definido, usando CWD como base para PROJECT_ROOT: {project_root}")

# --- Módulos Core y de Soporte (se inicializan como None) ---
utils = None
menu = None
ta_manager = None
event_processor = None
position_manager = None
balance_manager = None
position_state = None
open_snapshot_logger = None
results_reporter = None
live_operations = None
ut_bot_controller = None
connection_ticker = None
plotter = None
data_feeder = None

try:
    from core import utils
    from core import menu
    from core.strategy import ta_manager
    from core.strategy import event_processor
    from core.strategy import position_manager
    from core.strategy import balance_manager
    from core.strategy import position_state
    from core.strategy import ut_bot_controller
    from core.logging import open_position_snapshot_logger
    from core.reporting import results_reporter
    from core import live_operations
    from live.connection import ticker as connection_ticker
    from backtest.connection import data_feeder
    from core.visualization import plotter

except ImportError as e:
    print(f"ERROR IMPORTACIÓN CORE INICIAL: {e.name}"); traceback.print_exc(); sys.exit(1)
except Exception as e:
    print(f"ERROR FATAL Config/Import Inicial: {e}"); traceback.print_exc(); sys.exit(1)


# --- Importar los Runners ---
try:
    import live_runner
    import backtest_runner
    import automatic_runner
    import automatic_backtest_runner
except ImportError as e:
    print(f"ERROR CRITICO: No se pudieron importar los runners ({e.name})."); traceback.print_exc(); sys.exit(1)

# --- Variables Globales ---
final_summary: Dict[str, Any] = {}
operation_mode: str = "unknown"
active_ticker_module: Optional[Any] = None

# --- Bucle Principal del Menú ---
def main_loop():
    global final_summary, operation_mode, config, active_ticker_module
    global utils, menu, live_operations, position_manager, balance_manager
    global position_state, open_snapshot_logger, event_processor, ta_manager
    global results_reporter, ut_bot_controller, connection_ticker, plotter, data_feeder

    if not all([menu, config, utils]):
        print("ERROR CRITICO: Faltan módulos base (Menu, Config, Utils)."); sys.exit(1)

    if not configure_runtime_settings():
         print("\nERROR: No se pudo configurar el entorno base. Abortando."); sys.exit(1)

    print("\n[main] Inicializando clientes API de Bybit (una sola vez)...")
    try:
        from live.connection import manager as live_manager
        live_manager.initialize_all_clients()
        if not live_manager.get_initialized_accounts():
             print("[main] ADVERTENCIA: La inicialización de la API finalizó, pero no se cargó ningún cliente.")
        else:
             print(f"[main] Clientes API inicializados con éxito: {live_manager.get_initialized_accounts()}")
    except Exception as e_api:
        print(f"[main] ERROR CRITICO durante la inicialización de la API: {e_api}"); traceback.print_exc(); sys.exit(1)

    if getattr(config, 'AUTOMATIC_MODE_ENABLED', False):
        operation_mode = "automatic"
        print(f"\n--- MODO AUTOMÁTICO (LIVE) DETECTADO EN CONFIG.PY ---")
        try:
            automatic_runner.run_automatic_mode(
                final_summary=final_summary, operation_mode=operation_mode,
                config_module=config, utils_module=utils, menu_module=menu,
                live_operations_module=live_operations,
                position_manager_module=position_manager,
                balance_manager_module=balance_manager,
                position_state_module=position_state,
                open_snapshot_logger_module=open_snapshot_logger,
                event_processor_module=event_processor,
                ta_manager_module=ta_manager,
                ut_bot_controller_module=ut_bot_controller,
                connection_ticker_module=connection_ticker,
                plotter_module=plotter,
                results_reporter_module=results_reporter
            )
        except Exception as e: print(f"ERROR CRITICO en Modo Automático: {e}"); traceback.print_exc()
        return

    while True:
        choice = menu.get_main_menu_choice()

        if choice == '1':
            operation_mode = "live_interactive"
            try:
                active_ticker_module = live_runner.run_live_pre_start(
                    final_summary=final_summary, operation_mode=operation_mode,
                    config_module=config, utils_module=utils, menu_module=menu,
                    live_operations_module=live_operations,
                    position_manager_module=position_manager,
                    balance_manager_module=balance_manager,
                    position_state_module=position_state,
                    open_snapshot_logger_module=open_snapshot_logger,
                    event_processor_module=event_processor,
                    ta_manager_module=ta_manager
                )
            except Exception as e: print(f"ERROR CRITICO en Live Runner: {e}"); traceback.print_exc()
            break

        elif choice == '2':
            operation_mode = "backtest_interactive"
            try:
                backtest_runner.run_backtest_mode(
                    final_summary=final_summary, operation_mode=operation_mode,
                    config_module=config, utils_module=utils, menu_module=menu,
                    position_manager_module=position_manager,
                    event_processor_module=event_processor,
                    open_snapshot_logger_module=open_snapshot_logger,
                    results_reporter_module=results_reporter,
                    balance_manager_module=balance_manager,
                    position_state_module=position_state,
                    ta_manager_module=ta_manager
                )
            except Exception as e: print(f"ERROR CRITICO en Backtest Runner: {e}"); traceback.print_exc()
            break

        elif choice == '3':
            operation_mode = "automatic"
            try:
                automatic_runner.run_automatic_mode(
                    final_summary=final_summary, operation_mode=operation_mode,
                    config_module=config, utils_module=utils, menu_module=menu,
                    live_operations_module=live_operations,
                    position_manager_module=position_manager,
                    balance_manager_module=balance_manager,
                    position_state_module=position_state,
                    open_snapshot_logger_module=open_snapshot_logger,
                    event_processor_module=event_processor,
                    ta_manager_module=ta_manager,
                    ut_bot_controller_module=ut_bot_controller,
                    connection_ticker_module=connection_ticker,
                    plotter_module=plotter,
                    results_reporter_module=results_reporter
                )
            except Exception as e: print(f"ERROR CRITICO en Modo Automático: {e}"); traceback.print_exc()
            break

        elif choice == '4':
            operation_mode = "automatic_backtest"
            try:
                automatic_backtest_runner.run_automatic_backtest_mode(
                    final_summary=final_summary, operation_mode=operation_mode,
                    config_module=config, utils_module=utils, menu_module=menu,
                    position_manager_module=position_manager,
                    balance_manager_module=balance_manager,
                    position_state_module=position_state,
                    event_processor_module=event_processor,
                    ta_manager_module=ta_manager,
                    ut_bot_controller_module=ut_bot_controller,
                    open_snapshot_logger_module=open_snapshot_logger,
                    results_reporter_module=results_reporter,
                    data_feeder_module=data_feeder,
                    plotter_module=plotter
                )
            except Exception as e:
                 print(f"ERROR CRITICO durante ejecución de Backtest Automático: {e}")
                 traceback.print_exc()
            break

        elif choice == '0':
            operation_mode = "exit"; break
        else:
            print("Opción no válida."); time.sleep(1)

def configure_runtime_settings() -> bool:
    global config
    try:
        env_path = find_dotenv(raise_error_if_not_found=False, usecwd=True)
        if env_path:
            load_dotenv(dotenv_path=env_path, verbose=False, override=True)
            print(f"INFO: .env cargado desde: {env_path}")
        else:
            print("INFO: Archivo .env no encontrado.")
    except Exception as e:
        print(f"Error buscando o cargando .env: {e}")
    if not config: print("ERROR CRITICO: Objeto config no cargado/importado."); return False
    return True

if __name__ == "__main__":
    try:
        main_loop()
    except (SystemExit, KeyboardInterrupt):
        print("\n\nSaliendo del programa (Interrupción Detectada).")
    except Exception as e:
        print(f"\nERROR FATAL INESPERADO (Nivel Superior main.py): {e}")
        traceback.print_exc()
    finally:
        print("\n--- Ejecución Finalizada ---")
        if active_ticker_module and hasattr(active_ticker_module, 'stop_ticker_thread'):
            try: active_ticker_module.stop_ticker_thread()
            except Exception: pass

        pm_enabled_final = getattr(config, 'POSITION_MANAGEMENT_ENABLED', False) if config else False
        if position_manager and pm_enabled_final and results_reporter and final_summary and 'error' not in final_summary:
             print("Generando/Sobrescribiendo reporte final...")
             try:
                 results_reporter.generate_report(final_summary, operation_mode)
             except Exception as report_err:
                 print(f"  ERROR generando reporte final: {report_err}")
        print("\nPrograma terminado.")

# =============== FIN ARCHIVO: main.py (v13.3 - Llamadas a Runner Corregidas Completamente) ===============
