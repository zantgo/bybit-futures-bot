"""
Controlador Principal del Ciclo de Vida de la TUI.

v4.0 (Arquitectura de Controladores):
- Este módulo ya no orquesta el ciclo de vida del bot.
- Su única responsabilidad es recibir la instancia del BotController, inicializar
  las fachadas API de los componentes y lanzar la pantalla de bienvenida, que
  actúa como la vista principal del BotController y contiene el bucle de la
  aplicación.
"""
import sys
import os
import traceback
from typing import Dict, Any

try:
    from simple_term_menu import TerminalMenu
except ImportError:
    TerminalMenu = None

# --- Dependencias del Proyecto ---
from . import screens
from ._helpers import clear_screen, press_enter_to_continue

# Importar las APIs que este controlador necesita inicializar
from core.bot_controller import api as bc_api
from core.strategy.sm import api as sm_api


def launch_bot(bot_controller_instance: Any, dependencies: Dict[str, Any]):
    """
    Punto de entrada principal para la TUI. Lanza la interfaz de usuario.
    
    Args:
        bot_controller_instance: La instancia activa del BotController.
        dependencies: El diccionario completo de dependencias del sistema.
    """
    if not TerminalMenu:
        print("ERROR: La librería 'simple-term-menu' no está instalada.")
        sys.exit(1)

    try:
        # 1. Inicializar las fachadas API
        bc_api.init_bc_api(bot_controller_instance)
        
        # Las APIs de la sesión (SM, OM, PM) se inicializan dinámicamente
        # cuando el BotController crea una nueva sesión.
        
        # 2. Inyectar dependencias en todas las pantallas de la TUI.
        # Usamos el diccionario de dependencias que recibimos como argumento.
        if hasattr(screens, 'init_screens'):
            screens.init_screens(dependencies)
        
        # 3. Lanzar la pantalla de bienvenida, que ahora controla el flujo principal.
        # Esta función contendrá su propio bucle y gestionará la creación de sesiones
        # y el apagado del bot a través del BotController.
        screens.show_welcome_screen(bot_controller_instance)

    except (KeyboardInterrupt, SystemExit):
        print("\n\n[Main Controller] Interrupción detectada. Saliendo de forma ordenada...")
        # El apagado final lo gestionará el BotController a través de la TUI.
    except Exception as e:
        clear_screen()
        print("\n" + "="*80)
        print("!!! ERROR CRÍTICO INESPERADO EN EL CONTROLADOR DEL MENÚ !!!")
        print(f"  Tipo de Error: {type(e).__name__}")
        print(f"  Mensaje: {e}")
        print("-" * 80)
        traceback.print_exc()
        print("=" * 80)
        press_enter_to_continue()
    finally:
        # La lógica de apagado ahora es responsabilidad del BotController,
        # invocada desde la TUI, por lo que este bloque `finally` se simplifica.
        print("\n[Main Controller] Saliendo del programa. ¡Hasta luego!")
        os._exit(0)