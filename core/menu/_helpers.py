"""
Módulo de Ayuda para la TUI (Terminal User Interface).

v3.7 (get_input Refinado):
- La función `get_input` ahora muestra el prompt de 'desactivar' solo si
  se le proporciona explícitamente un `disable_value`.
- Esto permite tener campos obligatorios (sin opción 'd') y opcionales
  (con opción 'd') en los asistentes.
- La opción 'c' para cancelar se mantiene universal y lanza una excepción.
"""
import os
import datetime
from datetime import timezone
import textwrap
from typing import Dict, Any, Optional, Callable

# --- Dependencias del Proyecto (importaciones seguras) ---
try:
    from core import _utils
except ImportError:
    _utils = None

# --- Estilo Visual Consistente para simple-term-menu ---
MENU_STYLE = {
    "menu_cursor": "> ",
    "menu_cursor_style": ("fg_yellow", "bold"),
    "menu_highlight_style": ("bg_cyan", "fg_black"),
    "cycle_cursor": True,
    "clear_screen": True,
}

# --- Sistema de Ayuda en Pantalla (sin cambios) ---
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
    """Muestra una ventana de ayuda con el texto correspondiente a la clave."""
    text = HELP_TEXTS.get(help_key, "No hay ayuda disponible para esta sección.")
    clear_screen()
    print_tui_header(f"Ayuda: {help_key.replace('_', ' ').title()}")
    print(textwrap.dedent(text))
    press_enter_to_continue()


def press_enter_to_continue():
    """Pausa la ejecución y espera a que el usuario presione Enter."""
    input("\nPresiona Enter para continuar...")
    

# --- Funciones de Utilidad de la Terminal ---

def clear_screen():
    """Limpia la pantalla de la terminal."""
    os.system('cls' if os.name == 'nt' else 'clear')

def format_datetime_utc(dt_object: Optional[datetime.datetime], fmt: str = '%H:%M:%S %d-%m-%Y (UTC)') -> str:
    """Formatea un objeto datetime a string en formato UTC, manejando None."""
    if not isinstance(dt_object, datetime.datetime):
        return "N/A"
    try:
        dt_utc = dt_object.astimezone(timezone.utc)
        return dt_utc.strftime(fmt)
    except (ValueError, TypeError):
        return "Invalid DateTime"

def print_tui_header(title: str, width: int = 80):
    """Imprime una cabecera estilizada y consistente para cada pantalla de la TUI."""
    timestamp_str = format_datetime_utc(datetime.datetime.now())
    print("=" * width)
    print(f"|{title.center(width - 2)}|")
    if timestamp_str:
        print(f"|{timestamp_str.center(width - 2)}|")
    print("=" * width)


class UserInputCancelled(Exception):
    """Excepción para ser lanzada cuando el usuario cancela un wizard de entrada."""
    pass

# --- INICIO DE LA MODIFICACIÓN: get_input final y robusto ---
def get_input(
    prompt: str,
    type_func: Callable = str,
    default: Optional[Any] = None,
    min_val: Optional[float] = None,
    max_val: Optional[float] = None,
    disable_value: Any = "<NOT_SET>" # Usamos una señal interna para detectar si se pasó el argumento
) -> Any:
    """
    Función robusta para obtener entrada del usuario con validación.
    - Presionar 'c' siempre cancela y lanza UserInputCancelled.
    - Presionar 'd' solo funciona si se proporciona un `disable_value`, y devuelve ese valor.
    """
    is_disableable = disable_value != "<NOT_SET>"

    while True:
        try:
            prompt_full = f"{prompt}"
            
            if default is not None:
                prompt_full += f" [{default}]"
            
            # Construir el prompt de opciones dinámicamente
            options = ["'c' para cancelar"]
            if is_disableable:
                options.append("'d' para desactivar")
            prompt_full += f" [o {', '.join(options)}]: "

            val_str = input(prompt_full).strip()
            
            if val_str.lower() == 'c':
                raise UserInputCancelled("Entrada cancelada por el usuario.")

            if is_disableable and val_str.lower() == 'd':
                return disable_value

            if not val_str and default is not None:
                return default

            value = type_func(val_str)

            if min_val is not None and value < min_val:
                print(f"Error: El valor debe ser como mínimo {min_val}.")
                continue
            if max_val is not None and value > max_val:
                print(f"Error: El valor no puede ser mayor que {max_val}.")
                continue

            return value
        except UserInputCancelled:
            raise
        except (ValueError, TypeError):
            print(f"Error: Entrada inválida. Por favor, introduce un valor de tipo '{type_func.__name__}'.")
        except Exception as e:
            print(f"Error inesperado: {e}")
# --- FIN DE LA MODIFICACIÓN ---

def print_section(title: str, data: Dict[str, Any], is_account_balance: bool = False):
    """
    Imprime una sección de datos de manera formateada y legible.
    """
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