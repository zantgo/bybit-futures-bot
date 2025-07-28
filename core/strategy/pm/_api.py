"""
Interfaz Pública del Position Manager (PM API).

v6.0 (Modelo de Operación Estratégica Única):
- Se eliminan todas las funciones relacionadas con la gestión de múltiples hitos.
- Se introducen nuevas funciones para crear, modificar y forzar el inicio/fin
  de la única operación estratégica.
"""
import datetime
from typing import Optional, Dict, Any, Tuple, List, TYPE_CHECKING

if TYPE_CHECKING:
    from .manager import PositionManager
    from ._entities import Operacion

_pm_instance: Optional['PositionManager'] = None

def init_pm_api(instance: 'PositionManager'):
    """Inicializa esta fachada API inyectando la instancia principal del PositionManager."""
    global _pm_instance
    _pm_instance = instance

# --- Funciones de Acceso y Resumen de Estado ---
def is_initialized() -> bool:
    return _pm_instance.is_initialized() if _pm_instance else False

def get_position_summary() -> Dict[str, Any]:
    if not _pm_instance: return {"error": "PM no instanciado"}
    return _pm_instance.get_position_summary()

def get_unrealized_pnl(current_price: float) -> float:
    if not _pm_instance: return 0.0
    return _pm_instance.get_unrealized_pnl(current_price)

def get_session_start_time() -> Optional[datetime.datetime]:
    return _pm_instance.get_session_start_time() if _pm_instance else None

def get_global_tp_pct() -> Optional[float]:
    return _pm_instance.get_global_tp_pct() if _pm_instance else None

def is_session_tp_hit() -> bool:
    return _pm_instance.is_session_tp_hit() if _pm_instance else False

def get_global_sl_pct() -> Optional[float]:
    return _pm_instance.get_global_sl_pct() if _pm_instance else None

def get_session_time_limit() -> Dict[str, Any]:
    if not _pm_instance: return {'duration': 0, 'action': 'NEUTRAL'}
    return _pm_instance.get_session_time_limit()

# --- Funciones de Control de Posiciones ---
def manual_close_logical_position_by_index(side: str, index: int) -> Tuple[bool, str]:
    if not _pm_instance: return False, "PM no instanciado"
    return _pm_instance.manual_close_logical_position_by_index(side, index)

def close_all_logical_positions(side: str, reason: str = "MANUAL_ALL") -> bool:
    if not _pm_instance: return False
    return _pm_instance.close_all_logical_positions(side, reason)

# --- Funciones de Gestión de Límites de Sesión (TUI) ---
def set_global_stop_loss_pct(value: float) -> Tuple[bool, str]:
    if not _pm_instance: return False, "PM no instanciado"
    return _pm_instance.set_global_stop_loss_pct(value)

def set_global_take_profit_pct(value: float) -> Tuple[bool, str]:
    if not _pm_instance: return False, "PM no instanciado"
    return _pm_instance.set_global_take_profit_pct(value)
    
# --- INICIO: Nuevas Funciones para la Operación Estratégica Única (v6.0) ---
def get_operation() -> Optional['Operacion']:
    """Obtiene el objeto de la operación estratégica actual."""
    if not _pm_instance: return None
    return _pm_instance.get_operation()

def create_or_update_operation(params: Dict[str, Any]) -> Tuple[bool, str]:
    """Crea una nueva operación (si no hay ninguna) o actualiza la existente."""
    if not _pm_instance: return False, "PM no instanciado"
    return _pm_instance.create_or_update_operation(params)

def force_start_operation() -> Tuple[bool, str]:
    """Fuerza el inicio inmediato de la operación, ignorando la condición de entrada."""
    if not _pm_instance: return False, "PM no instanciado"
    return _pm_instance.force_start_operation()

def force_stop_operation(close_positions: bool = False) -> Tuple[bool, str]:
    """Fuerza la finalización de la operación activa."""
    if not _pm_instance: return False, "PM no instanciado"
    return _pm_instance.force_stop_operation(close_positions=close_positions)

# --- FIN: Nuevas Funciones ---

# --- Funciones de Ayuda y Sistema ---
def force_balance_update():
    """Delega la llamada para forzar una actualización de la caché de balances reales."""
    if _pm_instance:
        _pm_instance.force_balance_update()

def get_current_market_price() -> Optional[float]:
    """Obtiene el precio de mercado más reciente conocido por el ticker."""
    if not _pm_instance: return None
    return _pm_instance.get_current_market_price()

# --- (COMENTADO) Funciones de Gestión de Hitos Obsoletas ---
# def get_all_milestones() -> List['Hito']:
#     return _pm_instance.get_all_milestones() if _pm_instance else []
#
# def add_milestone(tipo_hito: str, condicion: Any, accion: Any, parent_id: Optional[str] = None) -> Tuple[bool, str]:
#     if not _pm_instance: return False, "PM no instanciado"
#     return _pm_instance.add_milestone(tipo_hito, condicion, accion, parent_id)
#
# def remove_milestone(milestone_id: str) -> Tuple[bool, str]:
#     if not _pm_instance: return False, "PM no instanciado"
#     return _pm_instance.remove_milestone(milestone_id)
#
# def update_milestone(milestone_id: str, nueva_condicion: Any, nueva_accion: Any) -> Tuple[bool, str]:
#     if not _pm_instance: return False, "PM no instanciado"
#     if hasattr(_pm_instance, 'update_milestone'):
#         return _pm_instance.update_milestone(milestone_id, nueva_condicion, nueva_accion)
#     return False, "Función 'update_milestone' no implementada en el manager."
#
# def force_trigger_milestone_with_pos_management(...) -> Tuple[bool, str]:
#     if not _pm_instance: return False, "PM no instanciado"
#     ...
#
# def force_end_operation(close_positions: bool = False) -> Tuple[bool, str]:
#     """(Obsoleto) Reemplazado por force_stop_operation para unificar nombres."""
#     if not _pm_instance: return False, "PM no instanciado"
#     return _pm_instance.force_end_operation(close_positions=close_positions)