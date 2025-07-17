# =============== INICIO ARCHIVO: automatic_backtest_runner.py (v1.3 - Lógica de Apertura Corregida) ===============
"""
Contiene la lógica para ejecutar un backtest del Modo Automático del bot.

v1.3:
- CORREGIDO: La máquina de estados ahora reacciona correctamente a las señales del
  UT Bot. Cuando ocurre un cambio de estado (NEUTRAL->ACTIVE o FLIP), se llama
  explícitamente a la lógica de apertura de bajo nivel del `position_manager` para
  simular la entrada inicial, resolviendo el bug de no-apertura.
"""
import os
import traceback
import json
import time
import sys
import datetime
from typing import Optional, Dict, Any, TYPE_CHECKING
import pandas as pd

# --- Importar Dependencias ---
if TYPE_CHECKING:
    import config
    from core import utils, menu
    from core.strategy import (
        position_manager, balance_manager, position_state,
        event_processor, ta_manager, ut_bot_controller
    )
    from core.logging import open_position_snapshot_logger
    from core.reporting import results_reporter
    from backtest.connection import data_feeder
    from core.visualization import plotter

# --- Estado Global del Runner ---
_bot_state: str = "NEUTRAL"
_sl_cooldown_until: Optional[datetime.datetime] = None

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
    ut_bot_controller_module: Any,
    open_snapshot_logger_module: Any,
    results_reporter_module: Any,
    data_feeder_module: Any,
    plotter_module: Any
):
    global _bot_state, _sl_cooldown_until

    # --- 1. Verificaciones y Configuración Interactiva ---
    if not all([config_module, utils_module, menu_module, event_processor_module,
                ta_manager_module, data_feeder_module, ut_bot_controller_module,
                position_manager_module, balance_manager_module, position_state_module]):
        print("ERROR CRITICO [Auto BT Runner]: Faltan dependencias esenciales. Abortando.")
        return

    print("\n--- Configuración para Backtest del Modo Automático ---")
    selected_base_size, selected_initial_slots = menu_module.get_position_setup_interactively()
    if selected_base_size is None or selected_initial_slots is None:
        print("Backtest cancelado."); return

    print(f"INFO [Auto BT Runner]: Usando Tamaño Base: {selected_base_size:.2f} USDT, Slots: {selected_initial_slots}")
    print(f"\n--- Iniciando MODO: {operation_mode.upper()} ---")
    
    _bot_state = "NEUTRAL"
    setattr(config_module, 'POSITION_TRADING_MODE', 'NEUTRAL')
    _sl_cooldown_until = None
    
    try:
        ut_controller = ut_bot_controller_module.UTBotController(config_module, utils_module)
        ta_manager_module.initialize()
        if open_snapshot_logger_module: open_snapshot_logger_module.initialize_logger()
        
        event_processor_module.initialize(
            operation_mode=operation_mode,
            initial_real_state=None,
            base_position_size_usdt=selected_base_size,
            initial_max_logical_positions=selected_initial_slots,
            ut_bot_controller_instance=None,
            stop_loss_event=None
        )
        if not getattr(position_manager_module, '_initialized', False):
            raise RuntimeError("Position Manager no se inicializó correctamente.")
        print("Componentes Core inicializados para Backtest Automático.")
    except Exception as e_init:
        print(f"ERROR CRITICO durante inicialización: {e_init}"); traceback.print_exc(); return

    # --- 3. Carga de Datos Históricos ---
    print("\nCargando datos históricos para el backtest...")
    data_dir = getattr(config_module, 'BACKTEST_DATA_DIR', 'data')
    csv_file = getattr(config_module, 'BACKTEST_CSV_FILE', 'data.csv')
    ts_col = getattr(config_module, 'BACKTEST_CSV_TIMESTAMP_COL', 'timestamp')
    price_col = getattr(config_module, 'BACKTEST_CSV_PRICE_COL', 'close')
    historical_data = data_feeder_module.load_and_prepare_data(data_dir, csv_file, ts_col, price_col)

    if historical_data is None or historical_data.empty:
        print("ERROR: No se cargaron datos históricos válidos. Abortando backtest."); return

    # --- 4. Bucle Principal de Backtest ---
    print(f"\n--- Ejecutando Backtest Automático sobre {len(historical_data)} filas ---")
    start_time = time.time()
    total_rows = len(historical_data)
    print_interval = max(1, total_rows // 20)

    for i, row in enumerate(historical_data.itertuples(index=True)):
        current_timestamp = row.Index
        current_price = float(getattr(row, 'price'))

        if not isinstance(current_timestamp, (datetime.datetime, pd.Timestamp)):
            continue

        # A. Procesar el tick con la estrategia de bajo nivel (para cierres y registro)
        low_level_signal_data = event_processor_module.process_event([], {"timestamp": current_timestamp, "price": current_price, "symbol": config_module.TICKER_SYMBOL})
        low_level_signal = low_level_signal_data.get('signal') if low_level_signal_data else "HOLD"

        # B. Procesar el tick con el controlador de alto nivel (UT Bot)
        ut_controller.add_tick(current_price, current_timestamp)
        ut_bot_signal = ut_controller.get_latest_signal()

        # C. Máquina de Estados
        if _sl_cooldown_until and current_timestamp < _sl_cooldown_until:
            continue
        
        if _bot_state in ["ACTIVE_LONG", "ACTIVE_SHORT"]:
            _check_roi_and_switch_to_neutral(config_module, position_manager_module, utils_module)
        
        # Procesar señal de alto nivel (UT Bot)
        if ut_bot_signal != "HOLD":
            if _bot_state == "NEUTRAL":
                if ut_bot_signal == "BUY":
                    print(f"\nINFO [Auto Backtest SM]: NEUTRAL -> BUY Signal @ {current_timestamp}. Cambiando a ACTIVE_LONG.")
                    _bot_state = "ACTIVE_LONG"
                    setattr(config_module, 'POSITION_TRADING_MODE', 'LONG_ONLY')
                    # Llamar al manejador de señal de bajo nivel para intentar la primera apertura
                    position_manager_module.handle_low_level_signal("BUY", current_price, current_timestamp)
                elif ut_bot_signal == "SELL":
                    print(f"\nINFO [Auto Backtest SM]: NEUTRAL -> SELL Signal @ {current_timestamp}. Cambiando a ACTIVE_SHORT.")
                    _bot_state = "ACTIVE_SHORT"
                    setattr(config_module, 'POSITION_TRADING_MODE', 'SHORT_ONLY')
                    position_manager_module.handle_low_level_signal("SELL", current_price, current_timestamp)

            elif _bot_state == "ACTIVE_LONG" and ut_bot_signal == "SELL":
                print(f"\nINFO [Auto Backtest SM]: ACTIVE_LONG -> SELL Signal (FLIP) @ {current_timestamp}.")
                _handle_flip_backtest('short', position_manager_module, config_module, current_price, current_timestamp)
                _bot_state = "ACTIVE_SHORT"
                setattr(config_module, 'POSITION_TRADING_MODE', 'SHORT_ONLY')
                # Tras el flip, intentar abrir la primera posición de la nueva tendencia
                position_manager_module.handle_low_level_signal("SELL", current_price, current_timestamp)

            elif _bot_state == "ACTIVE_SHORT" and ut_bot_signal == "BUY":
                print(f"\nINFO [Auto Backtest SM]: ACTIVE_SHORT -> BUY Signal (FLIP) @ {current_timestamp}.")
                _handle_flip_backtest('long', position_manager_module, config_module, current_price, current_timestamp)
                _bot_state = "ACTIVE_LONG"
                setattr(config_module, 'POSITION_TRADING_MODE', 'LONG_ONLY')
                position_manager_module.handle_low_level_signal("BUY", current_price, current_timestamp)

        # Si no hubo señal de alto nivel, procesar la señal de bajo nivel
        # siempre que el bot ya esté en una tendencia activa.
        elif _bot_state != "NEUTRAL":
            position_manager_module.handle_low_level_signal(low_level_signal, current_price, current_timestamp)

        # D. Chequear Stop Loss
        sl_pct = getattr(config_module, 'POSITION_PHYSICAL_STOP_LOSS_PCT', 0.0)
        if sl_pct > 0:
            for side in ['long', 'short']:
                physical_state = position_state_module.get_physical_position_state(side)
                avg_entry = utils_module.safe_float_convert(physical_state.get('avg_entry_price'))
                if avg_entry > 0 and len(position_state_module.get_open_logical_positions(side)) > 0:
                    sl_price = avg_entry * (1 - sl_pct / 100.0) if side == 'long' else avg_entry * (1 + sl_pct / 100.0)
                    if (side == 'long' and current_price <= sl_price) or (side == 'short' and current_price >= sl_price):
                        print(f"\nALERTA [Backtest]: STOP LOSS FÍSICO SIMULADO para {side.upper()} a precio {current_price:.4f}")
                        position_manager_module.close_all_logical_positions(side, current_price, current_timestamp)
                        _bot_state = "NEUTRAL"
                        setattr(config_module, 'POSITION_TRADING_MODE', 'NEUTRAL')
                        cooldown_secs = getattr(config_module, 'AUTOMATIC_SL_COOLDOWN_SECONDS', 900)
                        _sl_cooldown_until = current_timestamp + datetime.timedelta(seconds=cooldown_secs)

        if (i + 1) % print_interval == 0 or i == total_rows - 1:
            print(f"\r[Auto Backtest] Procesando: {i + 1}/{total_rows} ({((i + 1) / total_rows) * 100:.1f}%)", end="")

    print(f"\n\n--- Backtest Automático Finalizado en {time.time() - start_time:.2f} segundos ---")

    # --- 5. Reporte y Visualización ---
    if position_manager_module and getattr(config_module, 'POSITION_MANAGEMENT_ENABLED', False):
        summary = position_manager_module.get_position_summary()
        final_summary.clear(); final_summary.update(summary)
        if open_snapshot_logger_module: open_snapshot_logger_module.log_open_positions_snapshot(summary)
        if results_reporter_module:
            results_reporter_module.generate_report(summary, operation_mode)
        if plotter_module:
            signal_log = getattr(config_module, 'SIGNAL_LOG_FILE', '')
            closed_log = getattr(config_module, 'POSITION_CLOSED_LOG_FILE', '')
            plot_output = os.path.join(getattr(config_module, 'RESULT_DIR', 'result'), "automatic_backtest_plot.png")
            plotter_module.plot_signals_and_price(historical_data, signal_log, closed_log, plot_output)

# --- Funciones de Apoyo (sin cambios) ---
def _check_roi_and_switch_to_neutral(config_module: Any, position_manager_module: Any, utils_module: Any):
    # ... (cuerpo de la función sin cambios)
    global _bot_state
    if not getattr(config_module, 'AUTOMATIC_ROI_PROFIT_TAKING_ENABLED', False): return
    if _bot_state == "NEUTRAL": return # No chequear si ya estamos en neutral
    summary = position_manager_module.get_position_summary()
    if 'error' in summary: return
    initial_capital = summary.get('initial_total_capital', 0.0)
    if initial_capital < 1e-6: return
    total_pnl = summary.get('total_realized_pnl_long', 0.0) + summary.get('total_realized_pnl_short', 0.0)
    current_roi_pct = utils_module.safe_division(total_pnl, initial_capital) * 100
    target_roi_pct = getattr(config_module, 'AUTOMATIC_ROI_PROFIT_TARGET_PCT', 0.1)
    if current_roi_pct >= target_roi_pct:
        print(f"\nINFO [Auto Backtest]: ROI Alcanzado ({current_roi_pct:.3f}%). Cambiando a NEUTRAL.")
        _bot_state = "NEUTRAL"
        setattr(config_module, 'POSITION_TRADING_MODE', 'NEUTRAL')

def _handle_flip_backtest(target_side: str, position_manager_module: Any, config_module: Any, current_price: float, current_timestamp: datetime.datetime):
    current_side = 'short' if target_side == 'long' else 'long'
    summary = position_manager_module.get_position_summary()
    if 'error' in summary: return

    num_to_close = summary.get(f'open_{current_side}_positions_count', 0)
    if num_to_close > 0:
        position_manager_module.close_all_logical_positions(current_side, current_price, current_timestamp)

    if getattr(config_module, 'AUTOMATIC_FLIP_OPENS_NEW_POSITIONS', True) and num_to_close > 0:
        # La apertura ahora se gestionará en el bucle principal cuando se reciba la señal de flip.
        pass
# =============== FIN ARCHIVO: automatic_backtest_runner.py (v1.3 - Lógica de Apertura Corregida) ===============