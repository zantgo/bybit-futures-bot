# core/strategy/pm/_api.py

"""
Interfaz Pública del Position Manager (PM API).

Este módulo actúa como una fachada (proxy) que expone los métodos de una instancia
de la clase PositionManager.
"""
import datetime
from typing import Optional, Dict, Any, Tuple, List, TYPE_CHECKING

if TYPE_CHECKING:
    from .manager import PositionManager
    # --- INICIO DE LA MODIFICACIÓN: Importar nuevas entidades ---
    from ._entities import Hito
    # from ._entities import Milestone # Comentado
    # --- FIN DE LA MODIFICACIÓN ---

_pm_instance: Optional['PositionManager'] = None

def init_pm_api(instance: 'PositionManager'):
    """
    Inicializa esta fachada API inyectando la instancia principal del PositionManager.
    """
    global _pm_instance
    _pm_instance = instance

# ==============================================================================
# --- FUNCIONES PROXY (DELEGADAS) ---
# ==============================================================================

# --- Funciones de Acceso y Resumen de Estado ---

def is_initialized() -> bool:
    """Verifica si el Position Manager ha sido inicializado."""
    return _pm_instance.is_initialized() if _pm_instance else False

def get_position_summary() -> Dict[str, Any]:
    """Obtiene un resumen completo del estado actual del Position Manager."""
    if not _pm_instance: return {"error": "PM no instanciado"}
    return _pm_instance.get_position_summary()

def get_unrealized_pnl(current_price: float) -> float:
    """Calcula el PNL no realizado total de todas las posiciones abiertas."""
    if not _pm_instance: return 0.0
    return _pm_instance.get_unrealized_pnl(current_price)

# --- (COMENTADO) get_trend_state y get_trend_limits ---
# def get_trend_state() -> Dict[str, Any]:
#     """Obtiene el estado de la tendencia activa (NEUTRAL si no hay ninguna)."""
#     if not _pm_instance: return {'mode': 'UNKNOWN'}
#     return _pm_instance.get_trend_state()
    
# def get_trend_limits() -> Dict[str, Any]:
#     """Obtiene los límites de la tendencia activa."""
#     if not _pm_instance: return {}
#     return _pm_instance.get_trend_limits()

# --- INICIO DE LA MODIFICACIÓN: Nuevas funciones proxy para la Operación ---
def get_operation_state() -> Dict[str, Any]:
    """Obtiene el estado completo de la Operación activa."""
    if not _pm_instance: return {'error': 'PM no instanciado'}
    return _pm_instance.get_operation_state()

def get_operation_parameters() -> Dict[str, Any]:
    """Obtiene los parámetros de configuración de la Operación activa."""
    if not _pm_instance: return {}
    return _pm_instance.get_operation_parameters()
# --- FIN DE LA MODIFICACIÓN ---

def get_session_start_time() -> Optional[datetime.datetime]:
    """Obtiene la hora de inicio de la sesión."""
    return _pm_instance.get_session_start_time() if _pm_instance else None

def get_global_tp_pct() -> Optional[float]:
    """Obtiene el umbral de Take Profit Global por ROI de la sesión."""
    return _pm_instance.get_global_tp_pct() if _pm_instance else None

def is_session_tp_hit() -> bool:
    """Verifica si se ha alcanzado el TP global de la sesión."""
    return _pm_instance.is_session_tp_hit() if _pm_instance else False

def get_global_sl_pct() -> Optional[float]:
    """Obtiene el umbral de Stop Loss Global por ROI de la sesión."""
    return _pm_instance.get_global_sl_pct() if _pm_instance else None

def get_all_milestones() -> List['Hito']:
    """Obtiene todos los hitos (triggers) como objetos Hito."""
    return _pm_instance.get_all_milestones() if _pm_instance else []

def get_session_time_limit() -> Dict[str, Any]:
    """Obtiene la configuración del límite de tiempo de la sesión."""
    if not _pm_instance: return {'duration': 0, 'action': 'NEUTRAL'}
    return _pm_instance.get_session_time_limit()

# --- Funciones de Control de Posiciones ---

def manual_close_logical_position_by_index(side: str, index: int) -> Tuple[bool, str]:
    """Cierra una posición lógica específica por su índice."""
    if not _pm_instance: return False, "PM no instanciado"
    return _pm_instance.manual_close_logical_position_by_index(side, index)

def close_all_logical_positions(side: str, reason: str = "MANUAL_ALL") -> bool:
    """Cierra TODAS las posiciones lógicas de un lado."""
    if not _pm_instance: return False
    return _pm_instance.close_all_logical_positions(side, reason)

# --- (COMENTADO) Funciones de Ajuste de Parámetros de Sesión (TUI) ---
# Estas funciones ahora se gestionan a través de la modificación de la operación activa
# o la creación de un nuevo hito.
# def add_max_logical_position_slot() -> Tuple[bool, str]:
#     """Incrementa el número máximo de posiciones simultáneas."""
#     if not _pm_instance: return False, "PM no instanciado"
#     return _pm_instance.add_max_logical_position_slot()

# def remove_max_logical_position_slot() -> Tuple[bool, str]:
#     """Decrementa el número máximo de posiciones, si es seguro hacerlo."""
#     if not _pm_instance: return False, "PM no instanciado"
#     return _pm_instance.remove_max_logical_position_slot()

