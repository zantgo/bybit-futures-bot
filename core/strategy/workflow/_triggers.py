"""
Módulo para la gestión de Hitos Condicionales (Triggers).

Responsabilidad: Comprobar en cada tick si alguno de los hitos con estado 'ACTIVE'
se ha cumplido. De ser así, ejecuta la acción correspondiente y desencadena la
lógica de cascada (completar, cancelar hermanos, activar hijos) a través del
Position Manager.
"""
import sys
import os
import datetime
import traceback

# --- INICIO DE CAMBIOS: Importaciones Adaptadas ---

# Ajustar sys.path para importaciones absolutas
if __name__ != "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(script_dir))))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

# Importar dependencias con rutas absolutas desde la raíz del proyecto
try:
    # Usamos la fachada 'pm.api' para interactuar con el Position Manager
    from core.strategy.pm import api as position_manager
    from core.logging import memory_logger
except ImportError as e:
    print(f"ERROR [Workflow Triggers Import]: Falló importación de dependencias: {e}")
    position_manager = None
    class MemoryLoggerFallback:
        def log(self, msg, level="INFO"): print(f"[{level}] {msg}")
    memory_logger = MemoryLoggerFallback()

# --- FIN DE CAMBIOS: Importaciones Adaptadas ---


# --- Lógica de Hitos ---

def check_conditional_triggers(current_price: float, timestamp: datetime.datetime):
    """
    Comprueba y ejecuta los hitos condicionales con estado 'ACTIVE'.
    """
    if not position_manager or not position_manager.is_initialized():
        return

    try:
        # 1. Obtener todos los hitos del árbol de decisiones.
        all_milestones = position_manager.get_all_milestones()
        if not all_milestones:
            return

        # 2. Filtrar solo aquellos que están 'ACTIVE' para su evaluación.
        active_milestones = [m for m in all_milestones if m.status == 'ACTIVE']
        
        for milestone in active_milestones:
            # Envolver el procesamiento de un solo hito en un try-except
            # para que uno defectuoso no detenga la comprobación de los demás.
            try:
                condition = milestone.condition
                action = milestone.action
                milestone_id = milestone.id

                # 3. Evaluar la condición del hito
                condition_met = False
                if condition.type == "PRICE_ABOVE" and current_price >= condition.value:
                    condition_met = True
                elif condition.type == "PRICE_BELOW" and current_price <= condition.value:
                    condition_met = True
                
                # 4. Si la condición se cumple, ejecutar la acción y la cascada
                if condition_met:
                    trigger_msg = f"HITO ALCANZADO: ID '{milestone_id}'. Condición '{condition.type}' ({condition.value}) cumplida con precio {current_price}"
                    memory_logger.log(trigger_msg, level="INFO")

                    # 4a. Ejecutar la acción específica del hito.
                    # La lógica de ejecución de acciones se mantiene idéntica.
                    _execute_milestone_action(action, milestone_id)
                    
                    # 4b. Procesar la finalización del hito para la lógica de cascada.
                    # Esto marcará el hito como 'COMPLETED', cancelará a sus hermanos
                    # y activará a sus hijos.
                    if milestone.one_shot:
                        position_manager.process_triggered_milestone(milestone_id)

            except Exception as e_single:
                milestone_id_err = getattr(milestone, 'id', 'desconocido')
                memory_logger.log(f"ERROR [Workflow Triggers]: Procesando hito ID '{milestone_id_err}': {e_single}", level="ERROR")
                memory_logger.log(f"Traceback: {traceback.format_exc()}", level="ERROR")

    except Exception as e_main:
        memory_logger.log(f"ERROR CRÍTICO [Workflow Triggers]: Obteniendo hitos del PM: {e_main}", level="ERROR")
        traceback.print_exc()


def _execute_milestone_action(action, milestone_id: str):
    """
    Función auxiliar para ejecutar la acción de un hito.
    Esta lógica es la misma que la versión anterior, pero encapsulada.
    """
    if not position_manager:
        return

    action_type = action.type
    action_params = action.params

    if action_type == "SET_MODE":
        position_manager.set_manual_trading_mode(**action_params)
    elif action_type == "START_MANUAL_TREND":
        position_manager.start_manual_trend(**action_params)
    elif action_type == "CLOSE_ALL_LONGS":
        position_manager.close_all_logical_positions('long', reason=f"HITO_{milestone_id}")
    elif action_type == "CLOSE_ALL_SHORTS":
        position_manager.close_all_logical_positions('short', reason=f"HITO_{milestone_id}")
    else:
        memory_logger.log(f"ADVERTENCIA: Tipo de acción desconocido '{action_type}' para hito '{milestone_id}'.", level="WARN")
        return

    action_msg = f"ACCIÓN DE HITO: '{action_type}' ejecutada con parámetros: {action_params}"
    memory_logger.log(action_msg, level="INFO")