# =============== INICIO ARCHIVO: runners/live_interactive_runner.py (COMPLETO Y FINAL) ===============
"""
Contiene la lógica principal para orquestar el modo Live Interactivo del bot.

v16.0 (Orquestador Interactivo Refactorizado):
- Actúa como el orquestador principal de la sesión interactiva.
- Llama a los módulos de apoyo para los menús pre-inicio y el listener de teclas.
- Inicia y gestiona los hilos de Ticker y Listener de Teclas.
- Entra en un bucle principal para manejar la intervención del usuario a través de la CLI.
- No contiene lógica de trading; todo se delega al ecosistema del Position Manager.
"""
import time
import traceback
import json
import threading
from typing import Optional, Dict, Any, TYPE_CHECKING

# --- Type Hinting para dependencias inyectadas ---
if TYPE_CHECKING:
    import config
    from core import utils, menu, live_operations
    from core.strategy import pm_facade
    from core.strategy import event_processor, ta_manager, balance_manager, position_state
    from core.logging import open_position_snapshot_logger

# --- Importar helpers específicos del runner ---
from . import live_interactive_helpers
from . import live_interactive_menus

# --- Función Principal del Runner ---
def run_live_interactive_mode(
    final_summary: Dict[str, Any],
    operation_mode: str,
    # --- Módulos de Dependencia Inyectados ---
    config_module: Any, 
    utils_module: Any,  
    menu_module: Any,   
    live_operations_module: Any,
    position_manager_module: Any, # Realmente es pm_facade
    balance_manager_module: Any,
    position_state_module: Any,
    open_snapshot_logger_module: Any,
    event_processor_module: Any,
    ta_manager_module: Any
):
    
    connection_ticker_module: Optional[Any] = None
    key_listener_hilo: Optional[threading.Thread] = None
    bot_started: bool = False
    
    try:
        # --- 1. Preparación del Entorno y Verificaciones Pre-vuelo ---
        print("\n--- INICIANDO MODO: LIVE INTERACTIVO ---")
        
        # Importar y verificar el gestor de conexión
        try:
            from live.connection import manager as live_manager
            from live.connection import ticker as connection_ticker
            connection_ticker_module = connection_ticker
        except ImportError:
            raise RuntimeError("Módulos de conexión (manager, ticker) no encontrados.")

        if not live_manager.get_initialized_accounts():
            raise RuntimeError("No hay clientes API inicializados. No se puede continuar en modo live.")
        
        initialized_accs = live_manager.get_initialized_accounts()

        # --- 2. Menú Pre-Inicio ---
        # Delega toda la lógica del menú pre-inicio al módulo correspondiente
        base_size, initial_slots, action = live_interactive_menus.run_pre_start_menu(
            initialized_accs=initialized_accs,
            config_module=config_module,
            utils_module=utils_module,
            menu_module=menu_module,
            live_operations_module=live_operations_module,
            position_manager_module=position_manager_module,
            balance_manager_module=balance_manager_module,
            position_state_module=position_state_module
        )

        if action == "EXIT":
            print("[Live Runner] Saliendo por selección del usuario en el menú pre-inicio.")
            return None
        if action != "START_BOT" or base_size is None or initial_slots is None:
            raise RuntimeError("Configuración de sesión no completada o cancelada.")

        # --- 3. Inicialización de Componentes Core ---
        print("\n--- Inicializando Componentes Core para la Sesión Live ---")
        
        ta_manager_module.initialize()
        if open_snapshot_logger_module and getattr(config_module, 'POSITION_LOG_OPEN_SNAPSHOT', False):
            open_snapshot_logger_module.initialize_logger()

        # El modo de trading inicial para una sesión interactiva siempre es NEUTRAL
        setattr(config_module, 'POSITION_TRADING_MODE', 'NEUTRAL')

        position_manager_module.initialize(
            operation_mode=operation_mode,
            initial_real_state=None, # PM obtendrá el estado si lo necesita
            base_position_size_usdt_param=base_size,
            initial_max_logical_positions_param=initial_slots,
            stop_loss_event=None
        )
        
        event_processor_module.initialize(
            operation_mode=operation_mode,
            ut_bot_controller_instance=None
        )

        if not getattr(position_manager_module.pm_state, 'is_initialized', lambda: False)():
            raise RuntimeError("El Position Manager no se inicializó correctamente.")
        
        bot_started = True
        print("Componentes Core inicializados con éxito.")

        # --- 4. Inicio de Hilos y Bucle Principal ---
        print("\n--- Iniciando Operación del Bot ---")
        connection_ticker_module.start_ticker_thread(
            raw_event_callback=event_processor_module.process_event
        )
        
        if getattr(config_module, 'INTERACTIVE_MANUAL_MODE', False):
            stop_event = live_interactive_helpers.get_stop_key_listener_event()
            stop_event.clear()
            key_pressed_event = live_interactive_helpers.get_key_pressed_event()
            key_pressed_event.clear()
            key_listener_hilo = threading.Thread(target=live_interactive_helpers.key_listener_thread_func, daemon=True)
            key_listener_hilo.start()
        
        print("\n" + "="*50)
        print("EL BOT ESTÁ OPERATIVO Y PROCESANDO DATOS DE MERCADO".center(50))
        print("Iniciado en modo NEUTRAL.".center(50))
        print(f"Presiona '{live_interactive_helpers._manual_intervention_char}' para abrir el menú de control.".center(50))
        print("Presiona Ctrl+C para detener el bot.".center(50))
        print("="*50)

        # Bucle principal del runner
        while True:
            key_pressed_event = live_interactive_helpers.get_key_pressed_event()
            if getattr(config_module, 'INTERACTIVE_MANUAL_MODE', False) and key_pressed_event.is_set():
                print("\n[Live Runner] Intervención manual solicitada...")
                stop_event = live_interactive_helpers.get_stop_key_listener_event()
                stop_event.set()
                if key_listener_hilo and key_listener_hilo.is_alive():
                    key_listener_hilo.join(timeout=1.0)
                
                # Llamar al bucle del menú CLI
                menu_module.run_cli_menu_loop()
                
                # Reiniciar el listener para la próxima intervención
                key_pressed_event.clear()
                stop_event.clear()
                key_listener_hilo = threading.Thread(target=live_interactive_helpers.key_listener_thread_func, daemon=True)
                key_listener_hilo.start()
                print("\n[Live Runner] Menú cerrado. Reanudando operación normal...")
            
            if not connection_ticker_module._ticker_thread.is_alive():
                raise RuntimeError("¡El hilo del Ticker ha muerto inesperadamente!")

            time.sleep(0.5)

    except (KeyboardInterrupt, SystemExit):
        print("\n[Live Runner] Interrupción detectada. Iniciando secuencia de apagado...")
    except RuntimeError as e:
        print(f"\nERROR CRÍTICO EN TIEMPO DE EJECUCIÓN: {e}")
        traceback.print_exc()
    except Exception as e:
        print(f"\nERROR INESPERADO en Live Runner: {e}")
        traceback.print_exc()
    finally:
        # --- 5. Secuencia de Apagado Limpio ---
        print("\n--- Limpieza Final del Live Runner ---")
        
        stop_event = live_interactive_helpers.get_stop_key_listener_event()
        stop_event.set()
        if key_listener_hilo and key_listener_hilo.is_alive():
            key_listener_hilo.join(timeout=1.0)
        
        if bot_started and connection_ticker_module:
            print("Deteniendo el Ticker de precios...")
            connection_ticker_module.stop_ticker_thread()
            print("Ticker detenido.")
        
        if bot_started and getattr(config_module, 'POSITION_MANAGEMENT_ENABLED', False):
            print("Obteniendo resumen final del Position Manager...")
            summary = position_manager_module.get_position_summary()
            if summary and not summary.get('error'):
                final_summary.clear()
                final_summary.update(summary)
                
                if open_snapshot_logger_module and getattr(config_module, 'POSITION_LOG_OPEN_SNAPSHOT', False):
                    open_snapshot_logger_module.log_open_positions_snapshot(summary)
            else:
                final_summary['error'] = 'No se pudo obtener el resumen final del PM.'
        
        return connection_ticker_module

# --- CÓDIGO COMENTADO DEL ARCHIVO ORIGINAL ---
# El siguiente código ha sido refactorizado o movido a otros módulos.
# Se conserva aquí, comentado, como referencia histórica del desarrollo.
"""
# Esta función ahora es obsoleta y ha sido reemplazada por la CLI en core/menu.py
def handle_manual_intervention_menu(
    config_module: Any, 
    utils_module: Any,  
    menu_module: Any,   
    position_manager_module: Optional[Any]
):
    pass # La lógica ahora vive en core/menu.py y es llamada desde el bucle principal

# Esta función ha sido movida a runners/live_interactive_menus.py
def run_full_test_cycle(...):
    pass
"""
# =============== FIN ARCHIVO: runners/live_interactive_runner.py (COMPLETO Y FINAL) ===============