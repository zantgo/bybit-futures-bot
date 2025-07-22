"""
Módulo responsable de la inicialización de los componentes core del bot.

Su responsabilidad es construir el grafo de objetos de la estrategia
(especialmente el PositionManager y sus dependencias) y asegurar que todos
los componentes estén listos antes de que el bot comience a operar.

v2.1: Se actualiza la firma para aceptar todas las dependencias inyectadas.
"""
from typing import Any, Tuple, Dict
import traceback

def initialize_core_components(
    operation_mode: str,
    base_size: float,
    initial_slots: int,
    # --- Módulos y Clases de Dependencia Inyectados ---
    # <<< INICIO DE LA CORRECCIÓN: AÑADIR TODOS LOS PARÁMETROS ESPERADOS >>>
    config_module: Any,
    utils_module: Any,
    memory_logger_module: Any,
    connection_ticker_module: Any,
    live_operations_module: Any,
    connection_manager_module: Any,
    closed_position_logger_module: Any,
    open_snapshot_logger_module: Any,
    signal_logger_module: Any,
    # Clases del PM
    PositionManager: Any,
    BalanceManager: Any,
    PositionState: Any,
    PositionExecutor: Any,
    # Módulos internos del PM (fachadas y helpers)
    position_manager_api_module: Any,
    pm_helpers_module: Any,
    pm_calculations_module: Any,
    # Módulos de Estrategia
    ta_manager_module: Any,
    event_processor_module: Any
    # <<< FIN DE LA CORRECCIÓN >>>
) -> Tuple[bool, str]:
    """
    Construye e inicializa los componentes esenciales del bot y devuelve el estado.
    """
    print("\n--- Inicializando Componentes Core para la Sesión Live ---")
    try:
        # --- 1. Verificaciones y Inicializaciones Previas ---
        if not connection_manager_module.get_initialized_accounts():
            return False, "No hay clientes API inicializados. No se puede continuar."

        ta_manager_module.initialize()

        if open_snapshot_logger_module and getattr(config_module, 'POSITION_LOG_OPEN_SNAPSHOT', False):
            open_snapshot_logger_module.initialize_logger()

        # --- 2. Construcción del Grafo de Objetos del PM ---
        print("Construyendo grafo de objetos del Position Manager...")

        balance_manager_instance = BalanceManager(
            config=config_module,
            utils=utils_module,
            live_operations=live_operations_module,
            connection_manager=connection_manager_module
        )
        
        position_state_instance = PositionState(
            config=config_module,
            utils=utils_module,
            live_operations=live_operations_module
        )
        
        # El PositionManager y su Executor tienen una dependencia circular que resolvemos en dos pasos.
        # Primero creamos el PM sin el executor.
        pm_instance = PositionManager(
            balance_manager=balance_manager_instance,
            position_state=position_state_instance,
            executor=None, # Se asignará después
            config=config_module,
            utils=utils_module,
            memory_logger=memory_logger_module,
            connection_ticker=connection_ticker_module,
            helpers=pm_helpers_module,
            live_operations=live_operations_module,
            connection_manager=connection_manager_module
        )

        # Luego creamos el Executor, pasándole la instancia del PM.
        executor_instance = PositionExecutor(
            config=config_module,
            utils=utils_module,
            balance_manager=balance_manager_instance,
            position_state=position_state_instance,
            state_manager=pm_instance, # Inyectamos la instancia del PM
            calculations=pm_calculations_module,
            helpers=pm_helpers_module,
            live_operations=live_operations_module,
            connection_manager=connection_manager_module,
            closed_position_logger=closed_position_logger_module
        )
        
        # Finalmente, completamos la instancia del PM asignándole su Executor.
        pm_instance._executor = executor_instance
        
        # --- 3. Inicialización de los Componentes Instanciados ---
        
        real_balances_for_init: Dict[str, Dict[str, Any]] = {}
        for acc_name in connection_manager_module.get_initialized_accounts():
            real_balances_for_init[acc_name] = {
                'unified_balance': live_operations_module.get_unified_account_balance_info(acc_name)
            }

        pm_instance.initialize(
            operation_mode=operation_mode,
            base_size=base_size,
            max_pos=initial_slots,
            real_balances=real_balances_for_init
        )

        # Inicializar la fachada API del PM (para la TUI)
        position_manager_api_module.init_pm_api(pm_instance)

        # Inicializar el Event Processor, inyectando la instancia del PM
        event_processor_module.initialize(
            operation_mode=operation_mode,
            pm_instance=pm_instance
        )

        # --- 4. Verificación Final ---
        if not position_manager_api_module.is_initialized():
            return False, "El Position Manager no se inicializó correctamente."

        print("Componentes Core inicializados con éxito.")
        return True, "Inicialización completa."

    except Exception as e:
        traceback.print_exc()
        return False, f"Fallo catastrófico durante la inicialización de componentes: {e}"