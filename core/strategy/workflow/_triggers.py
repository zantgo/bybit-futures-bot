"""
Módulo para la gestión de Hitos Condicionales (Triggers).

v5.4 (Restauración de Lógica "Primero Gana"):
- Se restaura la lógica de evaluación para que se detenga en el primer hito
  que cumple su condición en un tick.
- Los hitos se evalúan en orden de creación para asegurar predictibilidad.
- La responsabilidad de cancelar a los "hermanos" recae enteramente en la
  función de cascada `process_triggered_milestone`, que ahora es más robusta.
"""
import sys
import os
import datetime
import traceback
from typing import Any, Dict, Tuple, Optional, List

# --- Importaciones Adaptadas ---
if __name__ != "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(script_dir))))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

try:
    from core.strategy.pm import api as position_manager
    from core.logging import memory_logger
    from core.strategy.pm._entities import Hito
    from core import utils
except ImportError as e:
    print(f"ERROR [Workflow Triggers Import]: Falló importación de dependencias: {e}")
    position_manager = None
    utils = None
    class Hito: pass
    class MemoryLoggerFallback:
        def log(self, msg, level="INFO"): print(f"[{level}] {msg}")
    memory_logger = MemoryLoggerFallback()

# --- Lógica de Hitos ---

def check_conditional_triggers(current_price: float, timestamp: datetime.datetime):
    """
    Comprueba y ejecuta el primer hito 'ARMADO' cuya condición se cumpla.
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

        current_tendencia = operation_state.get('configuracion', {}).get('tendencia', 'NEUTRAL')
        tipo_hito_a_evaluar = 'INICIALIZACION' if current_tendencia == 'NEUTRAL' else 'FINALIZACION'
        
        # --- INICIO DE LA CORRECCIÓN: Volver a la lógica de "el primero gana" ---
        # 1. Filtrar los hitos relevantes y ordenarlos por fecha de creación.
        #    Esto asegura que siempre se evalúe primero el que se creó antes.
        active_milestones_to_check = sorted(
            [m for m in all_milestones if m.status == 'ACTIVE' and m.tipo_hito == tipo_hito_a_evaluar],
            key=lambda m: m.created_at
        )

        # 2. Iterar y detenerse en el primer hito que se cumpla.
        for hito in active_milestones_to_check:
            try:
                condition_met, reason = _evaluate_milestone_conditions(hito, current_price, timestamp, operation_state)
                
                if condition_met:
                    trigger_msg = f"HITO ALCANZADO: ID ...{hito.id[-6:]}. Razón: {reason}"
                    memory_logger.log(trigger_msg, level="INFO")

                    if hito.one_shot:
                        position_manager.process_triggered_milestone(hito.id)
                    
                    # 3. Romper el bucle. Esto es crucial. Solo se procesa UN hito por tick.
                    #    La lógica de cascada en el PM se encargará del resto.
                    break

            except Exception as e_single:
                milestone_id_err = getattr(hito, 'id', 'desconocido')
                memory_logger.log(f"ERROR [Workflow Triggers]: Procesando hito ID '{milestone_id_err}': {e_single}", level="ERROR")
                memory_logger.log(f"Traceback: {traceback.format_exc()}", level="ERROR")
        # --- FIN DE LA CORRECCIÓN ---

    except Exception as e_main:
        memory_logger.log(f"ERROR CRÍTICO [Workflow Triggers]: Obteniendo estado del PM: {e_main}", level="ERROR")
        memory_logger.log(traceback.format_exc(), level="ERROR")


def _evaluate_milestone_conditions(hito: Hito, current_price: float, timestamp: datetime.datetime, operation_state: Dict[str, Any]) -> Tuple[bool, str]:
    # (Esta función se mantiene sin cambios, es correcta)
    cond = hito.condicion
    if cond.tipo_condicion_precio:
        price_met, price_reason = _evaluate_price_condition(cond.tipo_condicion_precio, cond.valor_condicion_precio, current_price)
        if price_met: return True, price_reason
    if hito.tipo_hito == 'FINALIZACION':
        op_summary = position_manager.get_position_summary()
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
            if timestamp.tzinfo is None and start_time.tzinfo is not None:
                 timestamp = timestamp.replace(tzinfo=start_time.tzinfo)
            elapsed_minutes = (timestamp - start_time).total_seconds() / 60.0
            if elapsed_minutes >= cond.tiempo_maximo_min:
                return True, f"Límite de duración de {cond.tiempo_maximo_min} min alcanzado"
    return False, ""

def _evaluate_price_condition(cond_type: Optional[str], cond_value: Optional[float], current_price: float) -> Tuple[bool, str]:
    # (Esta función se mantiene sin cambios, es correcta)
    if cond_type == 'MARKET': return True, "Activación inmediata por precio de mercado"
    if cond_value is None: return False, ""
    if cond_type == 'PRICE_ABOVE' and current_price > cond_value:
        return True, f"Precio ({current_price:.4f}) superó el umbral ({cond_value:.4f})"
    if cond_type == 'PRICE_BELOW' and current_price < cond_value:
        return True, f"Precio ({current_price:.4f}) cayó por debajo del umbral ({cond_value:.4f})"
    return False, ""