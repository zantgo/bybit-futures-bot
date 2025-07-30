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

# --- Estilo Visual Consistente para simple-term-menu ---
MENU_STYLE = {
    "menu_cursor": "> ",
    "menu_cursor_style": ("fg_yellow", "bold"),
    "menu_highlight_style": ("bg_cyan", "fg_black"),
    "cycle_cursor": True,
    "clear_screen": True,
}

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

def format_datetime_utc(dt_object: Optional[datetime.datetime], fmt: str = '%H:%M:%S %d-%m-%Y (UTC)') -> str:
    if not isinstance(dt_object, datetime.datetime): return "N/A"
    try:
        return dt_object.astimezone(timezone.utc).strftime(fmt)
    except (ValueError, TypeError):
        return "Invalid DateTime"

def print_tui_header(title: str, width: int = 80):
    timestamp_str = format_datetime_utc(datetime.datetime.now())
    print("=" * width)
    print(f"|{title.center(width - 2)}|")
    if timestamp_str: print(f"|{timestamp_str.center(width - 2)}|")
    print("=" * width)

class UserInputCancelled(Exception):
    """Excepción para ser lanzada cuando el usuario cancela un wizard de entrada."""
    pass

# --- INICIO DE LA VERSIÓN CORREGIDA Y DEFINITIVA ---
def get_input(
    prompt: str,
    type_func: Callable,
    default: Optional[Any] = None,
    min_val: Optional[float] = None,
    max_val: Optional[float] = None,
    is_optional: bool = False
) -> Any:
    """
    Función robusta para obtener entrada del usuario con validación.

    Args:
        is_optional (bool): Si es True, una entrada vacía devuelve None.
                            Si es False, una entrada vacía usa el default o da error.
    """
    while True:
        prompt_parts = [f"\n{prompt}"]
        
        default_display = default
        if is_optional and default is None:
            default_display = "DESACTIVADO"
        
        if default is not None:
            prompt_parts.append(f"[{default_display}]")
        
        options = ["'c' para cancelar"]
        if is_optional:
            options.append("Enter para desactivar")
            
        prompt_parts.append(f"(o {', '.join(options)}):")
        full_prompt = " ".join(prompt_parts) + " "
        
        try:
            val_str = input(full_prompt).strip()

            if val_str.lower() == 'c':
                raise UserInputCancelled("Entrada cancelada por el usuario.")

            if not val_str: # Usuario presionó Enter
                if is_optional:
                    return None # Desactivar campo opcional
                if default is not None:
                    return default # Usar default para campo obligatorio
                print("Error: Este campo es obligatorio y no puede estar vacío.")
                continue

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
            print(f"Error: Entrada inválida. Introduce un valor de tipo '{type_func.__name__}'.")
        except Exception as e:
            print(f"Error inesperado: {e}")
# --- FIN DE LA VERSIÓN CORREGIDA Y DEFINITIVA ---

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