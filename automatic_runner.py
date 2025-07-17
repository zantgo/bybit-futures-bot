"""
Contiene la lógica para ejecutar el Modo Automático del bot en VIVO.

v13.7 (Límite de Trades):
- Añadida lógica para limitar el número de trades por tendencia, controlada por
  AUTOMATIC_TRADE_LIMIT_ENABLED y AUTOMATIC_MAX_TRADES_PER_TREND.
v13.6 (Parada de Emergencia):
- Integrado el manejo del `_global_stop_loss_event` para una detención
  completa y limpia del bot si se activa el disyuntor global.
"""
import time
import traceback
import json
import datetime
import threading
import sys
import os
from typing import Optional, Dict, Any, List, TYPE_CHECKING

# --- Type Hinting ---
if TYPE_CHECKING:
    import config
    from core import utils, menu, live_operations
    from core.strategy import (
        position_manager, balance_manager, position_state,
        event_processor, ta_manager, ut_bot_controller
    )
    from core.logging import open_position_snapshot_logger
    from core.visualization import plotter
    from live.connection import ticker as connection_ticker

# --- Estado Global del Runner ---
_bot_state: str = "NEUTRAL"
_ut_bot_signal: str = "HOLD"
_stop_loss_event = threading.Event()
_global_stop_loss_event = threading.Event()
_sl_cooldown_until: Optional[datetime.datetime] = None
# <<< INICIO MODIFICACIÓN: Añadir contador de trades >>>
_trades_in_current_trend: int = 0
# <<< FIN MODIFICACIÓN >>>
_key_pressed_event = threading.Event()
_manual_intervention_char = 'm'
_stop_key_listener_thread = threading.Event()
_tick_visualization_status = {"low_level": True, "ut_bot": False}

# --- Hilo Listener de Teclas ---
if os.name == 'nt':
    import msvcrt
else:
    import select, tty, termios

def key_listener_thread_func():
    global _key_pressed_event, _manual_intervention_char, _stop_key_listener_thread
    print(f"\n[Key Listener] Hilo iniciado. Presiona '{_manual_intervention_char}' para menú, Ctrl+C para salir.")
    if os.name == 'nt':
        while not _stop_key_listener_thread.is_set():
            if msvcrt.kbhit():
                try:
                    char = msvcrt.getch().decode().lower()
                    if char == _manual_intervention_char: _key_pressed_event.set()
                except (UnicodeDecodeError, Exception): continue
            time.sleep(0.1)
    else:
        old_settings = None
        try:
            if not sys.stdin.isatty(): return
            old_settings = termios.tcgetattr(sys.stdin)
            tty.setcbreak(sys.stdin.fileno())
            while not _stop_key_listener_thread.is_set():
                if select.select([sys.stdin], [], [], 0.1)[0]:
                    char = sys.stdin.read(1).lower()
                    if char == _manual_intervention_char: _key_pressed_event.set()
        except Exception: pass
        finally:
            if old_settings: termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
    print("[Key Listener] Hilo terminado.")


# --- Hilo del Controlador UT Bot ---
def ut_bot_controller_thread_func(ut_controller: Any):
    global _ut_bot_signal
    while not _stop_key_listener_thread.is_set():
        try:
            new_signal = ut_controller.get_latest_signal()
            if new_signal != "HOLD":
                if _tick_visualization_status.get('ut_bot', False):
                     print(f"\n>>>> SEÑAL UT BOT GENERADA: {new_signal} <<<<")
                _ut_bot_signal = new_signal
        except Exception as e:
            print(f"ERROR [UT Bot Thread]: {e}"); traceback.print_exc()
        time.sleep(1)


