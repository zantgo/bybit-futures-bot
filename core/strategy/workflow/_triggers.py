# core/strategy/workflow/_triggers.py

"""
Módulo para la gestión de Triggers Condicionales.

Responsabilidad: Comprobar en cada tick si alguna de las reglas de trigger
definidas por el usuario se ha cumplido y, de ser así, ejecutar la acción
correspondiente a través del Position Manager.
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
    from core.strategy import pm as position_manager
    from core.logging import memory_logger
except ImportError as e:
    print(f"ERROR [Workflow Triggers Import]: Falló importación de dependencias: {e}")
    position_manager = None
    class MemoryLoggerFallback:
        def log(self, msg, level="INFO"): print(f"[{level}] {msg}")
    memory_logger = MemoryLoggerFallback()

# --- FIN DE CAMBIOS: Importaciones Adaptadas ---


# --- Lógica de Triggers ---

def check_conditional_triggers(current_price: float, timestamp: datetime.datetime):
    """
    Comprueba y ejecuta los triggers condicionales activos.
    """
    if not position_manager or not position_manager.is_initialized():
        return

    try:
        triggers_to_check = position_manager.get_all_triggers()
        if not triggers_to_check:
            return

        for trigger in triggers_to_check:
            if not trigger.get("is_active", False):
                continue

            # Envolver el procesamiento de un solo trigger en un try-except
            # para que un trigger defectuoso no detenga la comprobación de los demás.
            try:
                condition = trigger.get("condition", {})
                action = trigger.get("action", {})
                trigger_id = trigger.get("id")
                one_shot = trigger.get("one_shot", True)

                condition_met = False
                cond_type = condition.get("type")
                cond_value = condition.get("value")

                if cond_type == "PRICE_ABOVE" and current_price >= cond_value:
                    condition_met = True
                elif cond_type == "PRICE_BELOW" and current_price <= cond_value:
                    condition_met = True
                
                if condition_met:
                    trigger_msg = f"TRIGGER CONDICIONAL ACTIVADO: {trigger_id}. Condición '{cond_type}' ({cond_value}) cumplida con precio actual {current_price}"
                    memory_logger.log(trigger_msg, level="INFO")

                    action_type = action.get("type")
                    action_params = action.get("params", {})

                    if action_type == "SET_MODE":
                        position_manager.set_manual_trading_mode(**action_params)
                    elif action_type == "START_MANUAL_TREND":
                        position_manager.start_manual_trend(**action_params)
                    elif action_type == "CLOSE_ALL_LONGS":
                        position_manager.close_all_logical_positions('long', reason=f"TRIGGER_{trigger_id}")
                    elif action_type == "CLOSE_ALL_SHORTS":
                        position_manager.close_all_logical_positions('short', reason=f"TRIGGER_{trigger_id}")
                    
                    action_msg = f"TRIGGER ACCION: '{action_type}' ejecutada con parámetros: {action_params}"
                    memory_logger.log(action_msg, level="INFO")

                    if one_shot:
                        position_manager.update_trigger_status(trigger_id, is_active=False)

            except Exception as e_single:
                trigger_id_err = trigger.get('id', 'desconocido')
                memory_logger.log(f"ERROR [Workflow Triggers]: Procesando trigger ID '{trigger_id_err}': {e_single}", level="ERROR")
                memory_logger.log(f"Traceback: {traceback.format_exc()}", level="ERROR")

    except Exception as e_main:
        memory_logger.log(f"ERROR CRÍTICO [Workflow Triggers]: Obteniendo triggers del PM: {e_main}", level="ERROR")
        traceback.print_exc()