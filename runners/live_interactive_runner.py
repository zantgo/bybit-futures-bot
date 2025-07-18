# =============== INICIO ARCHIVO: runners/live_interactive_runner.py (CORREGIDO Y COMPLETO) ===============
"""
Contiene la lógica principal para orquestar el modo Live Interactivo del bot.

v17.0 (Asistente de Trading):
- Simplificado para actuar como un lanzador para el nuevo Asistente de Trading CLI.
- Delega toda la configuración inicial y el bucle de interacción al módulo `core.menu`.
- Inicia los componentes core y el ticker, luego cede el control al bucle de la CLI.
"""
import time
import traceback
# import json # Ya no se usa directamente en este archivo.
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
# from . import live_interactive_helpers # OBSOLETO: Reemplazado por la CLI bloqueante de core.menu
# from . import live_interactive_menus # OBSOLETO: Reemplazado por el Asistente/Wizard en core.menu

# --- Función Principal del Runner ---
def run_live_interactive_mode(
    final_summary: Dict[str, Any],
    operation_mode: str,
    # --- Módulos de Dependencia Inyectados ---
    config_module: Any, 
    utils_module: Any,  
    menu_module: Any,   
    live_operations_module: Any,
    position_manager_module: Any,
    balance_manager_module: Any,
    position_state_module: Any,
    open_snapshot_logger_module: Any,
    event_processor_module: Any,
    ta_manager_module: Any
):
    
    connection_ticker_module: Optional[Any] = None
    # key_listener_hilo: Optional[threading.Thread] = None # OBSOLETO
    bot_started: bool = False
    
    try:
        # --- 1. Asistente de Configuración Inicial (Wizard) ---
        print("\n--- INICIANDO MODO: LIVE INTERACTIVO ---")
        
        # El Asistente de Trading ahora maneja la configuración inicial.
        base_size, initial_slots = menu_module.run_trading_assistant_wizard()

        if base_size is None or initial_slots is None:
            print("[Live Runner] Saliendo, configuración no completada en el asistente.")
            return None

        # --- 2. Inicialización de Componentes Core ---
        print("\n--- Inicializando Componentes Core para la Sesión Live ---")
        
        # Importar y verificar el gestor de conexión
        try:
            from live.connection import manager as live_manager
            from live.connection import ticker as connection_ticker
            connection_ticker_module = connection_ticker
        except ImportError:
            raise RuntimeError("Módulos de conexión (manager, ticker) no encontrados.")

        if not live_manager.get_initialized_accounts():
            raise RuntimeError("No hay clientes API inicializados. No se puede continuar en modo live.")

        ta_manager_module.initialize()
        if open_snapshot_logger_module and getattr(config_module, 'POSITION_LOG_OPEN_SNAPSHOT', False):
            open_snapshot_logger_module.initialize_logger()

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
            ut_bot_controller_instance=None # No aplica en modo live
        )

        if not position_manager_module.pm_state.is_initialized():
            raise RuntimeError("El Position Manager no se inicializó correctamente.")
        
        bot_started = True
        print("Componentes Core inicializados con éxito.")

        # --- 3. Inicio de Hilos y Bucle Principal de la CLI ---
        print("\n--- Iniciando Operación del Bot y Asistente Interactivo ---")
        connection_ticker_module.start_ticker_thread(
            raw_event_callback=event_processor_module.process_event
        )
        
        # El listener de teclas ya no es necesario. La CLI de `core.menu` es bloqueante
        # y toma el control del hilo principal para la interacción del usuario.

        print("\n" + "="*50)
        print("EL BOT ESTÁ OPERATIVO Y PROCESANDO DATOS DE MERCADO".center(50))
        print("Iniciado en modo NEUTRAL.".center(50))
        print("Entrando en el Asistente de Trading Interactivo...".center(50))
        print("Presiona Ctrl+C en cualquier momento para detener el bot.".center(50))
        print("="*50)

        # Ceder el control al bucle de la CLI. Esta función es bloqueante.
        menu_module.run_cli_menu_loop()

        # Si el usuario sale del bucle con 'exit', el programa continuará hasta ser detenido por Ctrl+C.
        print("\n[Live Runner] Saliendo del menú interactivo. El bot seguirá corriendo en segundo plano.")
        print("Presiona Ctrl+C para detener completamente el bot.")
        while True:
            # Mantener el hilo principal vivo para que los hilos de fondo (ticker) sigan funcionando.
            time.sleep(3600)

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
        
        # Ya no hay un hilo listener de teclas que detener.
        # stop_event = live_interactive_helpers.get_stop_key_listener_event()
        # stop_event.set()
        # if key_listener_hilo and key_listener_hilo.is_alive():
        #     key_listener_hilo.join(timeout=1.0)
        
        if bot_started and connection_ticker_module and connection_ticker_module._ticker_thread.is_alive():
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

# =============== FIN ARCHIVO: runners/live_interactive_runner.py (CORREGIDO Y COMPLETO) ===============