# runner/__init__.py

"""
Contiene la lógica principal para orquestar el modo Live Interactivo del bot.

Este runner ha sido masivamente simplificado. Su única responsabilidad
es actuar como un lanzador para la nueva TUI (Terminal User Interface).
- Llama al asistente de configuración inicial.
- Si la configuración es exitosa, inicializa los componentes del bot.
- Finalmente, cede el control por completo al bucle principal del menú interactivo.
"""
import time
import traceback
from typing import Optional, Dict, Any, TYPE_CHECKING
import os
import sys

# --- INICIO DE CAMBIOS: Importaciones Adaptadas ---

# Ajustar sys.path para permitir importaciones absolutas desde la raíz del proyecto.
if __name__ != "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir) # Raíz del proyecto
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

# Type Hinting para las dependencias inyectadas por main.py, usando las nuevas rutas
if TYPE_CHECKING:
    import config
    from core import utils, api as live_operations
    from core import menu
    from core.strategy import pm as position_manager
    from core.strategy.pm import _balance as balance_manager_module
    from core.strategy.pm import _position_state as position_state_module
    from core.strategy import ta as ta_manager
    from core.strategy import _event_processor as event_processor_module
    from core.logging import _open_position_logger as open_snapshot_logger_module

# --- FIN DE CAMBIOS: Importaciones Adaptadas ---


# --- Función Principal del Runner ---

def run_live_interactive_mode(
    final_summary: Dict[str, Any],
    operation_mode: str,
    # --- Módulos de Dependencia Inyectados desde main.py ---
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
    """
    Orquesta el inicio y la ejecución del modo Live Interactivo.
    """
    connection_ticker_module: Optional[Any] = None
    bot_started: bool = False

    try:
        # --- 1. Lanzar el Asistente de Configuración Inicial (Wizard TUI) ---
        # La nueva TUI maneja toda la configuración inicial.
        # Devuelve los parámetros clave si el usuario confirma, o None si cancela.
        base_size, initial_slots = menu_module.run_trading_assistant_wizard()

        if base_size is None or initial_slots is None:
            print("[Live Runner] Saliendo, configuración no completada en el asistente.")
            return

        # --- 2. Inicialización de Componentes Core ---
        print("\n--- Inicializando Componentes Core para la Sesión Live ---")

        try:
            # --- INICIO DE CAMBIOS: Importación adaptada ---
            from connection import manager as live_manager
            from connection import ticker as connection_ticker
            # --- FIN DE CAMBIOS ---
            connection_ticker_module = connection_ticker
        except ImportError:
            raise RuntimeError("Módulos de conexión (manager, ticker) no encontrados.")

        if not live_manager.get_initialized_accounts():
            raise RuntimeError("No hay clientes API inicializados. No se puede continuar en modo live.")

        ta_manager_module.initialize()
        if open_snapshot_logger_module and getattr(config_module, 'POSITION_LOG_OPEN_SNAPSHOT', False):
            open_snapshot_logger_module.initialize_logger()

        # Inicializar el Position Manager con los parámetros obtenidos del wizard
        position_manager_module.initialize(
            operation_mode=operation_mode,
            initial_real_state=None, # El PM obtendrá los balances reales que necesite
            base_position_size_usdt_param=base_size,
            initial_max_logical_positions_param=initial_slots,
            stop_loss_event=None
        )

        # Inicializar el Event Processor (ahora más simple en modo live)
        event_processor_module.initialize(
            operation_mode=operation_mode
        )

        if not position_manager_module.is_initialized():
            raise RuntimeError("El Position Manager no se inicializó correctamente.")

        bot_started = True
        print("Componentes Core inicializados con éxito.")
        time.sleep(1.5)

        # --- 3. Iniciar Hilos y Ceder Control a la TUI ---
        print("\n--- Iniciando Operación del Bot y Asistente Interactivo ---")
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

        # Si el usuario sale del menú (presionando 'q' o ESC), el bot sigue corriendo.
        menu_module.clear_screen()
        print("\n[Live Runner] Has salido del menú interactivo.")
        print("El bot continúa procesando datos de mercado en segundo plano.")
        print("Presiona Ctrl+C en esta terminal para detener completamente el bot.")
        
        # Mantener el hilo principal vivo para que los hilos de fondo (ticker) sigan funcionando.
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
        # --- 4. Secuencia de Apagado Limpio ---
        print("\n--- Limpieza Final del Live Runner ---")

        if bot_started and connection_ticker_module:
            # Comprobación más segura para el objeto del hilo
            if hasattr(connection_ticker_module, '_ticker_thread') and connection_ticker_module._ticker_thread and connection_ticker_module._ticker_thread.is_alive():
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