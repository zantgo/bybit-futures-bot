"""
Contiene la lógica principal para orquestar el modo Live Interactivo del bot.

Este orquestador actúa como el punto central que:
1. Delega la inicialización de componentes a `_initializer`.
2. Inicia los hilos de operación (ticker) y cede el control a la TUI.
3. Delega la secuencia de apagado a `_shutdown`.
"""
import time
import traceback
from typing import Dict, Any

# Módulos internos del runner para SRP
from . import _initializer
from . import _shutdown

def run_live_interactive_mode(
    final_summary: Dict[str, Any],
    operation_mode: str,
    # Acepta todas las dependencias inyectadas desde main.py
    **dependencies 
):
    """
    Orquesta el inicio, ejecución y apagado del modo Live Interactivo.
    """
    bot_started = False

    try:
        # Extraer dependencias clave para claridad
        config_module = dependencies.get("config_module")
        event_processor_module = dependencies.get("event_processor_module")
        connection_ticker_module = dependencies.get("connection_ticker_module")

        # --- 1. Inicialización de Componentes Core (Delegada) ---
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

        # --- 2. Iniciar Hilos y Ceder Control a la TUI ---
        print("\n--- Iniciando Operación del Bot y Asistente Interactivo ---")
        
        # El adaptador fue creado y añadido a las dependencias en el inicializador
        exchange_adapter = dependencies.get("exchange_adapter")
        if not exchange_adapter:
            raise RuntimeError("El adaptador de exchange no fue creado durante la inicialización.")
        
        # El ticker ahora recibe el adaptador agnóstico en lugar de buscar la sesión por sí mismo
        connection_ticker_module.start_ticker_thread(
            exchange_adapter=exchange_adapter,
            raw_event_callback=event_processor_module.process_event
        )

        # Ceder control al bucle de espera
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
        # --- 3. Secuencia de Apagado Limpio (Delegada) ---
        _shutdown.perform_shutdown(
            final_summary=final_summary,
            bot_started=bot_started,
            config_module=dependencies.get("config_module"),
            connection_ticker_module=dependencies.get("connection_ticker_module"),
            position_manager_module=dependencies.get("position_manager_api_module"),
            open_snapshot_logger_module=dependencies.get("open_snapshot_logger_module")
        )