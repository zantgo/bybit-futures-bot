"""
Módulo de Ayuda para la TUI (Terminal User Interface).

v4.2 (get_input Definitivo):
- Refactorizada la función get_input para ser explícita en su comportamiento.
- Se elimina el parámetro 'disable_value' y se introduce 'is_optional'.
- Ahora maneja correctamente campos obligatorios con default, campos opcionales
  y cancelación sin ambigüedades.
"""
import os
import datetime
from datetime import timezone
import textwrap
from typing import Dict, Any, Optional, Callable
import shutil
import re
import time  # <--- IMPORTACIÓN AÑADIDA PARA CORREGIR EL NameError

# --- Estilo Visual Consistente para simple-term-menu ---
MENU_STYLE = {
    "menu_cursor": "> ",
    "menu_cursor_style": ("fg_yellow", "bold"),
    "menu_highlight_style": ("bg_cyan", "fg_black"),
    "cycle_cursor": True,
    "clear_screen": False,
}

RESET_COLOR = "\033[0m"

# --- Sistema de Ayuda en Pantalla ---
HELP_TEXTS = {
    "dashboard_main": textwrap.dedent("""
        El Dashboard es el centro de control principal. Muestra el estado
        en tiempo real de tu sesión de trading y te da acceso a todas las
        demás funcionalidades.
    """),
    "position_viewer": textwrap.dedent("""
        Esta pantalla te permite ver y gestionar tus 'posiciones lógicas' abiertas.
    """),
    "auto_mode": textwrap.dedent("""
        El Panel de Control de Operación te permite gestionar una única estrategia
        de trading a la vez, desde su inicio hasta su fin.
    """),
    "config_editor": textwrap.dedent("""
        Aquí puedes ajustar los parámetros GLOBALES del bot para la sesión actual.
        Los cambios aquí NO se guardan permanentemente en tu archivo config.py.
    """)
}

def show_help_popup(help_key: str):
    text = HELP_TEXTS.get(help_key, "No hay ayuda disponible para esta sección.")
    clear_screen()
    print_tui_header(f"Ayuda: {help_key.replace('_', ' ').title()}")
    print(textwrap.dedent(text))
    press_enter_to_continue()

def press_enter_to_continue():
    input("\nPresiona Enter para continuar...")

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def _get_terminal_width():
    """Obtiene el ancho actual del terminal."""
    try:
        return shutil.get_terminal_size().columns
    except:
        return 90

def _clean_ansi_codes(text: str) -> str:
    """Función de ayuda para eliminar códigos de color ANSI de un string."""
    ansi_escape = re.compile(r'\x1B\[[0-?]*[ -/]*[@-~]')
    return ansi_escape.sub('', str(text))

def _truncate_text(text: str, max_length: int) -> str:
    """Trunca el texto si es muy largo, añadiendo '...' al final."""
    clean_text = _clean_ansi_codes(text)
    if len(clean_text) <= max_length:
        return text
    
    truncated_clean = clean_text[:max_length-3] + "..."
    
    # Intenta preservar el color si existe
    color_codes = re.findall(r'(\x1B\[[0-?]*[ -/]*[@-~])', text)
    if color_codes:
        return color_codes[0] + truncated_clean + RESET_COLOR
    return truncated_clean

def _create_config_box_line(content: str, width: int) -> str:
    """Crea una línea de caja de configuración con el contenido alineado."""
    clean_content = _clean_ansi_codes(content)
    # El padding se calcula restando 4 (dos bordes y dos espacios)
    padding = ' ' * max(0, width - len(clean_content) - 4)
    return f"│ {content}{padding} │"

def format_datetime_utc(dt_object: Optional[datetime.datetime], fmt: str = '%H:%M:%S %d-%m-%Y (UTC)') -> str:
    if not isinstance(dt_object, datetime.datetime): return "N/A"
    try:
        return dt_object.astimezone(timezone.utc).strftime(fmt)
    except (ValueError, TypeError):
        return "Invalid DateTime"

