# connection/__init__.py

"""
Paquete de Conexión.

Este módulo expone públicamente los componentes necesarios para interactuar
con el mercado en vivo, como el gestor de sesiones API y el ticker de precios.

Módulos Públicos:
- manager: Gestiona las sesiones de la API de Bybit.
- ticker: Gestiona el hilo que obtiene los precios del mercado en tiempo real.
"""

# Importar los módulos internos con un alias público
# Esto permite que otros archivos hagan `from connection import manager`
from . import _manager as manager
from . import _ticker as ticker

# Definir __all__ es una buena práctica para controlar lo que se exporta
# cuando alguien hace `from connection import *`
__all__ = [
    'manager',
    'ticker'
]