"""
Paquete Runner: Ensambla dependencias y orquesta el apagado de sesión.

v4.0 (Arquitectura de Controladores):
- Este paquete ya no contiene la lógica de inicialización activa del bot.
- Su responsabilidad se ha centrado en exponer el ensamblador de dependencias
  y la lógica de apagado de la sesión, que son invocados por los controladores
  de nivel superior.
"""

# --- Importar las funciones públicas de los módulos internos ---

# Importar la nueva función desde su módulo especializado.
from ._initializer import assemble_dependencies

# Importar la función de apagado refactorizada desde su módulo especializado.
from ._shutdown import shutdown_session_backend

# --- Definir la API pública del paquete ---
# Esto define qué se importa cuando otro módulo hace `from runner import *`.
# Ahora exportamos las funciones con sus nuevos nombres correctos.
__all__ = [
    'assemble_dependencies',
    'shutdown_session_backend',
]