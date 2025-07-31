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
    from ._entities import Operacion

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

def force_start_operation(side: str) -> Tuple[bool, str]:
    """
    Delega la llamada para forzar el inicio inmediato de la operación para un lado específico,
    ignorando la condición de entrada.
    """
    if not _om_instance:
        return False, "OM no instanciado"
    return _om_instance.force_start_operation(side)

def force_stop_operation(side: str) -> Tuple[bool, str]:
    """
    Delega la llamada para forzar la finalización de la operación activa para un lado específico.
    """
    if not _om_instance:
        return False, "OM no instanciado"
    return _om_instance.force_stop_operation(side)