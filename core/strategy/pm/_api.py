"""
Interfaz Pública del Position Manager (PM API).

Este módulo actúa como una fachada (proxy) que expone los métodos de una instancia
de la clase PositionManager. Contiene todas las funciones que los consumidores
externos, como la TUI, utilizan para controlar y consultar el estado del PM.

v2.1: Añadidas funciones faltantes para completar la API y evitar
AttributeErrors en los módulos consumidores.
"""
import datetime
from typing import Optional, Dict, Any, Tuple, List, TYPE_CHECKING

# --- Dependencias de Tipado ---
if TYPE_CHECKING:
    from ._manager import PositionManager
    from ._entities import Milestone

# --- Instancia Global del Position Manager ---
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

def get_manual_state() -> Dict[str, Any]:
    """Obtiene el estado del modo manual."""
    return _pm_instance.get_manual_state() if _pm_instance else {}

def get_session_start_time() -> Optional[datetime.datetime]:
    """Obtiene la hora de inicio de la sesión."""
    return _pm_instance.get_session_start_time() if _pm_instance else None

def get_global_tp_pct() -> Optional[float]:
    """Obtiene el umbral de Take Profit Global por ROI."""
    return _pm_instance.get_global_tp_pct() if _pm_instance else None

def is_session_tp_hit() -> bool:
    """Verifica si se ha alcanzado el TP global de la sesión."""
    return _pm_instance.is_session_tp_hit() if _pm_instance else False

def get_individual_stop_loss_pct() -> float:
    """Obtiene el SL individual para nuevas posiciones."""
    return _pm_instance.get_individual_stop_loss_pct() if _pm_instance else 0.0

def get_trailing_stop_params() -> Dict[str, float]:
    """Obtiene los parámetros del Trailing Stop."""
    return _pm_instance.get_trailing_stop_params() if _pm_instance else {'activation': 0.0, 'distance': 0.0}

def get_trend_limits() -> Dict[str, Any]:
    """Obtiene los límites configurados para la tendencia actual/próxima."""
    return _pm_instance.get_trend_limits() if _pm_instance else {}

def get_trend_state() -> Dict[str, Any]:
    """Obtiene el estado de la tendencia actual (para el modo automático original)."""
    return _pm_instance.get_trend_state() if _pm_instance else {}

def get_global_sl_pct() -> Optional[float]:
    """Obtiene el umbral de Stop Loss Global por ROI."""
    return _pm_instance.get_global_sl_pct() if _pm_instance else None

def get_all_milestones() -> List['Milestone']:
    """Obtiene todos los hitos (triggers) como objetos Milestone."""
    return _pm_instance.get_all_milestones() if _pm_instance else []

# --- INICIO DEL CÓDIGO AÑADIDO ---
# Estas son las funciones que faltaban y que son requeridas por el módulo _limit_checks.

def get_session_time_limit() -> Dict[str, Any]:
    """Obtiene la configuración del límite de tiempo de la sesión."""
    if not _pm_instance: return {'duration': 0, 'action': 'NEUTRAL'}
    return _pm_instance.get_session_time_limit()

def set_session_tp_hit(value: bool):
    """
    Establece el estado de 'TP de sesión alcanzado'.
    En la implementación actual, esto se logra cambiando el modo a NEUTRAL.
    """
    if _pm_instance and value:
        # La acción de "TP de sesión alcanzado" es poner el bot en modo neutral.
        _pm_instance.set_manual_trading_mode("NEUTRAL", close_open=False)
    # Si value es False, podría implementarse una lógica para "reactivar" la sesión,
    # pero actualmente no es un caso de uso.

# --- FIN DEL CÓDIGO AÑADIDO ---


# --- Funciones de Control Manual (TUI) ---

def set_manual_trading_mode(mode: str, trade_limit: Optional[int] = None, close_open: bool = False) -> Tuple[bool, str]:
    """Establece el modo de trading manual."""
    if not _pm_instance: return False, "PM no instanciado"
    return _pm_instance.set_manual_trading_mode(mode, trade_limit, close_open)

def manual_close_logical_position_by_index(side: str, index: int) -> Tuple[bool, str]:
    """Cierra una posición lógica específica por su índice."""
    if not _pm_instance: return False, "PM no instanciado"
    return _pm_instance.manual_close_logical_position_by_index(side, index)

def close_all_logical_positions(side: str, reason: str = "MANUAL_ALL") -> bool:
    """Cierra TODAS las posiciones lógicas de un lado."""
    if not _pm_instance: return False
    return _pm_instance.close_all_logical_positions(side, reason)

# --- Funciones de Ajuste de Parámetros (TUI) ---

def add_max_logical_position_slot() -> Tuple[bool, str]:
    """Incrementa el número máximo de posiciones simultáneas."""
    if not _pm_instance: return False, "PM no instanciado"
    return _pm_instance.add_max_logical_position_slot()

