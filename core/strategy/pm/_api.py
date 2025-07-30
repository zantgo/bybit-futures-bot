"""
Interfaz Pública del Position Manager (PM API).

v7.0 (Arquitectura de Controladores):
- La función `get_current_market_price` ahora delega la llamada al `SessionManager`,
  que es el propietario del Ticker en la nueva arquitectura, mejorando la
  separación de responsabilidades.
- Las funciones de gestión de Operación han sido movidas a la API del OM (`om_api`).
  Esta API se centra exclusivamente en la gestión de posiciones y estado de sesión.
"""
import datetime
from typing import Optional, Dict, Any, Tuple, List, TYPE_CHECKING

if TYPE_CHECKING:
    from .manager import PositionManager
    from core.strategy.om._entities import Operacion

# --- Módulos API de Dependencia ---
# El PM API ahora necesita conocer al SM API para obtener el precio
from core.strategy.sm import api as sm_api

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

# --- INICIO DE LA MODIFICACIÓN: La función is_session_tp_hit() debe ser movida o renombrada ---
# Esta lógica ahora es más propia del SessionManager, pero el PM la usa internamente.
# Mantenemos la función pero renombramos para claridad futura.
def set_session_tp_hit(value: bool):
    """Establece el estado del TP de la sesión. Es llamado por el SM o el Event Processor."""
    if _pm_instance and hasattr(_pm_instance, 'set_session_tp_hit'):
        _pm_instance.set_session_tp_hit(value)

def is_session_tp_hit() -> bool:
    return _pm_instance.is_session_tp_hit() if _pm_instance else False
# --- FIN DE LA MODIFICACIÓN ---


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
    
# --- (ELIMINADO) Funciones de gestión de Operación ---
# Estas funciones ahora pertenecen y son gestionadas por el OperationManager (om_api)
# def get_operation() -> Optional['Operacion']: ...
# def create_or_update_operation(params: Dict[str, Any]) -> Tuple[bool, str]: ...
# def force_start_operation() -> Tuple[bool, str]: ...
# def force_stop_operation(close_positions: bool = False) -> Tuple[bool, str]: ...

# --- Funciones de Ayuda y Sistema ---
def force_balance_update():
    """Delega la llamada para forzar una actualización de la caché de balances reales."""
    if _pm_instance:
        _pm_instance.force_balance_update()

def get_current_market_price() -> Optional[float]:
    """
    Obtiene el precio de mercado más reciente conocido por la sesión.
    Delega la llamada a la API del SessionManager, que es el propietario del Ticker.
    """
    # La llamada ya no va al _pm_instance
    return sm_api.get_session_summary().get('current_market_price')