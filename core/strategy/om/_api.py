"""
Interfaz Pública del Operation Manager (OM API).

Este módulo actúa como una fachada (proxy) que expone los métodos públicos de
la instancia activa de la clase `OperationManager`.
"""
from typing import Optional, Dict, Any, Tuple, TYPE_CHECKING

# --- Dependencias de Tipado ---
# Usamos TYPE_CHECKING para evitar importaciones circulares en tiempo de ejecución,
# pero permitiendo que los analizadores de código estático entiendan los tipos.
if TYPE_CHECKING:
    from ._manager import OperationManager
    # La ruta de importación ya está corregida a la ubicación centralizada.
    from core.strategy.entities import Operacion

# --- Instancia Global del Módulo (Privada) ---
# Esta variable contendrá la única instancia del OperationManager para toda la sesión.
_om_instance: Optional['OperationManager'] = None

def init_om_api(instance: 'OperationManager'):
    """
    Inicializa esta fachada API inyectando la instancia principal del OperationManager.
    Esta función es llamada una sola vez por el `runner` al arrancar el bot.
    """
    global _om_instance
    _om_instance = instance

# ==============================================================================
# --- FUNCIONES PROXY (DELEGADAS) ---
# Cada función pública aquí simplemente comprueba que la instancia exista y
# luego delega la llamada al método correspondiente en el _om_instance.
# ==============================================================================

# --- Funciones de Acceso y Estado ---

def is_initialized() -> bool:
    """Verifica si el Operation Manager ha sido inicializado."""
    return _om_instance.is_initialized() if _om_instance else False

def get_operation_by_side(side: str) -> Optional['Operacion']:
    """Obtiene el objeto de la operación estratégica para un lado específico ('long' o 'short')."""
    if not _om_instance:
        return None
    return _om_instance.get_operation_by_side(side)

# --- Funciones de Acciones y Control ---

def create_or_update_operation(side: str, params: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Delega la llamada para crear o actualizar la operación existente para un lado específico.
    """
    if not _om_instance:
        return False, "OM no instanciado"
    return _om_instance.create_or_update_operation(side, params)

def pausar_operacion(side: str) -> Tuple[bool, str]:
    """Delega la llamada para pausar la operación."""
    if not _om_instance:
        return False, "OM no instanciado"
    return _om_instance.pausar_operacion(side)

def reanudar_operacion(side: str) -> Tuple[bool, str]:
    """Delega la llamada para reanudar la operación."""
    if not _om_instance:
        return False, "OM no instanciado"
    return _om_instance.reanudar_operacion(side)

def forzar_activacion_manual(side: str) -> Tuple[bool, str]:
    """Delega la llamada para forzar la activación manual de la operación."""
    if not _om_instance:
        return False, "OM no instanciado"
    return _om_instance.forzar_activacion_manual(side)

def activar_por_condicion(side: str) -> Tuple[bool, str]:
    """Delega la llamada para activar la operación cuando se cumple una condición."""
    if not _om_instance:
        return False, "OM no instanciado"
    return _om_instance.activar_por_condicion(side)

def detener_operacion(side: str, forzar_cierre_posiciones: bool) -> Tuple[bool, str]:
    """Delega la llamada para detener completamente la operación."""
    if not _om_instance:
        return False, "OM no instanciado"
    return _om_instance.detener_operacion(side, forzar_cierre_posiciones)

# --- Funciones de Actualización de Estado ---

def actualizar_pnl_realizado(side: str, pnl_amount: float):
    """Delega la llamada para actualizar el PNL realizado de una operación."""
    if _om_instance:
        _om_instance.actualizar_pnl_realizado(side, pnl_amount)

def actualizar_total_reinvertido(side: str, amount: float):
    """Delega la llamada para actualizar el contador de total reinvertido para métricas."""
    if _om_instance:
        _om_instance.actualizar_total_reinvertido(side, amount)

def actualizar_comisiones_totales(side: str, fee_amount: float):
    """Delega la llamada para actualizar las comisiones totales de una operación."""
    if _om_instance:
        _om_instance.actualizar_comisiones_totales(side, fee_amount)

def revisar_y_transicionar_a_detenida(side: str):
    """Delega la llamada para revisar si una operación pausada debe detenerse."""
    if _om_instance:
        _om_instance.revisar_y_transicionar_a_detenida(side)
