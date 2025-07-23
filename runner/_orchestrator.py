"""
Contiene la lógica principal para orquestar el ciclo de vida del backend del bot.

Este orquestador actúa como el punto central que, llamado por el controlador
de la TUI, se encarga de:
1. Delegar la inicialización de todos los componentes core a `_initializer`.
2. Iniciar los hilos de operación en segundo plano (como el ticker).
3. Delegar la secuencia de apagado a `_shutdown` cuando se le notifica.

v2.0 (Refactor): La responsabilidad del bucle de espera infinito y la captura
de KeyboardInterrupt ha sido transferida al `_main_controller` de la TUI, que
es el verdadero punto de control del ciclo de vida de la aplicación.
"""
import time
import traceback
from typing import Dict, Any, Tuple

# Módulos internos del runner para SRP
from . import _initializer
from . import _shutdown

def initialize_and_run_backend(
    operation_mode: str,
    # Acepta todas las dependencias inyectadas desde main.py
    **dependencies
) -> Tuple[bool, str]:
    """
    Orquesta la inicialización completa del backend y el arranque de los
    servicios en segundo plano (hilos).

    Devuelve un booleano indicando el éxito y un mensaje.
    """
    try:
        # Extraer dependencias clave para claridad
        config_module = dependencies.get("config_module")
        event_processor_module = dependencies.get("event_processor_module")
        connection_ticker_module = dependencies.get("connection_ticker_module")

        # --- 1. Inicialización de Componentes Core (Delegada) ---
        print("\n--- [Orchestrator] Inicializando Componentes Core ---")
        success, message = _initializer.initialize_core_components(
            operation_mode=operation_mode,
            base_size=getattr(config_module, 'POSITION_BASE_SIZE_USDT'),
            initial_slots=getattr(config_module, 'POSITION_MAX_LOGICAL_POSITIONS'),
            **dependencies
        )
        if not success:
            # Devuelve el fallo para que el controlador principal lo maneje
            return False, f"Fallo en la inicialización de componentes: {message}"
        
        time.sleep(1.5)

        # --- 2. Iniciar Hilos de Operación ---
        print("\n--- [Orchestrator] Iniciando Hilos de Operación (Ticker) ---")
        
        # El adaptador fue creado y añadido a las dependencias en el inicializador
        exchange_adapter = dependencies.get("exchange_adapter")
        if not exchange_adapter:
            raise RuntimeError("El adaptador de exchange no fue creado durante la inicialización.")
        
        # El ticker ahora recibe el adaptador agnóstico
        connection_ticker_module.start_ticker_thread(
            exchange_adapter=exchange_adapter,
            raw_event_callback=event_processor_module.process_event
        )
        
        print("[Orchestrator] Backend operativo. El control vuelve a la TUI.")
        return True, "Backend inicializado y corriendo."

    except RuntimeError as e:
        # Errores esperados o de validación
        traceback.print_exc()
        return False, str(e)
    except Exception as e:
        # Errores inesperados
        print(f"\nERROR INESPERADO en el Orquestador del Backend: {e}")
        traceback.print_exc()
        return False, f"Error inesperado: {e}"

# La función `perform_shutdown` ya está en `_shutdown.py` y es importada por
# el `__init__.py` del runner, por lo que no es necesario tener una copia aquí.
# El bucle `while True` y el bloque `finally` han sido eliminados porque su
# lógica ahora reside en el `_main_controller.py`.