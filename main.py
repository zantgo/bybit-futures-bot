# =============== INICIO ARCHIVO: main.py (v8.7.x - Llamadas a Runner Corregidas) ===============
"""
Punto de entrada principal (v8.7.x).
Selección de modo (Live/Backtest), configuración inicial base, y orquesta la ejecución.
Modo de Trading y configuración de posición se solicitan interactivamente DENTRO de cada runner.
v8.7.x: Corregidas llamadas a runners para pasar módulos con nombres de parámetros esperados.
v8.7.6: Elimina condición 'not os.path.exists' para generar/sobrescribir reporte siempre al final.
v8.7.5: Corregido TypeError en llamada Backtest (añadido menu=menu).
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

# --- Verificación de Dependencias ---
print("Verificando dependencias (dotenv, pybit, pandas, numpy, matplotlib)...")
try:
    import pybit, pandas, numpy, matplotlib
    print("Dependencias encontradas.")
except ImportError as e:
    print(f"\nError: Falta dependencia '{e.name}'.")
    print("Instala con: pip install python-dotenv pybit pandas numpy matplotlib")
    sys.exit(1)

# --- Módulos Core y de Soporte ---
# Estos se inicializan como None y se importan en el bloque try
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

try:
    from core import utils
    from core import menu
    from core.strategy import ta_manager
    from core.strategy import event_processor

    if getattr(config, 'POSITION_MANAGEMENT_ENABLED', False):
        try: from core.strategy import position_manager as pm_mod; position_manager = pm_mod
        except ImportError as e_pm: print(f"WARN: No se pudo cargar Position Manager. Error: {e_pm}")
        except Exception as e_pm_other: print(f"WARN: Excepción cargando Position Manager: {e_pm_other}")
        try: from core.strategy import balance_manager as bm_mod; balance_manager = bm_mod
        except ImportError: print("WARN: No se pudo cargar Balance Manager.")
        try: from core.strategy import position_state as ps_mod; position_state = ps_mod
        except ImportError as e_ps: print(f"WARN: No se pudo cargar Position State. Error: {e_ps}")
        except Exception as e_ps_other: print(f"WARN: Excepción cargando Position State: {e_ps_other}")

        if getattr(config, 'POSITION_LOG_OPEN_SNAPSHOT', False):
            try: from core.logging import open_position_snapshot_logger as opsl_mod; open_snapshot_logger = opsl_mod
            except ImportError: print("WARN: No se pudo cargar Open Snapshot Logger.")
        try: from core.reporting import results_reporter as rr_mod; results_reporter = rr_mod
        except ImportError: print("WARN: No se pudo cargar Results Reporter.")
        try: from core import live_operations as lo_mod; live_operations = lo_mod
        except ImportError: print("WARN: No se pudo cargar Live Operations (requerido para PM Live).")
    elif not live_operations:
         try: from core import live_operations as lo_mod; live_operations = lo_mod
         except ImportError: print("WARN: No se pudo cargar Live Operations (útil para gestión manual o info de mercado).")

except ImportError as e: print(f"ERROR IMPORTACIÓN CORE INICIAL: {e.name}"); traceback.print_exc(); sys.exit(1)
except Exception as e: print(f"ERROR FATAL Config/Import Inicial: {e}"); traceback.print_exc(); sys.exit(1)

# --- Importar los Runners ---
try:
    import live_runner
    import backtest_runner
except ImportError as e:
    print(f"ERROR CRITICO: No se pudieron importar los runners ({e.name})."); traceback.print_exc(); sys.exit(1)

# --- Variables Globales ---
final_summary: Dict[str, Any] = {}
operation_mode: str = "unknown"
active_ticker_module: Optional[Any] = None

# --- Bucle Principal del Menú ---
def main_loop():
    global final_summary, operation_mode, config, active_ticker_module, utils, menu, live_operations, position_manager, balance_manager, position_state, open_snapshot_logger, event_processor, ta_manager, results_reporter

    if not menu: print("ERROR CRITICO: Módulo Menu no disponible."); sys.exit(1)
    if not config: print("ERROR CRITICO: Módulo Config no cargado."); sys.exit(1)
    if not utils: print("ERROR CRITICO: Módulo Utils no cargado."); sys.exit(1)

    print("\nConfigurando entorno base...")
    if not configure_runtime_settings():
         print("\nERROR: No se pudo configurar el entorno base. Abortando."); sys.exit(1)

    while True:
        choice = menu.get_main_menu_choice()

        if choice == '1': # Modo Live
            operation_mode = "live_interactive"
            print(f"\n--- Iniciando Preparación Modo: {operation_mode.upper()} ---")
            try:
                # <<< LLAMADAS CORREGIDAS CON SUFIJO _module EN LOS NOMBRES DE ARGUMENTOS >>>
                active_ticker_module = live_runner.run_live_pre_start(
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
                    ta_manager_module=ta_manager
                )
                print("\nVolviendo de Sesión Live.")
            except TypeError as te:
                 if "run_live_pre_start() missing" in str(te) or "required positional argument" in str(te): print(f"\nERROR: Falta un argumento requerido en la llamada a live_runner. {te}")
                 elif "unexpected keyword argument" in str(te): print(f"\nERROR: Se pasó un argumento inesperado a live_runner. {te}")
                 else: print(f"ERROR TypeError llamando Live Runner: {te}")
                 traceback.print_exc()
            except Exception as e_live_run:
                 print(f"ERROR CRITICO durante ejecución Live Runner: {e_live_run}")
                 traceback.print_exc()
            break 

        elif choice == '2': # Modo Backtest
            operation_mode = "backtest_interactive"
            print(f"\n--- Iniciando Preparación Modo: {operation_mode.upper()} ---")
            try:
                # <<< LLAMADAS CORREGIDAS CON SUFIJO _module EN LOS NOMBRES DE ARGUMENTOS >>>
                backtest_runner.run_backtest_mode(
                    final_summary=final_summary,
                    operation_mode=operation_mode,
                    config_module=config,
                    utils_module=utils,
                    menu_module=menu,
                    position_manager_module=position_manager,
                    event_processor_module=event_processor,
                    open_snapshot_logger_module=open_snapshot_logger,
                    results_reporter_module=results_reporter,
                    balance_manager_module=balance_manager,
                    position_state_module=position_state,
                    ta_manager_module=ta_manager
                )
                print("\nBacktest completado.")
            except TypeError as te:
                 if "run_backtest_mode() missing" in str(te) or "required positional argument" in str(te): print(f"\nERROR: Falta un argumento requerido en la llamada a backtest_runner. {te}")
                 elif "unexpected keyword argument" in str(te): print(f"\nERROR: Se pasó un argumento inesperado a backtest_runner. {te}")
                 else: print(f"ERROR TypeError llamando Backtest Runner: {te}")
                 traceback.print_exc()
            except Exception as e_bt_run:
                 print(f"ERROR CRITICO durante ejecución Backtest Runner: {e_bt_run}")
                 traceback.print_exc()
            break 

        elif choice == '0':
            operation_mode = "exit"
            print("Saliendo del bot.");
            break

        else:
            print("Opción no válida. Intente de nuevo."); time.sleep(1)


def configure_runtime_settings() -> bool:
    """ Configura el entorno mínimo: carga .env y verifica config base. """
    global config 
    try:
        env_path = find_dotenv(raise_error_if_not_found=False, usecwd=True)
        if env_path:
            load_dotenv(dotenv_path=env_path, verbose=False, override=True)
            print(f"INFO: .env cargado desde: {env_path}")
        else:
            print("INFO: Archivo .env no encontrado (necesario para claves API modo Live y UIDs).")
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
    except SystemExit:
        print("\nSaliendo del programa (SystemExit).")
    except KeyboardInterrupt:
        print("\n\nInterrupción global detectada (Ctrl+C). Saliendo forzosamente.")
        pm_enabled_on_exit = getattr(config, 'POSITION_MANAGEMENT_ENABLED', False) if config else False
        if operation_mode.startswith("live") and position_manager and pm_enabled_on_exit and not final_summary:
             print("Obteniendo resumen final por interrupción...")
             try:
                 summary_on_interrupt = position_manager.get_position_summary()
                 if summary_on_interrupt and 'error' not in summary_on_interrupt: final_summary.update(summary_on_interrupt); print("  Resumen final por interrupción obtenido.")
                 elif summary_on_interrupt: print(f"  Error obteniendo resumen final por interrupción: {summary_on_interrupt.get('error', 'Desconocido')}")
                 else: print("  WARN: get_position_summary devolvió None durante interrupción.")
             except Exception as e_sum_int: print(f"  Error obteniendo resumen final por interrupción: {e_sum_int}")
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
                 else: print("  WARN: No se encontró stop_ticker_thread.")
        elif operation_mode.startswith("live"): print("INFO: Modo Live finalizado (o interrumpido).")

        pm_enabled_final = getattr(config, 'POSITION_MANAGEMENT_ENABLED', False) if config else False
        if position_manager and pm_enabled_final and not final_summary:
             print("Obteniendo resumen final para mostrar estado...")
             try:
                 summary_final_print = position_manager.get_position_summary()
                 if summary_final_print and 'error' not in summary_final_print: final_summary.update(summary_final_print)
                 elif summary_final_print: final_summary['error'] = summary_final_print.get('error', 'Error obteniendo resumen final')
                 else: final_summary['error'] = 'No se pudo obtener resumen final (respuesta vacía)'
             except AttributeError as ae:
                  if "'NoneType' object has no attribute" in str(ae) or "'_initialized'" in str(ae): final_summary['error'] = 'PM no inicializado correctamente'
                  else: final_summary['error'] = f'Error atributo obteniendo resumen final: {ae}'
             except Exception as e_sum_prn: final_summary['error'] = f'Excepción al obtener resumen final: {e_sum_prn}'
        elif pm_enabled_final and not position_manager:
             final_summary['error'] = 'Módulo Position Manager no cargado/disponible'

        print("\n--- Resumen de Posiciones Abiertas al Finalizar ---")
        if final_summary and isinstance(final_summary, dict) and 'error' not in final_summary:
            positions_were_managed = final_summary.get('management_enabled', False)
            if not positions_were_managed: print("  (Gestión de posiciones no estuvo activa o falló resumen).")
            else:
                open_longs_final = final_summary.get('open_long_positions', [])
                open_shorts_final = final_summary.get('open_short_positions', [])
                qty_prec = getattr(config, 'DEFAULT_QTY_PRECISION', 3) if config else 3
                price_prec = getattr(config, 'PRICE_PRECISION', 2) if config else 2
                print("\n  --- Posiciones LONG Abiertas (Lógicas) ---");
                if open_longs_final:
                    for pos in open_longs_final:
                        size = utils.safe_float_convert(pos.get('size_contracts'), 0.0) if utils else 0.0
                        entry = utils.safe_float_convert(pos.get('entry_price'), 0.0) if utils else 0.0
                        tp = utils.safe_float_convert(pos.get('take_profit_price'), None) if utils else None
                        tp_str = f"{tp:.{price_prec}f}" if tp is not None else "N/A"
                        pos_id_str = str(pos.get('id', 'N/A')); pos_id_short = "..." + pos_id_str[-6:] if len(pos_id_str) > 6 else pos_id_str
                        print(f"    - ID: {pos_id_short}, Entrada: {entry:.{price_prec}f}, Tamaño: {size:.{qty_prec}f}, TP: {tp_str}")
                else: print("    (Ninguna)")
                print("\n  --- Posiciones SHORT Abiertas (Lógicas) ---");
                if open_shorts_final:
                    for pos in open_shorts_final:
                        size = utils.safe_float_convert(pos.get('size_contracts'), 0.0) if utils else 0.0
                        entry = utils.safe_float_convert(pos.get('entry_price'), 0.0) if utils else 0.0
                        tp = utils.safe_float_convert(pos.get('take_profit_price'), None) if utils else None
                        tp_str = f"{tp:.{price_prec}f}" if tp is not None else "N/A"
                        pos_id_str = str(pos.get('id', 'N/A')); pos_id_short = "..." + pos_id_str[-6:] if len(pos_id_str) > 6 else pos_id_str
                        print(f"    - ID: {pos_id_short}, Entrada: {entry:.{price_prec}f}, Tamaño: {size:.{qty_prec}f}, TP: {tp_str}")
                else: print("    (Ninguna)")
                if open_longs_final or open_shorts_final:
                    print("\n  ADVERTENCIA: El bot finalizó con posiciones lógicas abiertas.");
                    if operation_mode.startswith("live"): print("               Verifica el estado FÍSICO en Bybit.")
            print("-" * 55)
        elif final_summary and 'error' in final_summary:
             print(f"\n--- Error Obteniendo Resumen Final ---"); print(f"  Error: {final_summary['error']}"); print("-" * 55)
        else:
             pm_enabled_print = getattr(config, 'POSITION_MANAGEMENT_ENABLED', False) if config else False
             if pm_enabled_print: print("\n--- Resumen Final de Posiciones ---\n  (No se pudo obtener o no hubo actividad).\n" + "-" * 55)
             else: print("\n--- Resumen Final de Posiciones ---\n  (Gestión desactivada).\n" + "-" * 55)

        report_path = getattr(config, 'RESULTS_FILEPATH', 'result/results.txt') if config else 'result/results.txt'
        pm_enabled_report = getattr(config,'POSITION_MANAGEMENT_ENABLED', False) if config else False
        if (pm_enabled_report and results_reporter and final_summary and 'error' not in final_summary):
             print("Generando/Sobrescribiendo reporte final...")
             try:
                 report_dir = os.path.dirname(report_path)
                 if report_dir: os.makedirs(report_dir, exist_ok=True)
                 if hasattr(results_reporter, 'generate_report'):
                     results_reporter.generate_report(final_summary, operation_mode)
                     print(f"  Reporte guardado en: {os.path.abspath(report_path)}")
                 else:
                     print("  WARN: results_reporter no tiene el método generate_report.")
             except Exception as report_err:
                 print(f"  ERROR generando reporte final: {report_err}")
        elif pm_enabled_report and (not final_summary or 'error' in final_summary):
             print("INFO: Reporte final no generado (gestión activa pero resumen inválido).")
        elif pm_enabled_report and not results_reporter:
             print("INFO: Reporte final no generado (reporter no disponible).")
        elif not pm_enabled_report:
             print("INFO: Reporte final no generado (gestión de posiciones desactivada).")

        print("\nPrograma terminado.")

# =============== FIN ARCHIVO: main.py (v8.7.x - Llamadas a Runner Corregidas) ===============