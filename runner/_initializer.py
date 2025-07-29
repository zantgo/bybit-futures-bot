"""
Módulo responsable de la inicialización de los componentes core del bot.

v3.4 (Arquitectura de OM/PM):
- Esta función ahora es responsable de instanciar tanto el OperationManager (OM)
  como el PositionManager (PM).
- Inyecta la API del OM como una dependencia en el PM, completando la
  separación de responsabilidades.
"""
# (COMENTARIO) Docstring de la versión anterior (v3.3) para referencia:
# """
# Módulo responsable de la inicialización de los componentes core del bot.
# 
# v3.3 (Robustez):
# - Añadida validación explícita para la dependencia `event_processor_module`
#   para prevenir errores de `AttributeError` durante la inicialización.
# """
from typing import Any, Tuple, Dict
import traceback
import types

from core.exchange import AbstractExchange

def initialize_core_components(
    operation_mode: str,
    base_size: float,
    initial_slots: int,
    **dependencies: Any
) -> Tuple[bool, str, Any]:
    """
    Construye e inicializa los componentes esenciales del bot y devuelve el estado
    y la instancia del adaptador de exchange creada.
    """
    print("\n--- Inicializando Componentes Core para la Sesión Live ---")
    
    memory_logger_module = dependencies.get('memory_logger_module')
    
    try:
        # --- Extracción de dependencias ---
        config_module = dependencies['config_module']
        utils_module = dependencies['utils_module']
        connection_manager_module = dependencies['connection_manager_module']
        open_snapshot_logger_module = dependencies.get('open_snapshot_logger_module')
        closed_position_logger_module = dependencies.get('closed_position_logger_module')
        
        # --- INICIO DE LA MODIFICACIÓN: Extraer dependencias del OM ---
        OperationManager = dependencies['OperationManager']
        operation_manager_api_module = dependencies['operation_manager_api_module']
        # --- FIN DE LA MODIFICACIÓN ---
        
        PositionManager = dependencies['PositionManager']
        BalanceManager = dependencies['BalanceManager']
        PositionState = dependencies['PositionState']
        PositionExecutor = dependencies['PositionExecutor']
        
        position_manager_api_module = dependencies['position_manager_api_module']
        pm_helpers_module = dependencies['pm_helpers_module']
        pm_calculations_module = dependencies['pm_calculations_module']
        
        ta_manager_module = dependencies['ta_manager_module']
        event_processor_module = dependencies['event_processor_module']

        if not isinstance(event_processor_module, types.ModuleType) or not hasattr(event_processor_module, 'initialize'):
            error_msg = "La dependencia 'event_processor_module' es inválida o no tiene la función 'initialize'."
            if memory_logger_module:
                memory_logger_module.log(f"ERROR FATAL: {error_msg}", "ERROR")
            return False, error_msg, None

        if not connection_manager_module.get_initialized_accounts():
            return False, "No hay clientes API inicializados. No se puede continuar.", None

        ta_manager_module.initialize()
        pm_helpers_module.set_dependencies(config_module, utils_module)

        print("Creando adaptador de exchange...")
        exchange_name = getattr(config_module, 'EXCHANGE_NAME', 'bybit').lower()
        exchange_adapter = None
        if exchange_name == 'bybit':
            from core.exchange._bybit_adapter import BybitAdapter
            exchange_adapter = BybitAdapter()
            symbol = getattr(config_module, 'TICKER_SYMBOL')
            if not exchange_adapter.initialize(symbol):
                return False, f"Fallo al inicializar el adaptador de Bybit.", None
        else:
            return False, f"Exchange '{exchange_name}' no soportado.", None
        print(f"Adaptador para '{exchange_name.upper()}' creado e inicializado con éxito.")

        # --- INICIO DE LA MODIFICACIÓN: Instanciar el OperationManager PRIMERO ---
        print("Instanciando Operation Manager...")
        om_instance = OperationManager(
            config=config_module,
            memory_logger_instance=memory_logger_module
        )
        operation_manager_api_module.init_om_api(om_instance)
        print("Operation Manager inicializado.")
        # --- FIN DE LA MODIFICACIÓN ---

        print("Construyendo grafo de objetos del Position Manager...")
        balance_manager_instance = BalanceManager(
            config=config_module,
            utils=utils_module,
            exchange_adapter=exchange_adapter
        )
        position_state_instance = PositionState(
            config=config_module,
            utils=utils_module,
            exchange_adapter=exchange_adapter
        )
        
        # --- INICIO DE LA MODIFICACIÓN: Inyectar la API del OM en el PM ---
        pm_instance = PositionManager(
            balance_manager=balance_manager_instance,
            position_state=position_state_instance,
            exchange_adapter=exchange_adapter,
            config=config_module,
            utils=utils_module,
            memory_logger=memory_logger_module,
            helpers=pm_helpers_module,
            operation_manager_api=operation_manager_api_module # <-- NUEVA DEPENDENCIA
        )
        # --- FIN DE LA MODIFICACIÓN ---

        executor_instance = PositionExecutor(
            config=config_module,
            utils=utils_module,
            balance_manager=balance_manager_instance,
            position_state=position_state_instance,
            exchange_adapter=exchange_adapter,
            calculations=pm_calculations_module,
            helpers=pm_helpers_module,
            closed_position_logger=closed_position_logger_module,
            state_manager=pm_instance
        )
        pm_instance.set_executor(executor_instance)
        
        balance_manager_instance.initialize(
            base_position_size_usdt=base_size,
            initial_max_logical_positions=initial_slots
        )
        
        # El PM ahora solo inicializa su propio estado, no la operación.
        pm_instance.initialize(operation_mode=operation_mode)

        position_manager_api_module.init_pm_api(pm_instance)
        
        event_processor_module.initialize(
            operation_mode=operation_mode,
            pm_instance=pm_instance,
            # (NOTA: El event_processor no necesita el om_instance directamente,
            # ya que su workflow (_triggers) importa la API de forma estática)
        )

        if not position_manager_api_module.is_initialized() or not operation_manager_api_module.is_initialized():
            return False, "El Position Manager o el Operation Manager no se inicializaron correctamente.", None

        print("Componentes Core inicializados con éxito.")
        return True, "Inicialización completa.", exchange_adapter

    except Exception as e:
        if memory_logger_module:
            memory_logger_module.log(f"Fallo catastrófico durante la inicialización de componentes: {e}", "ERROR")
            memory_logger_module.log(traceback.format_exc(), "ERROR")
        else:
            traceback.print_exc()
        return False, f"Fallo catastrófico durante la inicialización de componentes: {e}", None