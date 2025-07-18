"""
Contiene la lógica para ejecutar el Modo Automático del bot en VIVO.

v16.0 (Arquitectura Centralizada):
- Runner totalmente simplificado. No gestiona ningún estado de trading.
- Toda la lógica de apertura/cierre, incluyendo filtros de contexto, ROI por tendencia
  y límite de trades, está ahora centralizada en el position_manager.
- El runner solo inicia y mantiene vivos los hilos necesarios.
- Se elimina la máquina de estados explícita y cualquier función de apoyo relacionada.

v15.0 (Arquitectura de Régimen Sincronizada):
- Sincronizada la lógica con automatic_backtest_runner. Se elimina la máquina de
  estados explícita.
- El runner ahora solo gestiona los hilos y el bucle principal, mientras que
  toda la lógica de trading (contexto + señal) se delega al event_processor
  y al position_manager.
- Se elimina el hilo del controlador de alto nivel, ya que su lógica ahora
  se invoca directamente desde el event_processor en cada tick.
"""
import time
import traceback
import json
import datetime
import threading
import sys
import os
from typing import Optional, Dict, Any, List, TYPE_CHECKING

from core.strategy import market_regime_controller, pm_facade

# --- Type Hinting ---
if TYPE_CHECKING:
    import config
    from core import utils, menu, live_operations
    from core.strategy import (
        balance_manager, position_state,
        event_processor, ta_manager
    )
    from core.logging import open_position_snapshot_logger
    from core.visualization import plotter
    from live.connection import ticker as connection_ticker

# --- Estado Global del Runner (SIMPLIFICADO) ---
_global_stop_loss_event = threading.Event()
_key_pressed_event = threading.Event()
_manual_intervention_char = 'm'
_stop_key_listener_thread = threading.Event()
_tick_visualization_status = {"low_level": True, "ut_bot": False} # ut_bot es ahora obsoleto pero se mantiene por el menú

# --- Hilo Listener de Teclas (Sin cambios) ---
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

# --- Manejo del Menú de Intervención Manual (Simplificado, sin cambios) ---
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
        
        # <<< CAMBIO: _bot_state ya no existe. Se puede usar 'trading_mode' o el estado de tendencia del PM >>>
        # Para mantener la compatibilidad del menú, se usa 'trading_mode', que es más estático.
        summary['bot_state'] = summary.get('trend_status', {}).get('current_trend_side', 'NO_TREND')
        
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
            # Esta opción ya no tiene un efecto real sobre la lógica, pero se mantiene por consistencia del menú
            _tick_visualization_status['ut_bot'] = not _tick_visualization_status['ut_bot']
            print(f"INFO: Visualización de Señales de Alto Nivel {'ACTIVADA' if _tick_visualization_status['ut_bot'] else 'DESACTIVADA'} (Nota: el controlador ahora funciona en cada tick).")
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


# --- Lógica Principal del Runner (SIMPLIFICADA) ---
def run_automatic_mode(
    final_summary: Dict[str, Any], operation_mode: str,
    config_module: Any, utils_module: Any, menu_module: Any,
    live_operations_module: Any, position_manager_module: Any,
    balance_manager_module: Any, position_state_module: Any,
    open_snapshot_logger_module: Any, event_processor_module: Any,
    ta_manager_module: Any, market_regime_controller_module: Any,
    connection_ticker_module: Any,
    plotter_module: Any,
    results_reporter_module: Any
):
    global _global_stop_loss_event, _key_pressed_event, _stop_key_listener_thread

    print(f"\n--- INICIANDO MODO: {operation_mode.upper()} ---")
    key_listener_hilo: Optional[threading.Thread] = None
    bot_started = False
    
    _global_stop_loss_event.clear()

    try:
        from live.connection import manager as live_manager
        if not live_manager.get_initialized_accounts():
            raise RuntimeError("No hay clientes API inicializados.")

        # Instanciar el controlador de régimen de mercado
        regime_controller = market_regime_controller_module.MarketRegimeController(config_module, utils_module)

        print("Inicializando Componentes Core...")
        ta_manager_module.initialize()
        if open_snapshot_logger_module: open_snapshot_logger_module.initialize_logger()

        # <<< INICIALIZACIÓN DE MÓDULOS CRÍTICOS >>>
        # El Position Manager se debe inicializar antes que el Event Processor
        # para asegurar que está listo para recibir señales.
        position_manager_module.initialize(
            operation_mode=operation_mode,
            # No se pasan parámetros de tamaño/slots, ya que se leen de config
            # o se gestionan internamente en la inicialización de PM.
        )

        event_processor_module.initialize(
            operation_mode=operation_mode,
            ut_bot_controller_instance=regime_controller, # Pasar la instancia del controlador
            global_stop_loss_event=_global_stop_loss_event
            # El `stop_loss_event` para cambiar estado ya no es necesario aquí.
        )

        if not getattr(position_manager_module, '_initialized', False):
            raise RuntimeError("Position Manager no se inicializó correctamente.")

        print("Componentes Core inicializados.")
        bot_started = True

        # El runner ya no gestiona el estado. Su única misión es orquestar los hilos.
        print("INFO [Automatic Runner]: El bot está listo. Operará según el contexto de mercado definido por el Position Manager.")

        print("Iniciando hilos de operación (Ticker, Key Listener)...")
        connection_ticker_module.start_ticker_thread(raw_event_callback=event_processor_module.process_event)
        
        if getattr(config_module, 'INTERACTIVE_MANUAL_MODE', False):
            key_listener_hilo = threading.Thread(target=key_listener_thread_func, daemon=True)
            key_listener_hilo.start()

        print("--- BOT OPERATIVO EN MODO AUTOMÁTICO ---")
        
        # Bucle principal ahora es mucho más simple.
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
            
            # El bucle principal solo necesita mantenerse vivo y chequear interrupciones.
            # Toda la lógica de trading ocurre en el hilo del Ticker -> Event Processor -> Position Manager.
            time.sleep(1)

    except (KeyboardInterrupt, SystemExit):
        print("\n--- Interrupción Detectada. Deteniendo Proceso Automático... ---")
    except Exception as e:
        print(f"ERROR CRITICO en Runner Automático: {e}"); traceback.print_exc()
    finally:
        print("\n--- Limpieza Final del Runner Automático ---")
        _stop_key_listener_thread.set()
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

# --- Funciones de Apoyo (ELIMINADAS) ---
# Las funciones como _check_roi_and_switch_to_neutral, _check_trade_limit_and_switch_to_neutral, y _handle_flip
# ya no son necesarias en este runner, ya que no gestiona el estado de trading.
# La lógica de toma de ganancias y límite de trades ahora reside completamente dentro del Position Manager.