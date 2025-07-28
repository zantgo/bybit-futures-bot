"""
Módulo para la gestión de Triggers de la Operación Estratégica.

v6.0 (Modelo de Operación Estratégica Única):
- Se elimina por completo la lógica de evaluación de Hitos.
- La función `check_conditional_triggers` ha sido reescrita para una única
  responsabilidad: comprobar las condiciones de entrada y salida de la
  operación estratégica única gestionada por el Position Manager.
"""
import sys
import os
import datetime
import traceback
from typing import Any, Dict, Tuple, Optional

# --- Importaciones Adaptadas ---
if __name__ != "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(script_dir))))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

try:
    from core.strategy.pm import api as position_manager
    from core.logging import memory_logger
    # (COMENTADO) La entidad Hito ya no es necesaria.
    # from core.strategy.pm._entities import Hito 
    from core.strategy.pm._entities import Operacion # Importamos la nueva entidad
    from core import utils
except ImportError as e:
    print(f"ERROR [Workflow Triggers Import]: Falló importación de dependencias: {e}")
    position_manager = None
    utils = None
    class Operacion: pass
    class MemoryLoggerFallback:
        def log(self, msg, level="INFO"): print(f"[{level}] {msg}")
    memory_logger = MemoryLoggerFallback()

# --- INICIO DE LA MODIFICACIÓN: Nueva Lógica de Triggers para Operación Única ---

def check_conditional_triggers(current_price: float, timestamp: datetime.datetime):
    """
    Comprueba las condiciones de entrada y salida de la operación estratégica actual.
    """
    if not position_manager or not position_manager.is_initialized():
        return

    try:
        operacion = position_manager.get_operation()
        if not operacion:
            return

        # Escenario 1: La operación está EN_ESPERA, comprobamos su condición de entrada.
        if operacion.estado == 'EN_ESPERA':
            condition_met, reason = _evaluate_entry_condition(operacion, current_price)
            if condition_met:
                memory_logger.log(f"CONDICIÓN DE ENTRADA CUMPLIDA: {reason}", "INFO")
                # El PM se encargará de cambiar el estado a 'ACTIVA'.
                position_manager.force_start_operation()

        # Escenario 2: La operación está ACTIVA, comprobamos sus condiciones de salida.
        elif operacion.estado == 'ACTIVA':
            condition_met, reason = _evaluate_exit_conditions(operacion, current_price)
            if condition_met:
                memory_logger.log(f"CONDICIÓN DE SALIDA CUMPLIDA: {reason}", "INFO")
                # El PM se encargará de finalizar la operación.
                position_manager.force_stop_operation(close_positions=False) # Por defecto, no se cierran posiciones

    except Exception as e_main:
        memory_logger.log(f"ERROR CRÍTICO [Workflow Triggers]: {e_main}", level="ERROR")
        memory_logger.log(traceback.format_exc(), level="ERROR")


def _evaluate_entry_condition(operacion: Operacion, current_price: float) -> Tuple[bool, str]:
    """Evalúa la condición de entrada de la operación."""
    cond_type = operacion.tipo_cond_entrada
    cond_value = operacion.valor_cond_entrada

    if cond_type == 'MARKET':
        return True, "Activación inmediata por precio de mercado"
    
    if cond_value is None:
        return False, ""

    if cond_type == 'PRICE_ABOVE' and current_price > cond_value:
        return True, f"Precio ({current_price:.4f}) superó umbral de entrada ({cond_value:.4f})"
        
    if cond_type == 'PRICE_BELOW' and current_price < cond_value:
        return True, f"Precio ({current_price:.4f}) cayó por debajo de umbral de entrada ({cond_value:.4f})"
        
    return False, ""

def _evaluate_exit_conditions(operacion: Operacion, current_price: float) -> Tuple[bool, str]:
    """Evalúa todas las condiciones de salida de la operación."""
    
    # Comprobar límites de ROI
    summary = position_manager.get_position_summary()
    if summary and 'error' not in summary:
        current_op_roi = summary.get('operation_roi', 0.0)
        if operacion.tp_roi_pct is not None and current_op_roi >= operacion.tp_roi_pct:
            return True, f"TP por ROI alcanzado ({current_op_roi:.2f}% >= {operacion.tp_roi_pct}%)"
        if operacion.sl_roi_pct is not None and current_op_roi <= operacion.sl_roi_pct:
            return True, f"SL por ROI alcanzado ({current_op_roi:.2f}% <= {operacion.sl_roi_pct}%)"

    # Comprobar límite de trades
    if operacion.max_comercios is not None and operacion.comercios_cerrados_contador >= operacion.max_comercios:
        return True, f"Límite de {operacion.max_comercios} trades alcanzado"
    
    # Comprobar límite de tiempo
    start_time = operacion.tiempo_inicio_ejecucion
    if operacion.tiempo_maximo_min is not None and start_time:
        current_ts_utc = datetime.datetime.now(datetime.timezone.utc)
        elapsed_minutes = (current_ts_utc - start_time).total_seconds() / 60.0
        if elapsed_minutes >= operacion.tiempo_maximo_min:
            return True, f"Límite de duración de {operacion.tiempo_maximo_min} min alcanzado"
            
    return False, ""
