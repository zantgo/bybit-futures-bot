# core/menu/__init__.py

"""
Paquete de la Interfaz de Usuario de Terminal (TUI) para el Bot de Trading.

Este archivo __init__.py actúa como la fachada y el punto de entrada principal
para todo el paquete `menu`. Exporta las funciones clave que serán utilizadas
por el resto de la aplicación, como `main.py` y los `runners`.

Funciones Públicas Exportadas:
- launch_bot: Inicia el bot directamente en modo live_interactive.
- run_trading_assistant_wizard: Lanza el asistente de configuración inicial.
- run_tui_menu_loop: Lanza el bucle del menú interactivo principal.
- clear_screen: Función de ayuda para limpiar la terminal.
"""
import sys
import os
import time

# --- [OBSOLETO] Lógica de Click ---
# La dependencia de `click` ha sido eliminada para un lanzamiento directo.
# Se mantiene la importación del archivo original comentada para referencia.
# from ._cli import main_cli


# --- Importar y Exponer Funciones Públicas de los Módulos Internos ---

# Desde el módulo del asistente de configuración (_wizard)
try:
    from ._wizard import run_trading_assistant_wizard
except ImportError as e:
    print(f"ADVERTENCIA [menu/__init__]: No se pudo importar el asistente de configuración: {e}")
    def run_trading_assistant_wizard(*args, **kwargs):
        print("ERROR: El asistente de configuración no está disponible.")
        return None, None

# Desde el módulo del bucle principal (_main_loop)
try:
    from ._main_loop import run_tui_menu_loop
except ImportError as e:
    print(f"ADVERTENCIA [menu/__init__]: No se pudo importar el bucle del menú principal: {e}")
    def run_tui_menu_loop(*args, **kwargs):
        print("ERROR: El menú principal no está disponible.")

# Desde el módulo de helpers (_helpers)
try:
    from ._helpers import clear_screen
except ImportError as e:
     print(f"ADVERTENCIA [menu/__init__]: No se pudo importar helpers del menú: {e}")
     def clear_screen():
         pass


# --- Nueva Función de Lanzamiento Principal ---

def launch_bot():
    """
    Punto de entrada principal para iniciar el bot.
    Llama al orquestador en `main.py` para ejecutar el modo live_interactive.
    """
    try:
        # Ajustar sys.path para que la importación de main funcione correctamente.
        # Navegar dos niveles hacia arriba (desde core/menu/ hasta la raíz).
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(os.path.dirname(script_dir))
        if project_root not in sys.path:
            sys.path.insert(0, project_root)
        
        # Importar la función principal de forma segura
        from main import run_selected_mode
        
        # Comprobar si se pasaron argumentos de línea de comandos no deseados.
        # En esta nueva versión, se ignora cualquier argumento y se entra directo.
        if len(sys.argv) > 1:
            print("Info: Los argumentos de línea de comandos se ignoran.")
            print("Iniciando directamente en modo Live Interactivo...")
            time.sleep(2)
        
        # Ejecutar siempre el único modo disponible
        run_selected_mode("live_interactive")

    except ImportError:
        print("ERROR CRÍTICO [Launcher]: No se pudo encontrar 'main.py' en la raíz del proyecto.")
        print("Asegúrate de que la estructura de directorios sea la correcta.")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR INESPERADO [Launcher]: Ocurrió un error al intentar iniciar el bot: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


# --- Control de lo que se exporta con 'from core.menu import *' ---
__all__ = [
    'launch_bot',
    'run_trading_assistant_wizard',
    'run_tui_menu_loop',
    'clear_screen',
]