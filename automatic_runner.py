# =============== INICIO ARCHIVO: automatic_runner.py (NUEVO) ===============
"""
Contiene la lógica para ejecutar el Modo Automático del bot.

Este runner orquesta el bot de la siguiente manera:
1.  Inicia y gestiona tres hilos principales:
    - Hilo Ticker: Obtiene precios en tiempo real.
    - Hilo UT Bot Controller: Genera señales de dirección de alto nivel.
    - Hilo Key Listener: Permite la intervención manual del usuario.
2.  Implementa una máquina de estados de alto nivel para controlar el régimen del bot:
    - NEUTRAL: Estado de espera, no abre posiciones.
    - ACTIVE_LONG: El bot de bajo nivel solo puede abrir posiciones largas.
    - ACTIVE_SHORT: El bot de bajo nivel solo puede abrir posiciones cortas.
3.  Reacciona a las señales del UT Bot para cambiar de régimen (ej. "flipping" de long a short).
4.  Reacciona a los eventos de Stop Loss Físico, poniendo al bot en un estado de
    enfriamiento (cooldown) antes de reanudar las operaciones.
"""
import time
import traceback
import json
import datetime
import threading
import sys
import os
from typing import Optional, Dict, Any, List

# --- Dependencias del Proyecto (se pasan como argumentos) ---
# Esto es solo para type hinting y claridad
if False:
    import config
    from core import utils, menu, live_operations
    from core.strategy import (
        position_manager, balance_manager, position_state,
        event_processor, ta_manager, ut_bot_controller
    )
    from core.logging import open_position_snapshot_logger
    from live.connection import ticker as connection_ticker

# --- Estado Global del Runner Automático ---
_bot_state: str = "NEUTRAL"
_ut_bot_signal: str = "HOLD"
_stop_loss_event = threading.Event()
_sl_cooldown_until: Optional[datetime.datetime] = None

# --- Variables para el Listener de Teclado (igual que en live_runner) ---
_key_pressed_event = threading.Event()
_manual_intervention_char = 'm'
_stop_key_listener_thread = threading.Event()
# (El código de la función key_listener_thread_func se importará o se copiará aquí)
if os.name == 'nt':
    import msvcrt
else:
    import select, tty, termios

def key_listener_thread_func():
    # (Esta función es una copia de la de live_runner.py para mantener el módulo autocontenido)
    global _key_pressed_event, _manual_intervention_char, _stop_key_listener_thread
    print(f"\n[Key Listener] Hilo iniciado. Presiona '{_manual_intervention_char}' para menú, Ctrl+C para salir.")
    if os.name == 'nt':
        while not _stop_key_listener_thread.is_set():
            if msvcrt.kbhit():
                try:
                    char = msvcrt.getch().decode().lower()
                    if char == _manual_intervention_char:
                        print(f"\n[Key Listener] Tecla '{_manual_intervention_char}' detectada!")
                        _key_pressed_event.set()
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
                    if char == _manual_intervention_char:
                        print(f"\n[Key Listener] Tecla '{_manual_intervention_char}' detectada!")
                        _key_pressed_event.set()
        except Exception: pass
        finally:
            if old_settings:
                termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
    print("[Key Listener] Hilo terminado.")


# --- Hilo del Controlador UT Bot ---
def ut_bot_controller_thread_func(ut_controller, config_module):
    """
    Hilo que llama periódicamente al controlador UT Bot para generar una nueva señal.
    """
    global _ut_bot_signal
    signal_interval = getattr(config_module, 'UT_BOT_SIGNAL_INTERVAL_SECONDS', 3600)
    print(f"[UT Bot Thread] Hilo iniciado. Generando señal cada {signal_interval}s.")
    while not _stop_key_listener_thread.is_set(): # Usa el mismo evento de parada general
        try:
            # get_latest_signal se encarga de la lógica de agregación y cálculo
            new_signal = ut_controller.get_latest_signal()
            if new_signal != "HOLD":
                _ut_bot_signal = new_signal # Actualiza la señal global solo si es BUY o SELL
        except Exception as e:
            print(f"ERROR [UT Bot Thread]: {e}")
            traceback.print_exc()
        
        # Espera hasta el próximo intervalo de señal.
        # Esta espera determina la frecuencia con la que se generan las barras OHLC.
        time.sleep(1) # Chequea cada segundo para no esperar todo el intervalo si se cierra el bot.
                      # La lógica de agregación en get_latest_signal maneja el tiempo real.


