"""
Paquete Runner: Orquesta los diferentes modos de ejecución del bot.

Este __init__.py actúa como una fachada para el paquete, exponiendo las
funciones de alto nivel que los lanzadores (como main.py) y los controladores
(como _main_controller.py) necesitan.
"""
# --- INICIO DE LA NUEVA ESTRUCTURA CORRECTA ---

# Importar la función de inicialización desde su módulo especializado.
# Le damos un alias público para que el resto de la aplicación la conozca
# con un nombre claro y consistente.
from ._initializer import initialize_core_components as initialize_bot_backend

# Importar la función de apagado desde su módulo especializado.
# También le damos un alias público.
from ._shutdown import perform_shutdown as shutdown_bot_backend

# El orquestador principal no necesita ser público, es llamado por el controlador de la TUI
# directamente (si es necesario), pero el patrón actual lo mantiene interno.

# Definir __all__ para una API pública limpia y explícita.
# Esto define qué se importa cuando otro módulo hace `from runner import *`.
__all__ = [
    'initialize_bot_backend',
    'shutdown_bot_backend',
]

# --- FIN DE LA NUEVA ESTRUCTURA CORRECTA ---