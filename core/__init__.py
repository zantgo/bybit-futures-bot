"""
Paquete Core del Bot.

Este paquete contiene la lógica central y las utilidades de la aplicación.
Expone módulos y funciones clave para el resto del sistema.
"""

# Importar y exponer las funciones de utilidad desde el módulo privado _utils
from . import _utils as utils

# Definir la API pública del paquete core
__all__ = [
    'utils',
]