# --- Lógica Principal del Runner Automático ---
def run_automatic_mode(
    final_summary: Dict[str, Any],
    operation_mode: str,
    # --- Módulos Pasados como Dependencias ---
    config_module: Any,
    utils_module: Any,
    menu_module: Any,
    live_operations_module: Any,
    position_manager_module: Any,
    balance_manager_module: Any,
    position_state_module: Any,
    open_snapshot_logger_module: Any,
    event_processor_module: Any,
    ta_manager_module: Any,
    ut_bot_controller_module: Any,
    connection_ticker_module: Any
):
    """
    Función principal para ejecutar y gestionar el modo automático.
    """
    global _bot_state, _ut_bot_signal, _sl_cooldown_until

    print(f"\n--- INICIANDO MODO: {operation_mode.upper()} ---")

    # --- 1. Inicialización de Componentes ---
    key_listener_hilo: Optional[threading.Thread] = None
    ut_bot_hilo: Optional[threading.Thread] = None
    bot_started = False
    
    try:
        # Inicializar conexiones (ya debería estar hecho, pero es una buena práctica verificar)
        try:
            from live.connection import manager as live_manager
            if not live_manager.get_initialized_accounts():
                raise RuntimeError("No hay clientes API inicializados.")
        except (ImportError, RuntimeError) as e:
            print(f"ERROR CRITICO [Automatic Runner]: Fallo de conexión API: {e}")
            return

        # Instanciar el controlador del UT Bot
        ut_controller = ut_bot_controller_module.UTBotController(config_module, utils_module)

        # Inicializar todos los componentes del core
        print("Inicializando Componentes Core (TA, EP, PM)...")
        ta_manager_module.initialize()
        if open_snapshot_logger_module and getattr(config_module, 'POSITION_LOG_OPEN_SNAPSHOT', False):
            open_snapshot_logger_module.initialize_logger()
        
        # Pasar la instancia del UT Controller al Event Processor
        event_processor_module.initialize(
            operation_mode=operation_mode,
            ut_bot_controller_instance=ut_controller,
            # Pasar el evento de SL al position_manager
            stop_loss_event=_stop_loss_event
        )

        # Verificar que el Position Manager se inicializó correctamente
        if getattr(config_module, 'POSITION_MANAGEMENT_ENABLED', False):
             if not getattr(position_manager_module, '_initialized', False):
                 raise RuntimeError("Position Manager no se inicializó correctamente vía Event Processor.")

        print("Componentes Core inicializados.")
        bot_started = True

        # --- 2. Iniciar Hilos ---
        print("Iniciando hilos de operación (Ticker, UT Bot, Key Listener)...")
        # Hilo Ticker de Precios
        connection_ticker_module.start_ticker_thread(raw_event_callback=event_processor_module.process_event)
        
        # Hilo del Controlador UT Bot
        ut_bot_hilo = threading.Thread(
            target=ut_bot_controller_thread_func,
            args=(ut_controller, config_module),
            daemon=True
        )
        ut_bot_hilo.start()

        # Hilo del Listener de Teclado
        if getattr(config_module, 'INTERACTIVE_MANUAL_MODE', False):
            key_listener_hilo = threading.Thread(target=key_listener_thread_func, daemon=True)
            key_listener_hilo.start()

        print("--- BOT OPERATIVO EN MODO AUTOMÁTICO ---")
        
        # --- 3. Bucle Principal de la Máquina de Estados ---
        while True:
            # --- Manejo de Intervención Manual ---
            if _key_pressed_event.is_set():
                _stop_key_listener_thread.set()
                if key_listener_hilo and key_listener_hilo.is_alive():
                    key_listener_hilo.join(timeout=1.5)
                
                # Aquí iría la llamada al nuevo menú mejorado
                # handle_manual_intervention_menu(...)
                print("DEBUG: Menú de intervención manual sería llamado aquí.")

                _key_pressed_event.clear()
                _stop_key_listener_thread.clear()
                if getattr(config_module, 'INTERACTIVE_MANUAL_MODE', False):
                    key_listener_hilo = threading.Thread(target=key_listener_thread_func, daemon=True)
                    key_listener_hilo.start()

            # --- Manejo de Stop Loss ---
            if _stop_loss_event.is_set():
                print(f"ALERTA [Automatic Runner]: Evento de Stop Loss detectado! Cambiando a NEUTRAL.")
                _bot_state = "NEUTRAL"
                cooldown_seconds = getattr(config_module, 'AUTOMATIC_SL_COOLDOWN_SECONDS', 900)
                _sl_cooldown_until = datetime.datetime.now() + datetime.timedelta(seconds=cooldown_seconds)
                print(f"  - Bot en Cooldown por SL hasta: {_sl_cooldown_until.strftime('%Y-%m-%d %H:%M:%S')}")
                setattr(config_module, 'POSITION_TRADING_MODE', 'NEUTRAL') # Modo especial para que PM no abra nada
                _stop_loss_event.clear() # Resetear el evento
                _ut_bot_signal = "HOLD" # Ignorar señales viejas

            # --- Chequeo de Cooldown ---
            if _sl_cooldown_until and datetime.datetime.now() < _sl_cooldown_until:
                time.sleep(1)
                continue # Saltar el resto del bucle si estamos en cooldown

            # --- Lógica de la Máquina de Estados ---
            current_signal = _ut_bot_signal
            if current_signal != "HOLD":
                if _bot_state == "NEUTRAL":
                    if current_signal == "BUY":
                        print("INFO [State Machine]: NEUTRAL -> BUY Signal. Cambiando a ACTIVE_LONG.")
                        _bot_state = "ACTIVE_LONG"
                        setattr(config_module, 'POSITION_TRADING_MODE', 'LONG_ONLY')
                    elif current_signal == "SELL":
                        print("INFO [State Machine]: NEUTRAL -> SELL Signal. Cambiando a ACTIVE_SHORT.")
                        _bot_state = "ACTIVE_SHORT"
                        setattr(config_module, 'POSITION_TRADING_MODE', 'SHORT_ONLY')

                elif _bot_state == "ACTIVE_LONG":
                    if current_signal == "SELL":
                        print("INFO [State Machine]: ACTIVE_LONG -> SELL Signal. Ejecutando FLIP a SHORT.")
                        _handle_flip(
                            target_side='short',
                            position_manager_module=position_manager_module,
                            config_module=config_module,
                            live_operations_module=live_operations_module
                        )
                        _bot_state = "ACTIVE_SHORT"
                        setattr(config_module, 'POSITION_TRADING_MODE', 'SHORT_ONLY')

                elif _bot_state == "ACTIVE_SHORT":
                    if current_signal == "BUY":
                        print("INFO [State Machine]: ACTIVE_SHORT -> BUY Signal. Ejecutando FLIP a LONG.")
                        _handle_flip(
                            target_side='long',
                            position_manager_module=position_manager_module,
                            config_module=config_module,
                            live_operations_module=live_operations_module
                        )
                        _bot_state = "ACTIVE_LONG"
                        setattr(config_module, 'POSITION_TRADING_MODE', 'LONG_ONLY')

                _ut_bot_signal = "HOLD" # Consumir la señal

            time.sleep(0.5) # Pausa del bucle principal
    
    except (KeyboardInterrupt, SystemExit):
        print("\nDeteniendo Proceso Automático...")
    except Exception as e:
        print(f"ERROR CRITICO en el Runner Automático: {e}")
        traceback.print_exc()
    finally:
        print("\n--- Limpieza del Runner Automático ---")
        _stop_key_listener_thread.set()
        
        if key_listener_hilo and key_listener_hilo.is_alive():
            key_listener_hilo.join(timeout=1.0)
        if ut_bot_hilo and ut_bot_hilo.is_alive():
            ut_bot_hilo.join(timeout=1.0)
            
        if bot_started:
            connection_ticker_module.stop_ticker_thread()
            print("Ticker detenido.")

            if getattr(config_module, 'POSITION_MANAGEMENT_ENABLED', False) and position_manager_module:
                summary = position_manager_module.get_position_summary()
                final_summary.clear()
                final_summary.update(summary)
                print("\n--- Resumen Final (Automatic Runner) ---")
                print(json.dumps(summary, indent=2))
                if open_snapshot_logger_module and getattr(config_module, 'POSITION_LOG_OPEN_SNAPSHOT', False):
                    open_snapshot_logger_module.log_open_positions_snapshot(summary)


