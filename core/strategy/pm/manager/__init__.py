"""
Módulo Ensamblador del Position Manager.

Este archivo __init__.py importa las diferentes clases base que contienen
la lógica segmentada del PositionManager y las une en una única clase final
`PositionManager` mediante herencia múltiple.

Esta técnica de 'mixins' o clases base permite mantener el código organizado
en archivos más pequeños y manejables sin cambiar la interfaz pública ni
la funcionalidad del PositionManager original.
"""
from typing import Any

# 1. Importar todas las clases base de los módulos privados
from ._lifecycle import _LifecycleManager
from ._api_getters import _ApiGetters
from ._api_actions import _ApiActions
from ._workflow import _Workflow
from ._private_logic import _PrivateLogic

# 2. Definir la clase final `PositionManager` que hereda de todas las clases base.
# El orden de la herencia es importante para la Resolución de Métodos (MRO).
# _LifecycleManager debe ir primero porque contiene el constructor `__init__`.
class PositionManager(
    _LifecycleManager,
    _ApiGetters,
    _ApiActions,
    _Workflow,
    _PrivateLogic
):
    """
    Clase final ensamblada que orquesta la gestión de posiciones, capital y riesgo.
    Hereda toda su funcionalidad de las clases base importadas.
    """
    def __init__(self, *args: Any, **kwargs: Any):
        """
        El constructor de la clase final.
        Llama al constructor de la primera clase base en la lista de herencia
        (_LifecycleManager), que a su vez inicializa todas las dependencias
        y el estado necesarios.
        """
        super().__init__(*args, **kwargs)

# 3. Definir __all__ para que `from . import PositionManager` funcione correctamente.
__all__ = [
    'PositionManager',
]