# def set_base_position_size(new_size_usdt: float) -> Tuple[bool, str]:
#     """Establece el tamaño base de las nuevas posiciones."""
#     if not _pm_instance: return False, "PM no instanciado"
#     return _pm_instance.set_base_position_size(new_size_usdt)

# def set_leverage(new_leverage: float) -> Tuple[bool, str]:
#     """Establece el apalancamiento para futuras operaciones."""
#     if not _pm_instance: return False, "PM no instanciado"
#     return _pm_instance.set_leverage(new_leverage)

# --- Funciones de Gestión de Límites de Sesión (TUI) ---

def set_global_stop_loss_pct(value: float) -> Tuple[bool, str]:
    """Establece el disyuntor de SL global por ROI."""
    if not _pm_instance: return False, "PM no instanciado"
    return _pm_instance.set_global_stop_loss_pct(value)

def set_global_take_profit_pct(value: float) -> Tuple[bool, str]:
    """Establece el disyuntor de TP global por ROI."""
    if not _pm_instance: return False, "PM no instanciado"
    return _pm_instance.set_global_take_profit_pct(value)
    
# --- Funciones de Gestión de Hitos (TUI) ---

def add_milestone(tipo_hito: str, condicion: Any, accion: Any, parent_id: Optional[str] = None) -> Tuple[bool, str]:
    """Añade un nuevo hito al árbol de decisiones."""
    if not _pm_instance: return False, "PM no instanciado"
    return _pm_instance.add_milestone(tipo_hito, condicion, accion, parent_id)

def remove_milestone(milestone_id: str) -> Tuple[bool, str]:
    """Elimina un hito del árbol de decisiones."""
    if not _pm_instance: return False, "PM no instanciado"
    return _pm_instance.remove_milestone(milestone_id)

def update_milestone(milestone_id: str, nueva_condicion: Any, nueva_accion: Any) -> Tuple[bool, str]:
    """Actualiza los datos de un hito existente."""
    if not _pm_instance: return False, "PM no instanciado"
    if hasattr(_pm_instance, 'update_milestone'):
        return _pm_instance.update_milestone(milestone_id, nueva_condicion, nueva_accion)
    return False, "Función 'update_milestone' no implementada en el manager."

def force_trigger_milestone(milestone_id: str) -> Tuple[bool, str]:
    """Fuerza la activación de un hito, ignorando su condición de precio."""
    if not _pm_instance: return False, "PM no instanciado"
    if hasattr(_pm_instance, 'force_trigger_milestone'):
        return _pm_instance.force_trigger_milestone(milestone_id)
    return False, "Función 'force_trigger_milestone' no implementada en el manager."

def force_trigger_milestone_with_pos_management(
    milestone_id: str,
    long_pos_action: str = 'keep',
    short_pos_action: str = 'keep'
) -> Tuple[bool, str]:
    """
    Gestiona las posiciones existentes y luego fuerza la activación de un hito.
    """
    if not _pm_instance: return False, "PM no instanciado"
    if hasattr(_pm_instance, 'force_trigger_milestone_with_pos_management'):
        return _pm_instance.force_trigger_milestone_with_pos_management(
            milestone_id, long_pos_action, short_pos_action
        )
    return False, "Función 'force_trigger_milestone_with_pos_management' no implementada en el manager."

# --- INICIO DE LA MODIFICACIÓN (REQ-10) -> Adaptada a Operación ---
def update_active_operation_parameters(params_to_update: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Actualiza los parámetros de la operación actualmente activa en tiempo real.
    """
    if not _pm_instance: return False, "PM no instanciado"
    if hasattr(_pm_instance, 'update_active_operation_parameters'):
        return _pm_instance.update_active_operation_parameters(params_to_update)
    return False, "Función 'update_active_operation_parameters' no implementada en el manager."
# --- FIN DE LA MODIFICACIÓN ---

def force_end_operation(close_positions: bool = False) -> Tuple[bool, str]:
    """Fuerza la finalización de la operación activa y vuelve a NEUTRAL."""
    if not _pm_instance: return False, "PM no instanciado"
    return _pm_instance.force_end_operation(close_positions=close_positions)

def force_balance_update():
    """Delega la llamada para forzar una actualización de la caché de balances reales."""
    if _pm_instance:
        _pm_instance.force_balance_update()

# --- Funciones para uso interno del sistema (Workflow) ---

def process_triggered_milestone(milestone_id: str):
    """Procesa la cascada de un hito cumplido."""
    if _pm_instance:
        _pm_instance.process_triggered_milestone(milestone_id)

def set_session_tp_hit(value: bool):
    """Establece el estado de 'TP de sesión alcanzado' finalizando la tendencia activa."""
    if _pm_instance and value:
        _pm_instance.end_current_operation_and_neutralize("TP de Sesión Global Alcanzado")

def end_current_operation_and_neutralize(reason: str):
    """Finaliza la operación actual y revierte a modo NEUTRAL."""
    if _pm_instance:
        _pm_instance.end_current_operation_and_neutralize(reason)

# --- Funciones de Ayuda y Visualización ---

def get_current_market_price() -> Optional[float]:
    """Obtiene el precio de mercado más reciente conocido por el ticker."""
    if not _pm_instance: return None
    return _pm_instance.get_current_market_price()