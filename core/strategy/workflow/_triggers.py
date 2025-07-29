"""
Módulo para la gestión de Triggers de la Operación Estratégica.

v6.2 (Separación de Responsabilidades):
- Este módulo ahora importa y utiliza la nueva API del Operation Manager (`om_api`)
  para gestionar el ciclo de vida de la operación (iniciar/detener).
- Mantiene la dependencia con `pm_api` únicamente para obtener el resumen de
  posiciones necesario para el cálculo del ROI de salida.
- Se elimina la importación directa de la entidad `Operacion` desde `pm`,
  ya que ahora la obtiene a través de la `om_api`.
"""
# (COMENTARIO) Docstring de la versión anterior (v6.1) para referencia:
# """
# Módulo para la gestión de Triggers de la Operación Estratégica.
# 
# v6.1 (Condición de Salida por Precio):
# - La función `_evaluate_exit_conditions` ha sido actualizada para comprobar
#   la nueva condición de salida por precio (`tipo_cond_salida` y
#   `valor_cond_salida`) definida en la entidad `Operacion`.
# """
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
    # --- INICIO DE LA MODIFICACIÓN: Actualizar importaciones ---
    from core.strategy.pm import api as pm_api # Mantenemos para summary
    from core.strategy.om import api as om_api # Nueva API para la operación
    from core.strategy.om._entities import Operacion # La entidad ahora vive en 'om'
    from core.logging import memory_logger
    from core import utils
    # (COMENTADO) Importaciones antiguas para referencia
    # from core.strategy.pm import api as position_manager
    # from core.strategy.pm._entities import Operacion
    # --- FIN DE LA MODIFICACIÓN ---
except ImportError as e:
    print(f"ERROR [Workflow Triggers Import]: Falló importación de dependencias: {e}")
    pm_api = None
    om_api = None
    utils = None
    class Operacion: pass
    class MemoryLoggerFallback:
        def log(self, msg, level="INFO"): print(f"[{level}] {msg}")
    memory_logger = MemoryLoggerFallback()

# --- Lógica de Triggers para Operación Única ---

def check_conditional_triggers(current_price: float, timestamp: datetime.datetime):
    """
    Comprueba las condiciones de entrada y salida de la operación estratégica actual.
    """
    # --- INICIO DE LA MODIFICACIÓN: Usar ambas APIs ---
    if not pm_api or not pm_api.is_initialized() or not om_api or not om_api.is_initialized():
        return

    try:
        # La operación se obtiene de la nueva om_api
        operacion = om_api.get_operation()
        if not operacion:
            return

        # Escenario 1: La operación está EN_ESPERA, comprobamos su condición de entrada.
        if operacion.estado == 'EN_ESPERA':
            condition_met, reason = _evaluate_entry_condition(operacion, current_price)
            if condition_met:
                memory_logger.log(f"CONDICIÓN DE ENTRADA CUMPLIDA: {reason}", "INFO")
                # Se envía el comando a la om_api
                om_api.force_start_operation()

        # Escenario 2: La operación está ACTIVA, comprobamos sus condiciones de salida.
        elif operacion.estado == 'ACTIVA':
            condition_met, reason = _evaluate_exit_conditions(operacion, current_price)
            if condition_met:
                memory_logger.log(f"CONDICIÓN DE SALIDA CUMPLIDA: {reason}", "INFO")
                # Se envía el comando a la om_api. El PM se encargará de las posiciones si es necesario.
                om_api.force_stop_operation()
    # --- FIN DE LA MODIFICACIÓN ---

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
    
    # --- INICIO DE LA MODIFICACIÓN: Usar pm_api para el summary ---
    # Comprobar límites de ROI (requiere datos de posiciones del PM)
    summary = pm_api.get_position_summary()
    # --- FIN DE LA MODIFICACIÓN ---
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
            
    # Comprobar nueva condición de salida por precio
    cond_type_salida = operacion.tipo_cond_salida
    cond_value_salida = operacion.valor_cond_salida
    if cond_type_salida and cond_value_salida is not None:
        if cond_type_salida == 'PRICE_ABOVE' and current_price > cond_value_salida:
            return True, f"Precio ({current_price:.4f}) superó umbral de salida ({cond_value_salida:.4f})"
        if cond_type_salida == 'PRICE_BELOW' and current_price < cond_value_salida:
            return True, f"Precio ({current_price:.4f}) cayó por debajo de umbral de salida ({cond_value_salida:.4f})"

    return False, ""