def _handle_flip(target_side: str, position_manager_module: Any, config_module: Any, live_operations_module: Any):
    """
    Gestiona el "flip": cierra las posiciones del lado actual y opcionalmente
    abre nuevas en el lado opuesto.
    """
    current_side = 'short' if target_side == 'long' else 'long'
    print(f"--- Ejecutando FLIP de {current_side.upper()} a {target_side.upper()} ---")

    # 1. Obtener el estado actual antes de cerrar
    summary_before_flip = position_manager_module.get_position_summary()
    if 'error' in summary_before_flip:
        print(f"ERROR [Flip]: No se pudo obtener resumen PM: {summary_before_flip['error']}")
        return

    positions_to_close_key = f'open_{current_side}_positions'
    positions_to_close = summary_before_flip.get(positions_to_close_key, [])
    num_positions_to_close = len(positions_to_close)

    if num_positions_to_close == 0:
        print(f"INFO [Flip]: No hay posiciones {current_side.upper()} para cerrar. Procediendo a cambiar de modo.")
        return

    # 2. Cerrar todas las posiciones del lado actual
    print(f"Cerrando {num_positions_to_close} posiciones {current_side.upper()}...")
    success_closing = position_manager_module.close_all_logical_positions(current_side)

    if not success_closing:
        print("ERROR [Flip]: No se pudieron cerrar todas las posiciones. Flip abortado.")
        return

    # Esperar un poco para que el estado se actualice
    time.sleep(getattr(config_module, 'POST_CLOSE_SYNC_DELAY_SECONDS', 1.0) * 2)

    # 3. Abrir nuevas posiciones si está configurado
    if getattr(config_module, 'AUTOMATIC_FLIP_OPENS_NEW_POSITIONS', True):
        print(f"Abriendo {num_positions_to_close} posiciones en el lado {target_side.upper()}...")
        success_opening = position_manager_module.force_open_multiple_positions(target_side, num_positions_to_close)
        if not success_opening:
            print("ERROR [Flip]: Falló la apertura de nuevas posiciones post-flip.")
    else:
        print("INFO [Flip]: Cierre completado. No se abrirán nuevas posiciones automáticamente (config).")

    print("--- FLIP completado ---")

# =============== FIN ARCHIVO: automatic_runner.py (NUEVO) ===============