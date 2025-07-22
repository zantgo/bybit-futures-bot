# runner/_orchestrator.py

"""
Contiene la lógica principal para orquestar el modo Live Interactivo del bot.

Este orquestador actúa como el punto central que:
1. Llama al wizard de configuración.
2. Delega la inicialización de componentes a `_initializer`.
3. Inicia los hilos de operación y cede el control a la TUI.
4. Delega la secuencia de apagado a `_shutdown`.
"""
import time
import traceback
from typing import Optional, Dict, Any, TYPE_CHECKING

from core.menu import __init__LEGACY

# Módulos internos del runner para SRP
# ...
from . import _initializer
from . import _shutdown

# Type Hinting para las dependencias inyectadas por main.py
if TYPE_CHECKING:
    import config
    from core import utils
    from core.strategy import pm as position_manager
    from core.strategy import ta as ta_manager
    from core.strategy import _event_processor as event_processor_module
    from core.logging import _open_position_logger as open_snapshot_logger_module

# --- Función Principal del Runner ---

def run_live_interactive_mode(
    final_summary: Dict[str, Any],
    operation_mode: str,
    # --- Módulos de Dependencia Inyectados desde main.py ---
    config_module: Any,
    menu_module: Any,
    position_manager_module: Any,
    open_snapshot_logger_module: Any,
    event_processor_module: Any,
    ta_manager_module: Any,
    **kwargs # Captura argumentos extra no usados para evitar errores
):
    """
    Orquesta el inicio, ejecución y apagado del modo Live Interactivo.
    """
    bot_started = False
    connection_ticker_module = None

    try:
        # --- 1. Asistente de Configuración ---
        base_size, initial_slots = menu_module.run_trading_assistant_wizard()
        if base_size is None or initial_slots is None:
            print("[Live Runner] Saliendo, configuración no completada en el asistente.")
            return

        # --- 2. Inicialización de Componentes Core (Delegada) ---
        success, message = _initializer.initialize_core_components(
            operation_mode=operation_mode,
            base_size=base_size,
            initial_slots=initial_slots,
            config_module=config_module,
            ta_manager_module=ta_manager_module,
            open_snapshot_logger_module=open_snapshot_logger_module,
            position_manager_module=position_manager_module,
            event_processor_module=event_processor_module
        )
        if not success:
            raise RuntimeError(f"Fallo en la inicialización: {message}")
        
        bot_started = True
        time.sleep(1.5)

        # --- 3. Iniciar Hilos y Ceder Control a la TUI ---
        print("\n--- Iniciando Operación del Bot y Asistente Interactivo ---")
        from connection import ticker as connection_ticker
        connection_ticker_module = connection_ticker
        
        connection_ticker_module.start_ticker_thread(
            raw_event_callback=event_processor_module.process_event
        )

        menu_module.clear_screen()
        print("=" * 60)
        print("  EL BOT ESTÁ OPERATIVO Y PROCESANDO DATOS DE MERCADO".center(60))
        print("  Entrando en el Asistente de Trading Interactivo...".center(60))
        print("=" * 60)
        time.sleep(2)

        # Ceder el control total al bucle de la TUI. Esta función es bloqueante.
        menu_module.run_tui_menu_loop()

        # Si el usuario sale del menú, el bot sigue corriendo en segundo plano.
        menu_module.clear_screen()
        print("\n[Live Runner] Has salido del menú interactivo.")
        print("El bot continúa procesando datos de mercado en segundo plano.")
        print("Presiona Ctrl+C en esta terminal para detener completamente el bot.")
        
        # Mantener el hilo principal vivo para que los hilos de fondo sigan funcionando.
        while True:
            time.sleep(3600)

    except (KeyboardInterrupt, SystemExit):
        print("\n\n[Live Runner] Interrupción detectada. Iniciando secuencia de apagado...")
    except RuntimeError as e:
        print(f"\nERROR CRÍTICO EN TIEMPO DE EJECUCIÓN: {e}")
        traceback.print_exc()
    except Exception as e:
        print(f"\nERROR INESPERADO en Live Runner: {e}")
        traceback.print_exc()
    finally:
        # --- 4. Secuencia de Apagado Limpio (Delegada) ---
        _shutdown.perform_shutdown(
            final_summary=final_summary,
            bot_started=bot_started,
            config_module=config_module,
            connection_ticker_module=connection_ticker_module,
            position_manager_module=position_manager_module,
            open_snapshot_logger_module=open_snapshot_logger_module
        )