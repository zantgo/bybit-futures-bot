# =============== INICIO ARCHIVO: main.py (v13 - CORRECCIÓN FINAL Y DEFINITIVA) ===============
"""
Punto de entrada principal (v13).
Selección de modo (Live/Backtest/Automático), configuración inicial base, y orquesta la ejecución.

v13:
- Añade el modo "Automático" como un flujo de ejecución principal.
- Si config.AUTOMATIC_MODE_ENABLED es True, se salta el menú y se ejecuta directamente.
- Si es False, se añade como una opción en el menú principal.
- Importa y pasa las nuevas dependencias (ut_bot_controller, connection_ticker) a los runners.
"""
import sys
import os
import traceback
import time
import json
from typing import Optional, Dict, Any, List, Tuple
from dotenv import load_dotenv, find_dotenv
# Importar config directamente ya que está en la raíz
import config # Este es el módulo config global

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
# --- Nuevas dependencias a importar ---
ut_bot_controller = None
connection_ticker = None

try:
    from core import utils
    from core import menu
    from core.strategy import ta_manager
    from core.strategy import event_processor

    if getattr(config, 'POSITION_MANAGEMENT_ENABLED', False):
        try: from core.strategy import position_manager as pm_mod; position_manager = pm_mod
        except ImportError as e: print(f"WARN: No se pudo cargar Position Manager. Error: {e}")

        try: from core.strategy import balance_manager as bm_mod; balance_manager = bm_mod
        except ImportError as e: print(f"WARN: No se pudo cargar Balance Manager. Error: {e}")

        try: from core.strategy import position_state as ps_mod; position_state = ps_mod
        except ImportError as e: print(f"WARN: No se pudo cargar Position State. Error: {e}")

        # Importar el nuevo controlador UT Bot, necesario para el modo automático
        try: from core.strategy import ut_bot_controller as utb_mod; ut_bot_controller = utb_mod
        except ImportError as e: print(f"WARN: No se pudo cargar UT Bot Controller. Error: {e}")

        if getattr(config, 'POSITION_LOG_OPEN_SNAPSHOT', False):
            try: from core.logging import open_position_snapshot_logger as opsl_mod; open_snapshot_logger = opsl_mod
            except ImportError: print("WARN: No se pudo cargar Open Snapshot Logger.")
        try: from core.reporting import results_reporter as rr_mod; results_reporter = rr_mod
        except ImportError: print("WARN: No se pudo cargar Results Reporter.")

    # Live operations y ticker son necesarios para live y automatic
    try: from core import live_operations as lo_mod; live_operations = lo_mod
    except ImportError: print("WARN: No se pudo cargar Live Operations.")
    try: from live.connection import ticker as ct_mod; connection_ticker = ct_mod
    except ImportError: print("WARN: No se pudo cargar Connection Ticker.")

except ImportError as e:
    print(f"ERROR IMPORTACIÓN CORE INICIAL: {e.name}"); traceback.print_exc(); sys.exit(1)
except Exception as e:
    print(f"ERROR FATAL Config/Import Inicial: {e}"); traceback.print_exc(); sys.exit(1)


# --- Importar los Runners ---
try:
    import live_runner
    import backtest_runner
    # Importar el nuevo runner automático
    import automatic_runner
except ImportError as e:
    print(f"ERROR CRITICO: No se pudieron importar los runners ({e.name})."); traceback.print_exc(); sys.exit(1)

# --- Variables Globales ---
final_summary: Dict[str, Any] = {}
operation_mode: str = "unknown"
active_ticker_module: Optional[Any] = None # Se asignará connection_ticker