def remove_max_logical_position_slot() -> Tuple[bool, str]:
    """Decrementa el número máximo de posiciones, si es seguro hacerlo."""
    if not _pm_instance: return False, "PM no instanciado"
    return _pm_instance.remove_max_logical_position_slot()

def set_base_position_size(new_size_usdt: float) -> Tuple[bool, str]:
    """Establece el tamaño base de las nuevas posiciones."""
    if not _pm_instance: return False, "PM no instanciado"
    return _pm_instance.set_base_position_size(new_size_usdt)

def set_leverage(new_leverage: float) -> Tuple[bool, str]:
    """Establece el apalancamiento para futuras operaciones."""
    if not _pm_instance: return False, "PM no instanciado"
    return _pm_instance.set_leverage(new_leverage)

def set_individual_stop_loss_pct(value: float) -> Tuple[bool, str]:
    """Establece el SL para nuevas posiciones."""
    if not _pm_instance: return False, "PM no instanciado"
    return _pm_instance.set_individual_stop_loss_pct(value)

def set_trailing_stop_params(activation_pct: float, distance_pct: float) -> Tuple[bool, str]:
    """Ajusta los parámetros del Trailing Stop."""
    if not _pm_instance: return False, "PM no instanciado"
    return _pm_instance.set_trailing_stop_params(activation_pct, distance_pct)

# --- Funciones de Gestión de Límites y Hitos (TUI) ---

def set_global_stop_loss_pct(value: float) -> Tuple[bool, str]:
    """Establece el disyuntor de SL global por ROI."""
    if not _pm_instance: return False, "PM no instanciado"
    return _pm_instance.set_global_stop_loss_pct(value)

def set_global_take_profit_pct(value: float) -> Tuple[bool, str]:
    """Establece el disyuntor de TP global por ROI."""
    if not _pm_instance: return False, "PM no instanciado"
    return _pm_instance.set_global_take_profit_pct(value)

def set_session_time_limit(duration: int, action: str) -> Tuple[bool, str]:
    """Establece el límite de duración de la sesión."""
    if not _pm_instance: return False, "PM no instanciado"
    return _pm_instance.set_session_time_limit(duration, action)

def set_manual_trade_limit(limit: Optional[int]) -> Tuple[bool, str]:
    """Establece un límite al número de trades para la sesión manual."""
    if not _pm_instance: return False, "PM no instanciado"
    return _pm_instance.set_manual_trade_limit(limit)

def set_trend_limits(duration: Optional[int], tp_roi_pct: Optional[float], sl_roi_pct: Optional[float], trade_limit: Optional[int] = None) -> Tuple[bool, str]:
    """Establece los límites para la PRÓXIMA tendencia manual."""
    if not _pm_instance: return False, "PM no instanciado"
    return _pm_instance.set_trend_limits(duration, tp_roi_pct, sl_roi_pct, trade_limit)

def add_milestone(condition_data: Dict, action_data: Dict, parent_id: Optional[str] = None) -> Tuple[bool, str]:
    """Añade un nuevo hito al árbol de decisiones."""
    if not _pm_instance: return False, "PM no instanciado"
    return _pm_instance.add_milestone(condition_data, action_data, parent_id)

def remove_milestone(milestone_id: str) -> Tuple[bool, str]:
    """Elimina un hito del árbol de decisiones."""
    if not _pm_instance: return False, "PM no instanciado"
    return _pm_instance.remove_milestone(milestone_id)

# --- Funciones para uso interno del sistema (Workflow, Triggers) ---

def process_triggered_milestone(milestone_id: str):
    """Procesa la cascada de un hito cumplido."""
    if _pm_instance:
        _pm_instance.process_triggered_milestone(milestone_id)

def start_manual_trend(mode: str, trade_limit: Optional[int], duration_limit: Optional[int], tp_roi_limit: Optional[float], sl_roi_limit: Optional[float]) -> Tuple[bool, str]:
    """Inicia una nueva tendencia manual con límites específicos (usado por hitos)."""
    if not _pm_instance: return False, "PM no instanciado"
    return _pm_instance.start_manual_trend(mode, trade_limit, duration_limit, tp_roi_limit, sl_roi_limit)

def end_current_trend_and_ask():
    """Finaliza la tendencia actual y revierte a modo NEUTRAL."""
    if _pm_instance:
        _pm_instance.end_current_trend_and_ask()

# --- Funciones de Ayuda y Visualización ---

def get_current_price_for_exit() -> Optional[float]:
    """Obtiene el último precio del ticker para cierres manuales."""
    if not _pm_instance: return None
    return _pm_instance.get_current_price_for_exit()

def get_rrr_potential() -> Optional[float]:
    """Calcula el Risk/Reward Ratio Potencial hasta la activación del Trailing Stop."""
    if not _pm_instance: return None
    return _pm_instance.get_rrr_potential()