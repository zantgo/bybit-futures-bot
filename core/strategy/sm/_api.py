"""
Módulo de la Interfaz Pública (API) del SessionManager.

Este módulo actúa como una fachada (proxy) que expone de forma segura los
métodos públicos de la instancia activa del `SessionManager`. Cualquier otra parte
de la aplicación (como la TUI) que necesite interactuar con la lógica a nivel
de sesión, debe hacerlo a través de las funciones definidas aquí.
"""
from typing import Optional, Dict, Any, TYPE_CHECKING

# --- Dependencias de Tipado ---
if TYPE_CHECKING:
    from ._manager import SessionManager

# --- Instancia Global del Módulo (Privada) ---
_sm_instance: Optional['SessionManager'] = None


def init_sm_api(instance: 'SessionManager'):
    """
    Inicializa esta fachada API inyectando la instancia principal del SessionManager.
    """
    global _sm_instance
    _sm_instance = instance


# ==============================================================================
# --- FUNCIONES PROXY (DELEGADAS) ---
# Cada función pública aquí simplemente comprueba que la instancia del
# SessionManager exista y luego delega la llamada al método correspondiente.
# ==============================================================================

def start():
    """Delega la llamada para iniciar la sesión (arrancar el ticker)."""
    if _sm_instance:
        _sm_instance.start()


def stop():
    """Delega la llamada para detener la sesión (parar el ticker)."""
    if _sm_instance:
        _sm_instance.stop()


def get_session_summary() -> Dict[str, Any]:
    """
    Delega la llamada para obtener el resumen completo del estado de la sesión.
    """
    if not _sm_instance:
        return {"error": "SessionManager no instanciado."}
    return _sm_instance.get_session_summary()


def update_session_parameters(params: Dict[str, Any]):
    """
    Delega la llamada para actualizar los parámetros de la sesión en tiempo real.
    """
    if _sm_instance:
        _sm_instance.update_session_parameters(params)


def is_running() -> bool:
    """
    Delega la llamada para verificar si la sesión está actualmente en ejecución.
    """
    if not _sm_instance:
        return False
    return _sm_instance.is_running()


def force_single_tick():
    """Delega la llamada para forzar un único tick de precio."""
    if _sm_instance:
        _sm_instance.force_single_tick()