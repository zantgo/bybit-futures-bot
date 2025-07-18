# =============== INICIO ARCHIVO: live_runner.py (PUENTE) ===============
"""
Módulo puente para el modo Live Interactivo.

Este archivo se mantiene por retrocompatibilidad para que las llamadas desde `main.py`
no se rompan. Su única responsabilidad es importar y delegar la ejecución al
nuevo orquestador refactorizado ubicado en `runners/live_interactive_runner.py`.

Toda la lógica de ejecución real reside en el nuevo módulo.
"""
from typing import Optional, Dict, Any

def run_live_pre_start(
    final_summary: Dict[str, Any],
    operation_mode: str,
    # --- Módulos de Dependencia (se pasarán directamente) ---
    config_module: Any, 
    utils_module: Any,  
    menu_module: Any,   
    live_operations_module: Optional[Any],
    position_manager_module: Optional[Any],
    balance_manager_module: Optional[Any],
    position_state_module: Optional[Any],
    open_snapshot_logger_module: Optional[Any],
    event_processor_module: Optional[Any],
    ta_manager_module: Optional[Any]
) -> Optional[Any]:
    """
    Actúa como un puente, llamando a la nueva función principal del runner interactivo.
    """
    print("[Live Runner Bridge] Redirigiendo la ejecución al nuevo orquestador interactivo...")
    
    try:
        # Importar el nuevo runner refactorizado
        from runners import live_interactive_runner
        
        # Llamar a la función principal del nuevo runner, pasando todos los argumentos
        # tal como se recibieron.
        return live_interactive_runner.run_live_interactive_mode(
            final_summary=final_summary,
            operation_mode=operation_mode,
            config_module=config_module,
            utils_module=utils_module,
            menu_module=menu_module,
            live_operations_module=live_operations_module,
            position_manager_module=position_manager_module,
            balance_manager_module=balance_manager_module,
            position_state_module=position_state_module,
            open_snapshot_logger_module=open_snapshot_logger_module,
            event_processor_module=event_processor_module,
            ta_manager_module=ta_manager_module
        )
        
    except ImportError as e:
        print(f"ERROR CRITICO [Live Runner Bridge]: No se pudo importar el nuevo runner 'runners.live_interactive_runner'.")
        print(f"Detalle: {e}")
        # Asegúrate de que la estructura de directorios sea correcta y que `runners`
        # sea un paquete reconocible por Python (puede que necesite un archivo __init__.py vacío).
        return None
    except Exception as e:
        print(f"ERROR INESPERADO [Live Runner Bridge]: Ocurrió un error al delegar la ejecución.")
        print(f"Detalle: {e}")
        return None

# =============== FIN ARCHIVO: live_runner.py (PUENTE) ===============