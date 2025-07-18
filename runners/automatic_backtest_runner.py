"""
Contiene la lógica para ejecutar un backtest del Modo Automático del bot.

v2.0 (Arquitectura Centralizada):
- Alineado con la nueva arquitectura donde el position_manager centraliza toda la lógica de trading.
- La inicialización de los módulos se ha ajustado para pasar los parámetros de backtest
  (tamaño de posición, slots) directamente al `position_manager`.
- El runner está completamente simplificado: configura, alimenta datos y reporta. No toma
  ninguna decisión de trading.

v1.9 (Arquitectura de Régimen):
- Corregido AttributeError al renombrar la clase del controlador a MarketRegimeController.
- Simplificado drásticamente el bucle principal. El runner ya no gestiona una
  máquina de estados; ahora solo procesa los datos y delega toda la lógica de
  decisión al event_processor y al position_manager, que usan el contexto de mercado.
"""
import os
import traceback
import json
import time
import sys
import datetime
from typing import Optional, Dict, Any, TYPE_CHECKING
import pandas as pd

from core.strategy import pm_facade

# --- Importar Dependencias ---
if TYPE_CHECKING:
    import config
    from core import utils, menu
    from core.strategy import (
        balance_manager, position_state,
        event_processor, ta_manager, market_regime_controller
    )
    from core.logging import open_position_snapshot_logger
    from core.reporting import results_reporter
    from backtest.connection import data_feeder
    from core.visualization import plotter