# --- Manejo del Menú de Intervención Manual ---
def handle_manual_intervention_menu(
    config_module: Any,
    menu_module: Any,
    position_manager_module: Any
):
    global _tick_visualization_status
    if not all([config_module, menu_module, position_manager_module]): return
    if not getattr(position_manager_module, '_initialized', False): return
    while True:
        summary = position_manager_module.get_position_summary()
        if 'error' in summary:
            print(f"ERROR [Manual Menu]: No se pudo obtener resumen PM: {summary['error']}"); break
        summary['bot_state'] = _bot_state
        choice = menu_module.get_automatic_mode_intervention_menu(
            pm_summary=summary,
            tick_visualization_status=_tick_visualization_status
        )
        if choice == '1':
            menu_module.display_live_stats(summary)
        elif choice == '2':
            _tick_visualization_status['low_level'] = not _tick_visualization_status['low_level']
            setattr(config_module, 'PRINT_TICK_LIVE_STATUS', _tick_visualization_status['low_level'])
            print(f"INFO: Visualización de Ticks de Bajo Nivel {'ACTIVADA' if _tick_visualization_status['low_level'] else 'DESACTIVADA'}.")
            time.sleep(1.5)
        elif choice == '3':
            _tick_visualization_status['ut_bot'] = not _tick_visualization_status['ut_bot']
            print(f"INFO: Visualización de Señales de UT Bot {'ACTIVADA' if _tick_visualization_status['ut_bot'] else 'DESACTIVADA'}.")
            time.sleep(1.5)
        elif choice == '4':
            success, message = position_manager_module.add_max_logical_position_slot()
            print(f"Resultado: {message}"); time.sleep(2)
        elif choice == '5':
            success, message = position_manager_module.remove_max_logical_position_slot()
            print(f"Resultado: {message}"); time.sleep(2)
        elif choice == '6':
            try:
                current_size = summary.get('initial_base_position_size_usdt', 0.0)
                new_size_str = input(f"Ingrese nuevo tamaño base (USDT) [Actual: {current_size:.2f}], 0 para cancelar: ").strip()
                if new_size_str:
                    new_size = float(new_size_str)
                    if new_size > 0:
                        success, message = position_manager_module.set_base_position_size(new_size)
                        print(f"Resultado: {message}")
                    else: print("Cambio cancelado.")
            except (ValueError, TypeError): print("Error: Entrada inválida.")
            time.sleep(2)
        elif choice == '0':
            print("Volviendo a la operación del bot..."); break
        else:
            print("Opción inválida."); time.sleep(1)
    os.system('cls' if os.name == 'nt' else 'clear')


