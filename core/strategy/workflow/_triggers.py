# core/strategy/workflow/_triggers.py

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
from typing import Any, Dict

# --- INICIO DE CAMBIOS: Importaciones Adaptadas ---

# Ajustar sys.path para importaciones absolutas
if __name__ != "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(script_dir))))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

# Importar dependencias con rutas absolutas desde la raíz del proyecto
try:
    from core.strategy.pm import api as position_manager
    from core.logging import memory_logger
    # --- INICIO DE LA MODIFICACIÓN: Importar entidades para el tipado y utils ---
    from core.strategy.pm._entities import Hito
    from core import utils
    # --- FIN DE LA MODIFICACIÓN ---
except ImportError as e:
    print(f"ERROR [Workflow Triggers Import]: Falló importación de dependencias: {e}")
    position_manager = None
    utils = None
    class Hito: pass
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
        operation_state = position_manager.get_operation_state()
        if not operation_state or 'error' in operation_state:
            return

        all_milestones = position_manager.get_all_milestones()
        if not all_milestones:
            return

        # --- INICIO DE LA MODIFICACIÓN: Filtrado basado en el estado de la operación ---
        current_tendencia = operation_state.get('configuracion', {}).get('tendencia', 'NEUTRAL')
        
        # Determinar qué tipo de hito buscar
        tipo_hito_a_evaluar = 'INICIALIZACION' if current_tendencia == 'NEUTRAL' else 'FINALIZACION'
        
        active_milestones_to_check = [
            m for m in all_milestones 
            if m.status == 'ACTIVE' and m.tipo_hito == tipo_hito_a_evaluar
        ]
        # --- FIN DE LA MODIFICACIÓN ---

        for hito in active_milestones_to_check:
            try:
                # --- INICIO DE LA MODIFICACIÓN: Lógica de evaluación delegada ---
                condition_met, reason = _evaluate_milestone_conditions(hito, current_price, timestamp, operation_state)
                
                if condition_met:
                    trigger_msg = f"HITO ALCANZADO: ID ...{hito.id[-6:]}. Razón: {reason}"
                    memory_logger.log(trigger_msg, level="INFO")

                    # La única acción es notificar al PM. Él se encarga del resto.
                    if hito.one_shot:
                        position_manager.process_triggered_milestone(hito.id)
                # --- FIN DE LA MODIFICACIÓN ---

            except Exception as e_single:
                milestone_id_err = getattr(hito, 'id', 'desconocido')
                memory_logger.log(f"ERROR [Workflow Triggers]: Procesando hito ID '{milestone_id_err}': {e_single}", level="ERROR")
                memory_logger.log(f"Traceback: {traceback.format_exc()}", level="ERROR")

    except Exception as e_main:
        memory_logger.log(f"ERROR CRÍTICO [Workflow Triggers]: Obteniendo estado del PM: {e_main}", level="ERROR")
        memory_logger.log(traceback.format_exc(), level="ERROR")