def print_tui_header(title: str, subtitle: Optional[str] = None, width: int = 90):
    """
    Imprime una cabecera TUI estandarizada, ahora con soporte para subtítulo.
    """
    # Usar el ancho del terminal dinámicamente si es posible
    effective_width = _get_terminal_width()
    
    print("=" * effective_width)
    print(f"{title.center(effective_width)}")
    if subtitle:
        print(f"{subtitle.center(effective_width)}")
    print("=" * effective_width)

class UserInputCancelled(Exception):
    """Excepción para ser lanzada cuando el usuario cancela un wizard de entrada."""
    pass

# --- INICIO DE LA MODIFICACIÓN (Función `get_input` a prueba de errores) ---
def get_input(
    prompt: str,
    type_func: Callable,
    default: Optional[Any] = None,
    min_val: Optional[float] = None,
    max_val: Optional[float] = None,
    is_optional: bool = False,
    context_info: Optional[str] = None
) -> Any:
    """
    Función robusta para obtener entrada del usuario con una UI consistente y validación.
    """
    while True:
        clear_screen()
        
        header_title = "Asistente de Entrada de Datos"
        if context_info:
            print_tui_header(header_title, subtitle=context_info)
        else:
            print_tui_header(header_title)
        
        prompt_parts = [f"\n  {prompt}"]
        
        default_display = default
        if is_optional and default is None:
            default_display = "DESACTIVADO"
        
        if default is not None:
            prompt_parts.append(f" (Actual: {default_display})")
        
        full_prompt = "".join(prompt_parts)
        print(full_prompt)
        
        help_parts = []
        if is_optional:
            help_parts.append("Presiona [Enter] para desactivar/limpiar el valor.")
        if default is not None and not is_optional:
            help_parts.append(f"Presiona [Enter] para usar el valor actual ({default_display}).")
        help_parts.append("Escribe 'c' y presiona [Enter] para cancelar.")
        
        print(f"  > {' | '.join(help_parts)}")
        
        try:
            val_str = input("\n  >> ").strip()

            if val_str.lower() == 'c':
                raise UserInputCancelled("Entrada cancelada por el usuario.")

            if not val_str:
                if is_optional:
                    return None
                if default is not None:
                    return default
                print("\n  \033[91mError: Este campo es obligatorio y no puede estar vacío.\033[0m")
                time.sleep(1.5)
                continue

            # CORRECCIÓN: Filtrar secuencias de escape ANSI antes de convertir
            cleaned_val_str = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', val_str)
            if not cleaned_val_str: # Si el resultado es una cadena vacía (solo eran secuencias)
                 print("\n  \033[91mError: Entrada inválida. Por favor, introduce un número o valor válido.\033[0m")
                 time.sleep(1.5)
                 continue

            value = type_func(cleaned_val_str)

            if min_val is not None and value < min_val:
                print(f"\n  \033[91mError: El valor debe ser como mínimo {min_val}.\033[0m")
                time.sleep(1.5)
                continue
            if max_val is not None and value > max_val:
                print(f"\n  \033[91mError: El valor no puede ser mayor que {max_val}.\033[0m")
                time.sleep(1.5)
                continue
            
            return value

        except UserInputCancelled:
            raise
        except (ValueError, TypeError):
            print(f"\n  \033[91mError: Entrada inválida. Introduce un valor de tipo '{type_func.__name__}'.\033[0m")
            time.sleep(1.5)
        except Exception as e:
            print(f"\n  \033[91mError inesperado: {e}\033[0m")
            time.sleep(1.5)
# --- FIN DE LA MODIFICACIÓN ---

def print_section(title: str, data: Dict[str, Any], is_account_balance: bool = False):
    print(f"\n--- {title} {'-' * (76 - len(title))}")
    if not data:
        print("  (No hay datos disponibles)")
        return
    if is_account_balance:
        for acc_name, balance_info in data.items():
            if balance_info and not isinstance(balance_info, str):
                equity = float(balance_info.get('totalEquity', 0.0))
                print(f"  {acc_name.upper():<15}: Equity: {equity:9.2f} USDT")
            else:
                print(f"  {acc_name.upper():<15}: (No se pudieron obtener datos de balance)")
    else:
        max_key_len = max(len(str(k)) for k in data.keys()) if data else 0
        for key, value in data.items():
            print(f"  {str(key):<{max_key_len + 2}}: {value}")