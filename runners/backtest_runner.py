"""
Contiene la lógica para ejecutar el modo Backtest del bot.
Incluye carga de datos, configuración interactiva, simulación, reporte y visualización.

v8.8:
- Integrado el manejo de la excepción GlobalStopLossException para detener
  el backtest de forma controlada sin interrumpir la generación de reportes.
"""
import os
import traceback
import json
import time
import sys
from typing import Optional, Dict, Any, TYPE_CHECKING

# --- Importar Dependencias ---
try:
    import config
    from core import utils
    from core import menu
    from core.strategy import pm_facade
    from core.strategy import balance_manager
    from core.strategy import position_state
    from core.strategy import event_processor
    from core.strategy import ta_manager
    from core.logging import open_position_snapshot_logger
    from core.reporting import results_reporter
    from backtest.connection import data_feeder
    from core.visualization import plotter
except ImportError as e_core: print(f"ERROR CRITICO [BT Runner Import]: Falló importación: {e_core}"); traceback.print_exc(); sys.exit(1)
except Exception as e_imp_other: print(f"ERROR CRITICO [BT Runner Import]: Excepción importando: {e_imp_other}"); traceback.print_exc(); sys.exit(1)


# --- Lógica Modo Backtest ---
def run_backtest_mode(
    final_summary: Dict[str, Any],
    operation_mode: str,
    # --- Argumentos de Dependencias ---
    config_module: Any,
    utils_module: Any,
    menu_module: Any,
    position_manager_module: Optional[Any],
    event_processor_module: Optional[Any],
    open_snapshot_logger_module: Optional[Any],
    results_reporter_module: Optional[Any],
    balance_manager_module: Optional[Any],
    position_state_module: Optional[Any],
    ta_manager_module: Optional[Any]
    ):

    if not all([config_module, utils_module, menu_module, event_processor_module, ta_manager_module, data_feeder]):
         missing = [name for name, mod in [('config', config_module), ('utils', utils_module), ('menu', menu_module), ('EP', event_processor_module), ('TA', ta_manager_module), ('DataFeeder', data_feeder)] if not mod]
         print(f"ERROR CRITICO [Backtest Runner]: Faltan módulos esenciales: {missing}. Abortando.")
         return
    management_enabled_base = getattr(config_module, 'POSITION_MANAGEMENT_ENABLED', False)
    if management_enabled_base and not all([position_manager_module, position_state_module, balance_manager_module]):
         missing_pm = [name for name, mod in [('PM', position_manager_module), ('PS', position_state_module), ('BM', balance_manager_module)] if not mod]
         print(f"ERROR CRITICO [Backtest Runner]: Gestión habilitada pero faltan módulos PM/PS/BM: {missing_pm}. Abortando.")
         return

    print("\n--- Configuración Interactiva para Backtest ---")
    selected_trading_mode = menu_module.get_trading_mode_interactively()
    if selected_trading_mode == "CANCEL": print("Backtest cancelado."); return

    selected_base_size, selected_initial_slots = menu_module.get_position_setup_interactively()
    if selected_base_size is None or selected_initial_slots is None:
        print("Backtest cancelado (Configuración de Posiciones)."); return

    print("-" * 62)
    print(f"  Modo Trading Backtest      : {selected_trading_mode}")
    print(f"  Tamaño Base por Posición   : {selected_base_size:.4f} USDT")
    print(f"  Nº Inicial Slots por Lado  : {selected_initial_slots}")
    print("-" * 62)
    print("Confirmando configuración..."); time.sleep(1.5)

    original_trading_mode = getattr(config_module, 'POSITION_TRADING_MODE', 'LONG_SHORT')
    try:
        setattr(config_module, 'POSITION_TRADING_MODE', selected_trading_mode)
        setattr(config_module, 'PRINT_TICK_LIVE_STATUS', False)
        print(f"INFO [Backtest Runner]: Configuración temporal aplicada (Modo: {selected_trading_mode}).")
    except Exception as e_cfg_set: print(f"ERROR [Backtest Runner]: Aplicando config temporal: {e_cfg_set}"); return

    print(f"\n--- Iniciando MODO {operation_mode.upper()} (Trading: {selected_trading_mode}) ---")
    management_enabled_runtime = getattr(config_module, 'POSITION_MANAGEMENT_ENABLED', False)
    print(f"Gestión Posiciones: {'Activada' if management_enabled_runtime else 'Desactivada'}")
    if management_enabled_runtime:
        print(f"Log Snap Final: {getattr(config_module, 'POSITION_LOG_OPEN_SNAPSHOT', False)}")
        print(f"Generar Reporte: {'Sí' if results_reporter_module else 'No'}")
    print("\nInicializando Componentes Core (TA, EventProcessor)...")
    try:
        if not ta_manager_module or not hasattr(ta_manager_module, 'initialize'): raise RuntimeError("TA Manager no disponible/inválido.")
        ta_manager_module.initialize()

        if open_snapshot_logger_module and hasattr(open_snapshot_logger_module, 'initialize_logger') and getattr(config_module, 'POSITION_LOG_OPEN_SNAPSHOT', False):
            try: open_snapshot_logger_module.initialize_logger()
            except Exception as e_log_init: print(f"WARN: Error inicializando OSL: {e_log_init}")
        elif getattr(config_module, 'POSITION_LOG_OPEN_SNAPSHOT', False): print("WARN: OSL habilitado pero módulo no disponible.")

        if not event_processor_module or not hasattr(event_processor_module, 'initialize'): raise RuntimeError("Event Processor no disponible/inválido.")
        print(f"  Inicializando Event Processor (Modo: {operation_mode})...")
        event_processor_module.initialize(
            operation_mode=operation_mode,
            initial_real_state=None,
            base_position_size_usdt=selected_base_size,
            initial_max_logical_positions=selected_initial_slots
        )
        pm_init_success = getattr(position_manager_module, '_initialized', False) if management_enabled_runtime and position_manager_module else (not management_enabled_runtime)
        if management_enabled_runtime and not pm_init_success:
             raise RuntimeError("Position Manager no se inicializó correctamente vía Event Processor.")

        print("Componentes Core inicializados.")
    except RuntimeError as e_init_core: print(f"ERROR CRITICO [BT Runner]: Inicializando componentes: {e_init_core}"); traceback.print_exc(); return
    except Exception as e_init_gen: print(f"ERROR CRITICO [BT Runner]: Excepción inesperada inicializando: {e_init_gen}"); traceback.print_exc(); return

    print("\nProcesando datos históricos..."); print("-" * 30)
    historical_data = None; backtest_completed_successfully = False
    try:
        print("Cargando datos desde CSV...");
        data_dir = getattr(config_module, 'BACKTEST_DATA_DIR', 'data'); csv_file = getattr(config_module, 'BACKTEST_CSV_FILE', 'data.csv')
        ts_col = getattr(config_module, 'BACKTEST_CSV_TIMESTAMP_COL', 'timestamp'); price_col = getattr(config_module, 'BACKTEST_CSV_PRICE_COL', 'price')
        historical_data = data_feeder.load_and_prepare_data(data_dir, csv_file, ts_col, price_col)
        if historical_data is not None and not historical_data.empty:
            print(f"Ejecutando backtest ({len(historical_data)} filas)...");
            if not hasattr(event_processor_module, 'process_event'): raise RuntimeError("Event Processor sin método 'process_event'.")

            # <<< INICIO DE LA MODIFICACIÓN >>>
            try:
                data_feeder.run_backtest(
                    historical_data_df=historical_data,
                    callback=event_processor_module.process_event
                )
            except event_processor_module.GlobalStopLossException as e:
                print("\n" + "="*80)
                print("--- BACKTEST DETENIDO POR GLOBAL STOP LOSS ---".center(80))
                print(f"--- Razón: {e} ---".center(80))
                print("--- El proceso continuará para generar el reporte y gráfico final. ---".center(80))
                print("="*80)
            # <<< FIN DE LA MODIFICACIÓN >>>

            print("\n--- Backtest Finalizado (Procesamiento de Datos) ---"); backtest_completed_successfully = True

            management_enabled_final = getattr(config_module, 'POSITION_MANAGEMENT_ENABLED', False)
            pm_initialized_final = getattr(position_manager_module, '_initialized', False) if position_manager_module else False

            if management_enabled_final and position_manager_module and pm_initialized_final:
                 final_pm_summary_local = position_manager_module.get_position_summary()
                 if final_pm_summary_local and 'error' not in final_pm_summary_local:
                     final_summary.clear(); final_summary.update(final_pm_summary_local)
                     print("\n--- Resumen Final (Backtest PM) ---"); print(json.dumps(final_pm_summary_local, indent=2)); print("-" * 30)
                     if open_snapshot_logger_module and hasattr(open_snapshot_logger_module, 'log_open_positions_snapshot') and getattr(config_module, 'POSITION_LOG_OPEN_SNAPSHOT', False):
                          try: open_snapshot_logger_module.log_open_positions_snapshot(final_pm_summary_local);
                          except Exception as log_err: print(f"WARN: Error guardando snapshot final: {log_err}")
                     elif getattr(config_module, 'POSITION_LOG_OPEN_SNAPSHOT', False): print("WARN: Snapshot Logger habilitado pero módulo/método no disponible.")
                 elif final_pm_summary_local: print(f"WARN: Error obteniendo resumen PM: {final_pm_summary_local.get('error', 'N/A')}"); final_summary.clear(); final_summary['error'] = final_pm_summary_local.get('error', 'Error obteniendo resumen PM')
                 else: print("WARN: No se pudo obtener resumen PM post-backtest."); final_summary.clear(); final_summary['error'] = 'Resumen PM vacío post-backtest'
            elif management_enabled_final: print("WARN: No se pudo obtener resumen final (PM habilitado pero no disponible/inicializado)."); final_summary.clear(); final_summary['error'] = 'PM habilitado pero no disponible/inicializado'
        else: print("ERROR: No se cargaron datos históricos válidos.")
    except Exception as backtest_err: print(f"ERROR CRITICO durante Backtest: {backtest_err}"); traceback.print_exc()
    finally:
        print("--- Fin Procesamiento Backtest ---")
        try: setattr(config_module, 'POSITION_TRADING_MODE', original_trading_mode); print(f"INFO [BT Runner]: Config POSITION_TRADING_MODE restaurada a '{original_trading_mode}'.")
        except Exception as e_cfg_restore: print(f"WARN: No se pudo restaurar config.POSITION_TRADING_MODE: {e_cfg_restore}")

    if backtest_completed_successfully:
        management_enabled_report = getattr(config_module, 'POSITION_MANAGEMENT_ENABLED', False)
        if results_reporter_module and management_enabled_report and final_summary and isinstance(final_summary, dict) and 'error' not in final_summary:
             print("\nGenerando reporte de resultados...")
             try:
                 if hasattr(results_reporter_module, 'generate_backtest_report_from_summary'):
                      report_path = getattr(config_module, 'RESULTS_FILEPATH', 'result/results.txt'); report_dir = os.path.dirname(report_path);
                      if report_dir: os.makedirs(report_dir, exist_ok=True)
                      results_reporter_module.generate_backtest_report_from_summary(
                          pm_summary=final_summary,
                          operation_mode=operation_mode,
                          config_module=config_module,
                          utils_module=utils_module
                      )
                      print(f"Reporte generado en: {os.path.abspath(report_path)}")
                 elif hasattr(results_reporter_module, 'generate_report'):
                      print("WARN: Usando generate_report genérico. Asegúrate que calcula bien el Equity y Margen Usado para backtest.")
                      report_path = getattr(config_module, 'RESULTS_FILEPATH', 'result/results.txt'); report_dir = os.path.dirname(report_path);
                      if report_dir: os.makedirs(report_dir, exist_ok=True)
                      results_reporter_module.generate_report(final_summary, operation_mode)
                      print(f"Reporte generado en: {os.path.abspath(report_path)}")
                 else: print("WARN: results_reporter no tiene método de generación de reporte adecuado.")
             except Exception as report_err: print(f"\nERROR generando reporte: {report_err}"); traceback.print_exc()
        elif management_enabled_report and (not final_summary or 'error' in final_summary): print("\nWARN: Reporte no generado (falta resumen válido o error PM).")
        elif management_enabled_report and not results_reporter_module: print("\nWARN: Results Reporter no disponible.")

        if historical_data is not None and not historical_data.empty:
             print("\nIniciando visualización (Default para Backtest)...")
             try:
                 if not plotter or not hasattr(plotter, 'plot_signals_and_price'): print("ERROR: Módulo/función Plotter no disponible.")
                 else:
                     signal_log_path = getattr(config_module, 'SIGNAL_LOG_FILE', 'logs/signals_log.jsonl');
                     actual_closed_positions_log_path = None
                     log_closed_enabled = getattr(config_module, 'POSITION_LOG_CLOSED_POSITIONS', False)
                     if management_enabled_report and log_closed_enabled:
                          closed_log_file_rel = getattr(config_module, 'POSITION_CLOSED_LOG_FILE', 'logs/closed_positions.jsonl')
                          if closed_log_file_rel:
                              abs_closed_log_file = os.path.abspath(closed_log_file_rel)
                              if os.path.exists(abs_closed_log_file): actual_closed_positions_log_path = abs_closed_log_file
                              else: print(f"WARN [Plotter]: Log cerradas no encontrado en '{abs_closed_log_file}'.")
                          else: print("WARN [Plotter]: Log cerradas habilitado pero path no definido.")

                     plot_output_dir = getattr(config_module, 'RESULT_DIR', 'result'); symbol_cfg = getattr(config_module, "TICKER_SYMBOL", "data")
                     plot_filename_base = getattr(config_module, 'PLOT_OUTPUT_FILENAME', f'plot_{symbol_cfg}_{selected_trading_mode}.png')
                     plot_filename = plot_filename_base if plot_filename_base.lower().endswith('.png') else plot_filename_base + '.png'
                     os.makedirs(plot_output_dir, exist_ok=True); plot_output_path = os.path.abspath(os.path.join(plot_output_dir, plot_filename))
                     print(f"Generando gráfico en: {plot_output_path}")
                     plotter.plot_signals_and_price(
                          historical_data_df=historical_data,
                          signal_log_filepath=signal_log_path,
                          closed_positions_log_filepath=actual_closed_positions_log_path if actual_closed_positions_log_path else "",
                          output_filepath=plot_output_path
                      )
                     print("Visualización completada.")
             except ImportError: print("ERROR: Módulo Plotter no encontrado.")
             except FileNotFoundError as e_plot_fnf: print(f"ERROR visualización (archivo no encontrado): {e_plot_fnf}")
             except Exception as plot_err: print(f"ERROR durante visualización: {plot_err}"); traceback.print_exc()
        else: print("\nNo se puede visualizar: datos históricos no disponibles.")
    else: print("\nBacktest no completado con éxito. No se generará reporte ni visualización.")