# --- Lógica Principal del Runner (MODIFICADA) ---
def run_automatic_mode(
    final_summary: Dict[str, Any], operation_mode: str,
    config_module: Any, utils_module: Any, menu_module: Any,
    live_operations_module: Any, position_manager_module: Any,
    balance_manager_module: Any, position_state_module: Any,
    open_snapshot_logger_module: Any, event_processor_module: Any,
    ta_manager_module: Any, ut_bot_controller_module: Any,
    connection_ticker_module: Any,
    plotter_module: Any,
    results_reporter_module: Any
):
    global _bot_state, _ut_bot_signal, _sl_cooldown_until, _global_stop_loss_event, _trades_in_current_trend

    print(f"\n--- INICIANDO MODO: {operation_mode.upper()} ---")
    key_listener_hilo: Optional[threading.Thread] = None
    ut_bot_hilo: Optional[threading.Thread] = None
    bot_started = False
    
    _global_stop_loss_event.clear()

    try:
        from live.connection import manager as live_manager
        if not live_manager.get_initialized_accounts():
            raise RuntimeError("No hay clientes API inicializados.")

        ut_controller = ut_bot_controller_module.UTBotController(config_module, utils_module)

        print("Inicializando Componentes Core...")
        ta_manager_module.initialize()
        if open_snapshot_logger_module: open_snapshot_logger_module.initialize_logger()

        event_processor_module.initialize(
            operation_mode=operation_mode,
            ut_bot_controller_instance=ut_controller,
            stop_loss_event=_stop_loss_event,
            global_stop_loss_event=_global_stop_loss_event
        )

        if not getattr(position_manager_module, '_initialized', False):
            raise RuntimeError("Position Manager no se inicializó correctamente.")

        print("Componentes Core inicializados.")
        bot_started = True

        print("INFO [Automatic Runner]: Estableciendo estado inicial a NEUTRAL.")
        _bot_state = "NEUTRAL"
        setattr(config_module, 'POSITION_TRADING_MODE', 'NEUTRAL')
        _trades_in_current_trend = 0

        print("Iniciando hilos de operación (Ticker, UT Bot, Key Listener)...")
        connection_ticker_module.start_ticker_thread(raw_event_callback=event_processor_module.process_event)
        ut_bot_hilo = threading.Thread(target=ut_bot_controller_thread_func, args=(ut_controller,), daemon=True)
        ut_bot_hilo.start()
        if getattr(config_module, 'INTERACTIVE_MANUAL_MODE', False):
            key_listener_hilo = threading.Thread(target=key_listener_thread_func, daemon=True)
            key_listener_hilo.start()

        print("--- BOT OPERATIVO EN MODO AUTOMÁTICO ---")

        while True:
            if _global_stop_loss_event.is_set():
                print("--- [Runner] Detención por Global Stop Loss detectada. Saliendo del bucle principal. ---")
                break

            if getattr(config_module, 'INTERACTIVE_MANUAL_MODE', False) and _key_pressed_event.is_set():
                _stop_key_listener_thread.set()
                if key_listener_hilo: key_listener_hilo.join(timeout=1.5)
                handle_manual_intervention_menu(config_module, menu_module, position_manager_module)
                _key_pressed_event.clear(); _stop_key_listener_thread.clear()
                key_listener_hilo = threading.Thread(target=key_listener_thread_func, daemon=True)
                key_listener_hilo.start()

            if _stop_loss_event.is_set():
                print(f"ALERTA [Runner]: Evento de SL detectado! Cambiando a NEUTRAL.")
                _bot_state = "NEUTRAL"
                cooldown = getattr(config_module, 'AUTOMATIC_SL_COOLDOWN_SECONDS', 900)
                _sl_cooldown_until = datetime.datetime.now() + datetime.timedelta(seconds=cooldown)
                setattr(config_module, 'POSITION_TRADING_MODE', 'NEUTRAL')
                _stop_loss_event.clear(); _ut_bot_signal = "HOLD"

            if _sl_cooldown_until and datetime.datetime.now() < _sl_cooldown_until:
                time.sleep(1); continue

            # <<< INICIO MODIFICACIÓN: Chequeo de trades cerrados >>>
            closed_count = position_manager_module.get_and_reset_closed_trades_count()
            if closed_count > 0:
                _trades_in_current_trend += closed_count
                print(f"INFO [Runner]: {closed_count} trade(s) cerrado(s). Total en tendencia: {_trades_in_current_trend}.")
                _check_trade_limit_and_switch_to_neutral(config_module)
            # <<< FIN MODIFICACIÓN >>>

            if _bot_state in ["ACTIVE_LONG", "ACTIVE_SHORT"]:
                _check_roi_and_switch_to_neutral(config_module, position_manager_module, utils_module)

            current_signal = _ut_bot_signal
            if current_signal != "HOLD":
                if _bot_state == "NEUTRAL":
                    if current_signal == "BUY":
                        print(f"INFO [State Machine]: NEUTRAL -> BUY Signal. Cambiando a ACTIVE_LONG.")
                        _bot_state = "ACTIVE_LONG"
                        setattr(config_module, 'POSITION_TRADING_MODE', 'LONG_ONLY')
                        _trades_in_current_trend = 0 # Resetear contador
                    elif current_signal == "SELL":
                        print(f"INFO [State Machine]: NEUTRAL -> SELL Signal. Cambiando a ACTIVE_SHORT.")
                        _bot_state = "ACTIVE_SHORT"
                        setattr(config_module, 'POSITION_TRADING_MODE', 'SHORT_ONLY')
                        _trades_in_current_trend = 0 # Resetear contador
                elif _bot_state == "ACTIVE_LONG" and current_signal == "SELL":
                    print(f"INFO [State Machine]: ACTIVE_LONG -> SELL Signal (FLIP). Cambiando a ACTIVE_SHORT.")
                    _handle_flip('short', position_manager_module, config_module)
                    _bot_state = "ACTIVE_SHORT"
                    setattr(config_module, 'POSITION_TRADING_MODE', 'SHORT_ONLY')
                    _trades_in_current_trend = 0 # Resetear contador
                elif _bot_state == "ACTIVE_SHORT" and current_signal == "BUY":
                    print(f"INFO [State Machine]: ACTIVE_SHORT -> BUY Signal (FLIP). Cambiando a ACTIVE_LONG.")
                    _handle_flip('long', position_manager_module, config_module)
                    _bot_state = "ACTIVE_LONG"
                    setattr(config_module, 'POSITION_TRADING_MODE', 'LONG_ONLY')
                    _trades_in_current_trend = 0 # Resetear contador

                _ut_bot_signal = "HOLD"

            time.sleep(0.5)

    except (KeyboardInterrupt, SystemExit):
        print("\n--- Interrupción Detectada. Deteniendo Proceso Automático... ---")
    except Exception as e:
        print(f"ERROR CRITICO en Runner Automático: {e}"); traceback.print_exc()
    finally:
        print("\n--- Limpieza Final del Runner Automático ---")
        _stop_key_listener_thread.set()
        if ut_bot_hilo and ut_bot_hilo.is_alive(): ut_bot_hilo.join(timeout=1.0)
        if key_listener_hilo and key_listener_hilo.is_alive(): key_listener_hilo.join(timeout=1.0)

        if bot_started:
            connection_ticker_module.stop_ticker_thread()
            if position_manager_module and getattr(config_module, 'POSITION_MANAGEMENT_ENABLED', False):
                summary = position_manager_module.get_position_summary()
                final_summary.clear(); final_summary.update(summary)
                print("\n--- Resumen Final (Automatic Runner) ---\n" + json.dumps(summary, indent=2))
                if open_snapshot_logger_module:
                    open_snapshot_logger_module.log_open_positions_snapshot(summary)
                if results_reporter_module:
                    results_reporter_module.generate_report(summary, operation_mode)
                if plotter_module:
                    print("INFO: La visualización final para el modo live/automático se basa en los logs generados.")