def _evaluate_milestone_conditions(hito: Hito, current_price: float, timestamp: datetime.datetime, operation_state: Dict[str, Any]) -> (bool, str):
    """
    Función auxiliar que contiene la lógica para evaluar todas las condiciones de un hito.
    Devuelve (True, "razón") si se cumple, o (False, "") si no.
    """
    cond = hito.condicion

    if hito.tipo_hito == 'INICIALIZACION' and cond.condicion_precio:
        # Lógica para Hitos de Inicialización (solo precio)
        return _evaluate_price_condition(cond.condicion_precio, current_price, hito.id)

    elif hito.tipo_hito == 'FINALIZACION':
        # Lógica para Hitos de Finalización (múltiples condiciones)
        
        # 1. Comprobar límites de la operación
        op_summary = position_manager.get_position_summary() # Necesitamos el ROI calculado
        if op_summary:
            current_op_roi = op_summary.get('operation_roi', 0.0)
            if cond.tp_roi_pct is not None and current_op_roi >= cond.tp_roi_pct:
                return True, f"TP por ROI de Operación alcanzado ({current_op_roi:.2f}% >= {cond.tp_roi_pct}%)"
            if cond.sl_roi_pct is not None and current_op_roi <= cond.sl_roi_pct:
                return True, f"SL por ROI de Operación alcanzado ({current_op_roi:.2f}% <= {cond.sl_roi_pct}%)"

        if cond.max_comercios is not None and operation_state.get('comercios_cerrados_contador', 0) >= cond.max_comercios:
            return True, f"Límite de {cond.max_comercios} trades alcanzado"
        
        start_time = operation_state.get('tiempo_inicio_ejecucion')
        if cond.tiempo_maximo_min is not None and start_time:
            elapsed_minutes = (timestamp - start_time).total_seconds() / 60.0
            if elapsed_minutes >= cond.tiempo_maximo_min:
                return True, f"Límite de duración de {cond.tiempo_maximo_min} min alcanzado"

        # 2. Comprobar condición de precio opcional
        if cond.condicion_precio:
            price_met, price_reason = _evaluate_price_condition(cond.condicion_precio, current_price, hito.id)
            if price_met:
                return True, price_reason

    return False, ""


def _evaluate_price_condition(price_cond, current_price: float, hito_id: str) -> (bool, str):
    """Evalúa la condición de precio de dos pasos."""
    # Resolver 'market_price'
    mayor_a = current_price if price_cond.activacion_mayor_a == 'market_price' else price_cond.activacion_mayor_a
    menor_a = current_price if price_cond.activacion_menor_a == 'market_price' else price_cond.activacion_menor_a

    # Paso 1: "Armar" la condición (se cumple el primer requisito)
    if not price_cond.estado_mayor_a_cumplido and current_price > mayor_a:
        price_cond.estado_mayor_a_cumplido = True
        memory_logger.log(f"Hito ...{hito_id[-6:]}: Condición 'mayor a {mayor_a}' cumplida. Esperando 'menor a'.", "DEBUG")

    if not price_cond.estado_menor_a_cumplido and current_price < menor_a:
        price_cond.estado_menor_a_cumplido = True
        memory_logger.log(f"Hito ...{hito_id[-6:]}: Condición 'menor a {menor_a}' cumplida. Esperando 'mayor a'.", "DEBUG")

    # Paso 2: "Disparar" la condición (se cumplen ambos requisitos)
    if price_cond.estado_mayor_a_cumplido and current_price < menor_a:
        return True, f"Precio superó {mayor_a} y luego bajó de {menor_a} (actual: {current_price})"
    
    if price_cond.estado_menor_a_cumplido and current_price > mayor_a:
        return True, f"Precio bajó de {menor_a} y luego superó {mayor_a} (actual: {current_price})"
        
    return False, ""


# --- (COMENTADO) _execute_milestone_action ---
# La lógica de esta función ahora reside en `process_triggered_milestone` en el PM.
# def _execute_milestone_action(action, milestone_id: str):
#     """
#     Función auxiliar para ejecutar la acción de un hito.
#     Esta lógica es la misma que la versión anterior, pero encapsulada.
#     """
#     if not position_manager:
#         return

#     action_type = action.type
#     action_params = action.params

#     if action_type == "SET_MODE":
#         position_manager.set_manual_trading_mode(**action_params)
#     elif action_type == "START_MANUAL_TREND":
#         position_manager.start_manual_trend(**action_params)
#     elif action_type == "CLOSE_ALL_LONGS":
#         position_manager.close_all_logical_positions('long', reason=f"HITO_{milestone_id}")
#     elif action_type == "CLOSE_ALL_SHORTS":
#         position_manager.close_all_logical_positions('short', reason=f"HITO_{milestone_id}")
#     else:
#         memory_logger.log(f"ADVERTENCIA: Tipo de acción desconocido '{action_type}' para hito '{milestone_id}'.", level="WARN")
#         return

#     action_msg = f"ACCIÓN DE HITO: '{action_type}' ejecutada con parámetros: {action_params}"
#     memory_logger.log(action_msg, level="INFO")