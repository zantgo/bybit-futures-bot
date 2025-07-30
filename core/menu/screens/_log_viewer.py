"""
Módulo para la pantalla "Visor de Logs" de la TUI.

Esta pantalla muestra los últimos mensajes registrados por el `memory_logger`,
permitiendo al usuario ver la actividad del bot en tiempo real sin
interrumpir el menú principal.
"""
import sys
import os
from typing import Dict, Any, Optional

# --- INICIO DE CAMBIOS: Importaciones Adaptadas ---

# Ajustar sys.path para importaciones absolutas
if __name__ != "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(script_dir))))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

# Importar dependencias
try:
    from simple_term_menu import TerminalMenu
except ImportError:
    TerminalMenu = None

try:
    from core.logging import memory_logger
    from .._helpers import (
        clear_screen,
        print_tui_header,
        MENU_STYLE
    )
    import config # <-- AÑADIDO SEGÚN TUS INSTRUCCIONES
except ImportError as e:
    print(f"ERROR [TUI Log Viewer]: Falló importación de dependencias: {e}")
    memory_logger = None
    MENU_STYLE = {}
    config = None
    def clear_screen(): pass
    def print_tui_header(title): print(f"--- {title} ---")

# --- FIN DE CAMBIOS: Importaciones Adaptadas ---


# --- Pantalla del Visor de Logs ---

def show_log_viewer():
    """
    Muestra una pantalla con los últimos logs capturados en memoria.
    Esta función tiene su propio bucle para permitir refrescar la vista.
    """
    if not TerminalMenu or not memory_logger or not config:
        print("\nError: Dependencias de menú o configuración no disponibles.")
        import time
        time.sleep(2)
        return

    log_viewer_style = MENU_STYLE.copy()
    log_viewer_style["clear_screen"] = False # Evita parpadeo al refrescar

    while True:
        clear_screen()
        print_tui_header("Visor de Logs en Tiempo Real")
        
        all_logs = memory_logger.get_logs()
        
        if not all_logs:
            print("\n  (No hay logs para mostrar)")
        else:
            # --- INICIO DE LA MODIFICACIÓN SEGÚN INSTRUCCIONES ---
            # Leer el límite desde el archivo de configuración centralizado.
            max_lines_to_show = getattr(config, 'TUI_LOG_VIEWER_MAX_LINES', 100)
            
            # Aplicar el slicing para obtener solo las últimas N líneas.
            logs_to_show = all_logs[-max_lines_to_show:]
            
            # Mensaje actualizado para reflejar el número total de logs y los que se muestran.
            print(f"\n  --- Mostrando las últimas {len(logs_to_show)} de {len(all_logs)} entradas ---")
            # --- FIN DE LA MODIFICACIÓN ---
            
            for timestamp, level, message in logs_to_show:
                color_code = ""
                if level == "ERROR": color_code = "\x1b[91m"  # Rojo brillante
                elif level == "WARN": color_code = "\x1b[93m" # Amarillo brillante
                elif level == "DEBUG": color_code = "\x1b[90m" # Gris
                reset_code = "\x1b[0m"
                
                # Truncar mensajes largos para que no rompan el formato visual en una sola línea.
                print(f"  {timestamp} [{color_code}{level:<5}{reset_code}] {message[:200]}")

        menu_items = ["[r] Refrescar", "[b] Volver al Menú Principal"]
        title = "\n[r] Refrescar | [b] o [ESC] Volver"
        
        terminal_menu = TerminalMenu(
            menu_items,
            title=title,
            **log_viewer_style
        )
        choice_index = terminal_menu.show()

        if choice_index == 0: # El usuario seleccionó [r] Refrescar
            continue
        else: # El usuario seleccionó [b] Volver, presionó ESC o una opción nula
            break