# --- Funciones de Apoyo ---
def _check_roi_and_switch_to_neutral(config_module: Any, position_manager_module: Any, utils_module: Any):
    global _bot_state
    if not getattr(config_module, 'AUTOMATIC_ROI_PROFIT_TAKING_ENABLED', False): return
    if _bot_state == "NEUTRAL": return
    try:
        summary = position_manager_module.get_position_summary()
        if 'error' in summary: return
        initial_capital = summary.get('initial_total_capital', 0.0)
        if initial_capital < 1e-6: return
        total_pnl = summary.get('total_realized_pnl_long', 0.0) + summary.get('total_realized_pnl_short', 0.0)
        current_roi_pct = utils_module.safe_division(total_pnl, initial_capital) * 100
        target_roi_pct = getattr(config_module, 'AUTOMATIC_ROI_PROFIT_TARGET_PCT', 0.1)
        if current_roi_pct >= target_roi_pct:
            print("\n" + "#"*80)
            print(f"### OBJETIVO DE ROI ALCANZADO ({current_roi_pct:.3f}% >= {target_roi_pct:.3f}%) ###".center(80))
            print(f"### Cambiando estado de '{_bot_state}' a 'NEUTRAL'. No se abrirán nuevas posiciones. ###".center(80))
            print("### Esperando nueva señal del UT Bot para reactivar. ###".center(80))
            print("#"*80 + "\n")
            _bot_state = "NEUTRAL"
            setattr(config_module, 'POSITION_TRADING_MODE', 'NEUTRAL')
    except Exception as e:
        print(f"ERROR [Runner Check ROI]: {e}")

# <<< INICIO MODIFICACIÓN: Nueva función de chequeo de límite de trades >>>
def _check_trade_limit_and_switch_to_neutral(config_module: Any):
    global _bot_state, _trades_in_current_trend
    if not getattr(config_module, 'AUTOMATIC_TRADE_LIMIT_ENABLED', False): return
    if _bot_state == "NEUTRAL": return

    limit = getattr(config_module, 'AUTOMATIC_MAX_TRADES_PER_TREND', 5)
    if _trades_in_current_trend >= limit:
        print("\n" + "#"*80)
        print(f"### LÍMITE DE TRADES ALCANZADO ({_trades_in_current_trend}/{limit}) ###".center(80))
        print(f"### Cambiando estado de '{_bot_state}' a 'NEUTRAL'. No se abrirán nuevas posiciones. ###".center(80))
        print("### Esperando nueva señal del UT Bot para reactivar. ###".center(80))
        print("#"*80 + "\n")
        _bot_state = "NEUTRAL"
        setattr(config_module, 'POSITION_TRADING_MODE', 'NEUTRAL')
# <<< FIN MODIFICACIÓN >>>

def _handle_flip(target_side: str, position_manager_module: Any, config_module: Any):
    current_side = 'short' if target_side == 'long' else 'long'
    print(f"--- Ejecutando FLIP de {current_side.upper()} a {target_side.upper()} ---")
    summary = position_manager_module.get_position_summary()
    if 'error' in summary:
        print(f"ERROR [Flip]: No se pudo obtener resumen PM: {summary['error']}"); return

    num_to_close = summary.get(f'open_{current_side}_positions_count', 0)
    if num_to_close > 0:
        current_price = position_manager_module.get_current_price_for_exit()
        if not current_price:
            print("ERROR [Flip]: No se pudo obtener precio actual para cierre. Abortando flip."); return
        print(f"Cerrando {num_to_close} posiciones {current_side.upper()}...")
        success_closing = position_manager_module.close_all_logical_positions(current_side, current_price, datetime.datetime.now())
        if not success_closing:
            print("ERROR [Flip]: No se pudieron cerrar todas las posiciones. Flip abortado.");
            return
        time.sleep(getattr(config_module, 'POST_CLOSE_SYNC_DELAY_SECONDS', 1.0) * 2)

    if getattr(config_module, 'AUTOMATIC_FLIP_OPENS_NEW_POSITIONS', True) and num_to_close > 0:
        print(f"Abriendo {num_to_close} posiciones en el lado {target_side.upper()}...")
        success_opening = position_manager_module.force_open_multiple_positions(target_side, num_to_close)
        if not success_opening: print("ERROR [Flip]: Falló la apertura de nuevas posiciones post-flip.")
    else:
        print("INFO [Flip]: Cierre completado. Comportamiento de no-reapertura configurado.")

    print("--- FLIP completado ---")