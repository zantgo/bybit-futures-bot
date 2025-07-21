# runner/_initializer.py

"""
Módulo responsable de la inicialización de los componentes core del bot.

Su única responsabilidad es asegurar que todos los módulos y gestores
necesarios estén listos y configurados antes de que el bot comience a operar.
"""
from typing import Any, Tuple

def initialize_core_components(
    operation_mode: str,
    base_size: float,
    initial_slots: int,
    # Módulos de dependencia inyectados
    config_module: Any,
    ta_manager_module: Any,
    open_snapshot_logger_module: Any,
    position_manager_module: Any,
    event_processor_module: Any
) -> Tuple[bool, str]:
    """
    Inicializa los componentes esenciales del bot y devuelve el estado.

    Returns:
        Tuple[bool, str]: (True si éxito, mensaje de estado)
    """
    print("\n--- Inicializando Componentes Core para la Sesión Live ---")
    try:
        from connection import manager as live_manager
        if not live_manager.get_initialized_accounts():
            return False, "No hay clientes API inicializados. No se puede continuar."

        # Inicializar Análisis Técnico
        ta_manager_module.initialize()

        # Inicializar Logger de Snapshots si está habilitado
        if open_snapshot_logger_module and getattr(config_module, 'POSITION_LOG_OPEN_SNAPSHOT', False):
            open_snapshot_logger_module.initialize_logger()

        # Inicializar el Position Manager con los parámetros del wizard
        position_manager_module.initialize(
            operation_mode=operation_mode,
            initial_real_state=None,  # El PM obtendrá los balances reales que necesite
            base_position_size_usdt_param=base_size,
            initial_max_logical_positions_param=initial_slots,
            stop_loss_event=None
        )

        # Inicializar el Event Processor
        event_processor_module.initialize(
            operation_mode=operation_mode
        )

        # Verificación final de la inicialización del PM
        if not position_manager_module.api.is_initialized():
            return False, "El Position Manager no se inicializó correctamente."

        print("Componentes Core inicializados con éxito.")
        return True, "Inicialización completa."

    except Exception as e:
        return False, f"Fallo durante la inicialización de componentes: {e}"