# --- Bucle Principal del Menú ---
def main_loop():
    global final_summary, operation_mode, config, active_ticker_module
    global utils, menu, live_operations, position_manager, balance_manager
    global position_state, open_snapshot_logger, event_processor, ta_manager
    global results_reporter, ut_bot_controller, connection_ticker

    # Verificar dependencias críticas
    if not all([menu, config, utils]):
        print("ERROR CRITICO: Faltan módulos base (Menu, Config, Utils)."); sys.exit(1)

    print("\nConfigurando entorno base...")
    if not configure_runtime_settings():
         print("\nERROR: No se pudo configurar el entorno base. Abortando."); sys.exit(1)

    # ### INICIO DE LA CORRECCIÓN DEFINITIVA ###
    # La inicialización de la API se hace UNA SOLA VEZ aquí, antes de cualquier selección de modo.
    print("\n[main] Inicializando clientes API de Bybit (una sola vez)...")
    try:
        from live.connection import manager as live_manager
        live_manager.initialize_all_clients()
        
        # Después de la inicialización, verificamos si realmente se cargó algo.
        # El propio `manager` ya imprime los errores, aquí solo confirmamos el resultado.
        if not live_manager.get_initialized_accounts():
             print("[main] ADVERTENCIA: La inicialización de la API finalizó, pero no se cargó ningún cliente.")
             print("[main] Los modos Live y Automático probablemente fallarán. Verifica tu archivo .env")
        else:
             print(f"[main] Clientes API inicializados con éxito: {live_manager.get_initialized_accounts()}")
    except Exception as e_api:
        print(f"[main] ERROR CRITICO durante la inicialización de la API: {e_api}")
        traceback.print_exc()
        sys.exit(1)
    # ### FIN DE LA CORRECCIÓN DEFINITIVA ###

    # --- FLUJO DE EJECUCIÓN ---
    # Si el modo automático está activado en config, se ejecuta directamente.
    if getattr(config, 'AUTOMATIC_MODE_ENABLED', False):
        operation_mode = "automatic"
        print(f"\n--- MODO AUTOMÁTICO DETECTADO EN CONFIG.PY ---")
        print("Iniciando directamente el runner automático...")
        
        if not all([automatic_runner, ut_bot_controller, connection_ticker]):
            print("ERROR CRITICO: Faltan dependencias para el Modo Automático (automatic_runner, ut_bot_controller, connection_ticker).")
            sys.exit(1)
            
        try:
            active_ticker_module = connection_ticker
            automatic_runner.run_automatic_mode(
                final_summary=final_summary,
                operation_mode=operation_mode,
                config_module=config,
                utils_module=utils,
                menu_module=menu,
                live_operations_module=live_operations,
                position_manager_module=position_manager,
                balance_manager_module=balance_manager,
                position_state_module=position_state,
                open_snapshot_logger_module=open_snapshot_logger,
                event_processor_module=event_processor,
                ta_manager_module=ta_manager,
                ut_bot_controller_module=ut_bot_controller,
                connection_ticker_module=connection_ticker
            )
            print("\nSaliendo del Modo Automático.")
        except Exception as e_auto_run:
            print(f"ERROR CRITICO durante ejecución del Modo Automático: {e_auto_run}")
            traceback.print_exc()
        return # Termina la ejecución después del modo automático

    # Si el modo automático no está activado, muestra el menú principal.
    while True:
        choice = menu.get_main_menu_choice() # El menú ahora debería mostrar la opción 'Automático'

        if choice == '1': # Modo Live Interactivo
            operation_mode = "live_interactive"
            print(f"\n--- Iniciando Preparación Modo: {operation_mode.upper()} ---")
            try:
                # El live_runner tiene su propia llamada a initialize_all_clients, pero gracias al flag
                # _initialized, solo imprimirá una advertencia y no hará nada, lo cual es seguro.
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
                print("\nVolviendo de Sesión Live.")
            except Exception as e_live_run:
                 print(f"ERROR CRITICO durante ejecución Live Runner: {e_live_run}")
                 traceback.print_exc()
            break

        elif choice == '2': # Modo Backtest
            operation_mode = "backtest_interactive"
            print(f"\n--- Iniciando Preparación Modo: {operation_mode.upper()} ---")
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
                print("\nBacktest completado.")
            except Exception as e_bt_run:
                 print(f"ERROR CRITICO durante ejecución Backtest Runner: {e_bt_run}")
                 traceback.print_exc()
            break
        
        elif choice == '3': # Modo Automático (seleccionado desde el menú)
            operation_mode = "automatic"
            print(f"\n--- Iniciando Preparación Modo: {operation_mode.upper()} ---")
            
            # Ya no se necesita el bloque de inicialización aquí, porque se hizo al principio.
            
            if not all([automatic_runner, ut_bot_controller, connection_ticker]):
                print("ERROR CRITICO: Faltan dependencias para el Modo Automático.")
                time.sleep(2); continue
            try:
                active_ticker_module = connection_ticker
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
                    connection_ticker_module=connection_ticker
                )
                print("\nVolviendo de Sesión Automática.")
            except Exception as e_auto_run:
                print(f"ERROR CRITICO durante ejecución del Modo Automático: {e_auto_run}")
                traceback.print_exc()
            break

        elif choice == '0':
            operation_mode = "exit"
            print("Saliendo del bot.");
            break

        else:
            print("Opción no válida. Intente de nuevo."); time.sleep(1)


