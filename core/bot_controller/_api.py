"""
Módulo de la Interfaz Pública (API) del BotController.

Este módulo actúa como una fachada (proxy) que expone de forma segura los
métodos públicos de la instancia activa del `BotController`. Cualquier otra parte
de la aplicación (como la TUI) que necesite interactuar con la lógica a nivel
de aplicación, debe hacerlo a través de las funciones definidas aquí.

Este patrón de diseño asegura que la implementación interna del BotController
pueda cambiar sin afectar a sus consumidores, siempre que la firma de esta API
se mantenga estable.
"""

from typing import Optional, Dict, Any, Tuple, TYPE_CHECKING

# --- Dependencias de Tipado ---
# Usamos TYPE_CHECKING para evitar importaciones circulares en tiempo de ejecución,
# pero permitiendo que los analizadores de código estático entiendan los tipos.
if TYPE_CHECKING:
    from ._manager import BotController
    from core.strategy.sm._manager import SessionManager

# --- Instancia Global del Módulo (Privada) ---
# Esta variable contendrá la única instancia del BotController para toda la sesión.
_bc_instance: Optional['BotController'] = None


def init_bc_api(instance: 'BotController'):
    """
    Inicializa esta fachada API inyectando la instancia principal del BotController.
    Esta función es llamada una sola vez por el `runner` o el `main_controller`
    al arrancar el bot.
    """
    global _bc_instance
    _bc_instance = instance


# ==============================================================================
# --- FUNCIONES PROXY (DELEGADAS) ---
# Cada función pública aquí simplemente comprueba que la instancia del
# BotController exista y luego delega la llamada al método correspondiente.
# ==============================================================================

def initialize_connections() -> Tuple[bool, str]:
    """
    Delega la llamada para inicializar y validar todas las conexiones API.

    Returns:
        Una tupla (bool, str) indicando el éxito y un mensaje descriptivo.
    """
    if not _bc_instance:
        return False, "Error: BotController no instanciado."
    return _bc_instance.initialize_connections()


def create_session() -> Optional['SessionManager']:
    """
    Delega la llamada para crear una nueva sesión de trading.

    Returns:
        Una instancia de SessionManager si la creación fue exitosa, de lo
        contrario None.
    """
    if not _bc_instance:
        return None
    return _bc_instance.create_session()


def get_general_config() -> Dict[str, Any]:
    """
    Delega la llamada para obtener la configuración general de la aplicación.
    """
    if not _bc_instance:
        return {"Error": "BotController no instanciado."}
    return _bc_instance.get_general_config()


def update_general_config(params: Dict[str, Any]) -> bool:
    """

    Delega la llamada para actualizar la configuración general de la aplicación.
    """
    if not _bc_instance:
        return False
    return _bc_instance.update_general_config(params)


def shutdown_bot():
    """
    Delega la llamada para ejecutar la secuencia de apagado de la aplicación.
    """
    if _bc_instance:
        _bc_instance.shutdown_bot()