# --- Lógica del Runner de Backtest Automático ---
def run_automatic_backtest_mode(
    final_summary: Dict[str, Any],
    operation_mode: str,
    # --- Módulos de Dependencia ---
    config_module: Any,
    utils_module: Any,
    menu_module: Any,
    position_manager_module: Any,
    balance_manager_module: Any,
    position_state_module: Any,
    event_processor_module: Any,
    ta_manager_module: Any,
    market_regime_controller_module: Any,
    open_snapshot_logger_module: Any,
    results_reporter_module: Any,
    data_feeder_module: Any,
    plotter_module: Any
):
    # --- 1. Verificaciones y Configuración Interactiva ---
    if not all([config_module, utils_module, menu_module, event_processor_module,
                ta_manager_module, data_feeder_module, market_regime_controller_module,
                position_manager_module, balance_manager_module, position_state_module]):
        print("ERROR CRITICO [Auto BT Runner]: Faltan dependencias esenciales. Abortando.")
        return

    print("\n--- Configuración para Backtest del Modo Automático ---")
    selected_base_size, selected_initial_slots = menu_module.get_position_setup_interactively()
    if selected_base_size is None or selected_initial_slots is None:
        print("Backtest cancelado."); return

    print(f"INFO [Auto BT Runner]: Usando Tamaño Base: {selected_base_size:.2f} USDT, Slots: {selected_initial_slots}")
    print(f"\n--- Iniciando MODO: {operation_mode.upper()} ---")
    
    # --- 2. Inicialización de Componentes ---
    # La gestión de estado (NEUTRAL, ACTIVE_LONG, etc.) ahora es implícita
    # y manejada por la lógica de tendencia dentro del Position Manager.
    
    historical_data = None
    backtest_completed_or_interrupted = False
    
    try:
        # Instanciar el controlador de régimen de mercado
        regime_controller = market_regime_controller_module.MarketRegimeController(config_module, utils_module)
        
        ta_manager_module.initialize()
        if open_snapshot_logger_module: open_snapshot_logger_module.initialize_logger()
        
        # <<< CAMBIO: Inicializar PM primero, pasándole los parámetros del backtest >>>
        # PM necesita los parámetros para configurar correctamente el Balance Manager desde el inicio.
        position_manager_module.initialize(
            operation_mode=operation_mode,
            initial_real_state=None,
            base_position_size_usdt_param=selected_base_size,
            initial_max_logical_positions_param=selected_initial_slots,
            stop_loss_event=None # No se necesita evento en backtest
        )
        
        # Ahora inicializar el Event Processor, que depende de un PM ya configurado.
        event_processor_module.initialize(
            operation_mode=operation_mode,
            ut_bot_controller_instance=regime_controller, # Pasar la instancia correcta
            # Ya no se pasan parámetros de posición, EP los consultará al PM si es necesario.
            stop_loss_event=None # No hay hilos que parar en backtest
        )

        if not getattr(position_manager_module, '_initialized', False):
            raise RuntimeError("Position Manager no se inicializó correctamente.")
        print("Componentes Core inicializados para Backtest Automático.")

        # --- 3. Carga de Datos Históricos (sin cambios) ---
        print("\nCargando datos históricos para el backtest...")
        data_dir = getattr(config_module, 'BACKTEST_DATA_DIR', 'data')
        csv_file = getattr(config_module, 'BACKTEST_CSV_FILE', 'data.csv')
        ts_col = getattr(config_module, 'BACKTEST_CSV_TIMESTAMP_COL', 'timestamp')
        price_col = getattr(config_module, 'BACKTEST_CSV_PRICE_COL', 'price')
        historical_data = data_feeder_module.load_and_prepare_data(data_dir, csv_file, ts_col, price_col)

        if historical_data is None or historical_data.empty:
            raise RuntimeError("No se cargaron datos históricos válidos. Abortando backtest.")

        # --- 4. Bucle Principal de Backtest (SIMPLIFICADO, sin cambios) ---
        print(f"\n--- Ejecutando Backtest Automático sobre {len(historical_data)} filas ---")
        start_time = time.time()
        total_rows = len(historical_data)
        print_interval = max(1, total_rows // 20)

        try:
            for i, row in enumerate(historical_data.itertuples(index=True)):
                current_timestamp = row.Index
                current_price = float(getattr(row, 'price'))

                if not isinstance(current_timestamp, (datetime.datetime, pd.Timestamp)):
                    continue
                
                # Toda la lógica de decisión ahora está dentro de process_event,
                # que a su vez llama al Position Manager.
                event_processor_module.process_event([], {"timestamp": current_timestamp, "price": current_price, "symbol": config_module.TICKER_SYMBOL})

                if (i + 1) % print_interval == 0 or i == total_rows - 1:
                    print(f"\r[Auto Backtest] Procesando: {i + 1}/{total_rows} ({((i + 1) / total_rows) * 100:.1f}%)", end="")
        
        except event_processor_module.GlobalStopLossException as e:
            print("\n" + "="*80)
            print("--- BACKTEST DETENIDO POR GLOBAL STOP LOSS ---".center(80))
            print(f"--- Razón: {e} ---".center(80))
            print("--- El proceso continuará para generar el reporte y gráfico final. ---".center(80))
            print("="*80)

        print(f"\n\n--- Backtest Automático Finalizado en {time.time() - start_time:.2f} segundos ---")
        backtest_completed_or_interrupted = True

    except (KeyboardInterrupt, SystemExit):
        print("\n\n--- Backtest Interrumpido por el Usuario ---")
        backtest_completed_or_interrupted = True
    except Exception as e:
        print(f"ERROR CRITICO durante la ejecución del backtest: {e}")
        traceback.print_exc()
        backtest_completed_or_interrupted = True
    finally:
        # --- 5. Reporte y Visualización (sin cambios) ---
        if backtest_completed_or_interrupted:
            # NOTA: El sombreado del gráfico ya no es necesario ya que no hay una máquina de estados explícita
            # en el runner. El gráfico mostrará las operaciones que SÍ se ejecutaron,
            # lo cual es el resultado deseado de la simulación.
            if position_manager_module and getattr(config_module, 'POSITION_MANAGEMENT_ENABLED', False):
                summary = position_manager_module.get_position_summary()
                final_summary.clear(); final_summary.update(summary)
                if open_snapshot_logger_module: open_snapshot_logger_module.log_open_positions_snapshot(summary)
                if results_reporter_module:
                    results_reporter_module.generate_report(summary, operation_mode)
                if plotter_module and historical_data is not None:
                    signal_log = getattr(config_module, 'SIGNAL_LOG_FILE', '')
                    closed_log = getattr(config_module, 'POSITION_CLOSED_LOG_FILE', '')
                    plot_output = os.path.join(getattr(config_module, 'RESULT_DIR', 'result'), "automatic_backtest_plot.png")
                    plotter_module.plot_signals_and_price(
                        historical_data,
                        signal_log,
                        closed_log,
                        plot_output
                    )