def configure_runtime_settings() -> bool:
    """Configura el entorno mínimo: carga .env y verifica config base."""
    global config
    try:
        env_path = find_dotenv(raise_error_if_not_found=False, usecwd=True)
        if env_path:
            load_dotenv(dotenv_path=env_path, verbose=False, override=True)
            print(f"INFO: .env cargado desde: {env_path}")
        else:
            print("INFO: Archivo .env no encontrado (necesario para claves API y UIDs).")
    except Exception as e:
        print(f"Error buscando o cargando .env: {e}")

    if not config: print("ERROR CRITICO: Objeto config no cargado/importado."); return False
    pm_enabled_config = getattr(config, 'POSITION_MANAGEMENT_ENABLED', False)
    if not pm_enabled_config: print("INFO Base: Gestión de posiciones DESACTIVADA globalmente por config.py.")
    else: print("INFO Base: Gestión de posiciones ACTIVADA globalmente por config.py.")
    print("Entorno base configurado.")
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
        
        if active_ticker_module and hasattr(active_ticker_module, '_ticker_thread'):
             ticker_thread_instance = getattr(active_ticker_module, '_ticker_thread', None)
             if ticker_thread_instance and ticker_thread_instance.is_alive():
                 print("Asegurando parada final del ticker...")
                 if hasattr(active_ticker_module, 'stop_ticker_thread'):
                     try: active_ticker_module.stop_ticker_thread(); print("  Ticker detenido.")
                     except Exception as stop_err: print(f"  Error deteniendo ticker en finally: {stop_err}")
        elif operation_mode.startswith(("live", "automatic")):
            print("INFO: Modo Live/Automático finalizado (o interrumpido).")

        pm_enabled_final = getattr(config, 'POSITION_MANAGEMENT_ENABLED', False) if config else False
        if position_manager and pm_enabled_final and not final_summary:
             print("Obteniendo resumen final para mostrar estado...")
             try:
                 summary_final_print = position_manager.get_position_summary()
                 if summary_final_print and 'error' not in summary_final_print:
                     final_summary.update(summary_final_print)
                 elif summary_final_print: final_summary['error'] = summary_final_print.get('error', 'Error obteniendo resumen')
                 else: final_summary['error'] = 'No se pudo obtener resumen (respuesta vacía)'
             except Exception as e_sum_prn:
                 final_summary['error'] = f'Excepción al obtener resumen final: {e_sum_prn}'

        print("\n--- Resumen de Posiciones Abiertas al Finalizar ---")
        if final_summary and 'error' not in final_summary:
            if not final_summary.get('management_enabled', False):
                print("  (Gestión de posiciones no estuvo activa o falló resumen).")
            else:
                open_longs_final = final_summary.get('open_long_positions', [])
                open_shorts_final = final_summary.get('open_short_positions', [])
                qty_prec = getattr(config, 'DEFAULT_QTY_PRECISION', 3)
                price_prec = getattr(config, 'PRICE_PRECISION', 2)
                print("\n  --- Posiciones LONG Abiertas (Lógicas) ---");
                if open_longs_final:
                    for pos in open_longs_final:
                        size = utils.safe_float_convert(pos.get('size_contracts'), 0.0)
                        entry = utils.safe_float_convert(pos.get('entry_price'), 0.0)
                        tp = utils.safe_float_convert(pos.get('take_profit_price'), None)
                        tp_str = f"{tp:.{price_prec}f}" if tp is not None else "N/A"
                        pos_id_str = str(pos.get('id', 'N/A')); pos_id_short = "..." + pos_id_str[-6:]
                        print(f"    - ID: {pos_id_short}, Entrada: {entry:.{price_prec}f}, Tamaño: {size:.{qty_prec}f}, TP: {tp_str}")
                else: print("    (Ninguna)")
                print("\n  --- Posiciones SHORT Abiertas (Lógicas) ---");
                if open_shorts_final:
                    for pos in open_shorts_final:
                        size = utils.safe_float_convert(pos.get('size_contracts'), 0.0)
                        entry = utils.safe_float_convert(pos.get('entry_price'), 0.0)
                        tp = utils.safe_float_convert(pos.get('take_profit_price'), None)
                        tp_str = f"{tp:.{price_prec}f}" if tp is not None else "N/A"
                        pos_id_str = str(pos.get('id', 'N/A')); pos_id_short = "..." + pos_id_str[-6:]
                        print(f"    - ID: {pos_id_short}, Entrada: {entry:.{price_prec}f}, Tamaño: {size:.{qty_prec}f}, TP: {tp_str}")
                else: print("    (Ninguna)")
                if open_longs_final or open_shorts_final:
                    print("\n  ADVERTENCIA: El bot finalizó con posiciones lógicas abiertas.");
                    if operation_mode.startswith(("live", "automatic")):
                        print("               Verifica el estado FÍSICO en Bybit.")
            print("-" * 55)
        elif final_summary and 'error' in final_summary:
             print(f"\n--- Error Obteniendo Resumen Final ---\n  Error: {final_summary['error']}\n" + "-" * 55)
        else:
             print("\n--- Resumen Final de Posiciones ---\n  (Gestión desactivada o no se generó resumen).\n" + "-" * 55)

        if (pm_enabled_final and results_reporter and final_summary and 'error' not in final_summary):
             print("Generando/Sobrescribiendo reporte final...")
             try:
                 report_path = getattr(config, 'RESULTS_FILEPATH', 'result/results.txt')
                 report_dir = os.path.dirname(report_path)
                 if report_dir: os.makedirs(report_dir, exist_ok=True)
                 results_reporter.generate_report(final_summary, operation_mode)
                 print(f"  Reporte guardado en: {os.path.abspath(report_path)}")
             except Exception as report_err:
                 print(f"  ERROR generando reporte final: {report_err}")

        print("\nPrograma terminado.")

# =============== FIN ARCHIVO: main.py (v13 - CORRECCIÓN FINAL Y DEFINITIVA) ===============
