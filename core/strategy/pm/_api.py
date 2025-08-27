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
    from core.strategy.entities import Operacion, LogicalPosition

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

# --- Funciones de Control de Posiciones ---
def manual_close_logical_position_by_index(side: str, index: int) -> Tuple[bool, str]:
    """
    Delega la llamada para cerrar manualmente una posición lógica específica por su
    índice en la lista de posiciones abiertas.
    """
    if not _pm_instance:
        return False, "PM no instanciado"
    return _pm_instance.manual_close_logical_position_by_index(side, index)

def close_all_logical_positions(side: str, reason: str = "MANUAL_ALL") -> Tuple[bool, str]:
    """
    Delega la llamada para cerrar todas las posiciones lógicas de un lado.
    Se corrige el tipo de retorno para que coincida con la implementación.
    """
    if not _pm_instance:
        return False, "PM no instanciado"
    return _pm_instance.close_all_logical_positions(side, reason)

def get_current_market_price() -> Optional[float]:
    """
    Obtiene el precio de mercado más reciente conocido por la sesión.
    Delega la llamada a la API del SessionManager, que es el propietario del Ticker.
    """
    # La llamada ya no va al _pm_instance
    return sm_api.get_session_summary().get('current_market_price')

def sync_physical_positions(side: str):
    """
    Delega la llamada para sincronizar el estado interno de las posiciones
    con la realidad del exchange para un lado específico.
    """
    if _pm_instance:
        _pm_instance.sync_physical_positions(side)