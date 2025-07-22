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

# Módulos internos del runner para SRP
from . import _initializer
from . import _shutdown

# Type Hinting para las dependencias inyectadas por main.py
if TYPE_CHECKING:
    # Este bloque solo es para el análisis estático, no afecta la ejecución
    pass

def run_live_interactive_mode(
    final_summary: Dict[str, Any],
    operation_mode: str,
    # --- Módulos de Dependencia Inyectados desde main.py ---
    # La firma de la función ahora usa **kwargs para aceptar todas las dependencias
    # que main.py le pasa, sin necesidad de listarlas todas.
    **dependencies 
):
    """
    Orquesta el inicio, ejecución y apagado del modo Live Interactivo.
    """
    bot_started = False
    connection_ticker_module = None

    try:
        # <<< INICIO DE LA CORRECCIÓN >>>
        # Extraer las dependencias necesarias del diccionario kwargs
        menu_module = dependencies.get("menu_module") # Asumiendo que se inyecta con esta clave
        config_module = dependencies.get("config_module")
        event_processor_module = dependencies.get("event_processor_module")
        position_manager_api_module = dependencies.get("position_manager_api_module")
        # <<< FIN DE LA CORRECCIÓN >>>

        # --- 1. Asistente de Configuración ---
        # (Esta parte ahora la maneja `_main_controller` y `screens/_welcome`,
        # por lo que esta llamada puede ser obsoleta, pero la mantenemos por seguridad)
        
        # --- 2. Inicialización de Componentes Core (Delegada) ---
        success, message = _initializer.initialize_core_components(
            operation_mode=operation_mode,
            base_size=getattr(config_module, 'POSITION_BASE_SIZE_USDT'),
            initial_slots=getattr(config_module, 'POSITION_MAX_LOGICAL_POSITIONS'),
            **dependencies
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

        # El control ahora se cede en `_main_controller.py`
        # El resto de este bloque `try` se vuelve un bucle de espera.
        print("\n[Runner Orchestrator] El bot está operativo.")
        print("El control está en la Interfaz de Usuario en Terminal (TUI).")
        print("Presiona Ctrl+C en esta terminal para detener completamente el bot.")
        
        while True:
            time.sleep(3600)

    except (KeyboardInterrupt, SystemExit):
        print("\n\n[Orquestador] Interrupción detectada. Iniciando secuencia de apagado...")
    except RuntimeError as e:
        print(f"\nERROR CRÍTICO EN TIEMPO DE EJECUCIÓN: {e}")
        traceback.print_exc()
    except Exception as e:
        print(f"\nERROR INESPERADO en el Orquestador: {e}")
        traceback.print_exc()
    finally:
        # --- 4. Secuencia de Apagado Limpio (Delegada) ---
        _shutdown.perform_shutdown(
            final_summary=final_summary,
            bot_started=bot_started,
            # <<< INICIO DE LA CORRECCIÓN >>>
            config_module=dependencies.get("config_module"),
            connection_ticker_module=dependencies.get("connection_ticker_module"),
            position_manager_module=dependencies.get("position_manager_api_module"),
            open_snapshot_logger_module=dependencies.get("open_snapshot_logger_module")
            # <<< FIN DE LA CORRECCIÓN >>>
        )