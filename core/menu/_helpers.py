# =============== INICIO ARCHIVO: core/menu/_helpers.py (CORREGIDO FINAL V2) ===============
"""
Módulo de Ayuda para la TUI (Terminal User Interface).

Contiene funciones de utilidad reutilizables para la TUI, como limpiar la pantalla,
imprimir cabeceras estilizadas, obtener entrada del usuario de forma robusta,
y formatear secciones de información para mantener un estilo visual consistente
inspirado en la claridad y legibilidad.
"""
import os
import datetime
from typing import Dict, Any, Optional, Callable

# --- Dependencias del Proyecto (importaciones seguras) ---
try:
    from core import _utils
except ImportError:
    # Fallback si el módulo no está disponible
    _utils = None

# --- Estilo Visual Consistente para simple-term-menu ---
# Inspirado en la paleta de colores del instalador de Debian (alto contraste)
MENU_STYLE = {
    "menu_cursor": "> ",
    "menu_cursor_style": ("fg_yellow", "bold"),
    "menu_highlight_style": ("bg_cyan", "fg_black"),
    "cycle_cursor": True,
    "clear_screen": True,
}

# --- Funciones de Utilidad de la Terminal ---

def clear_screen():
    """Limpia la pantalla de la terminal."""
    os.system('cls' if os.name == 'nt' else 'clear')

def print_tui_header(title: str, width: int = 80):
    """
    Imprime una cabecera estilizada y consistente para cada pantalla de la TUI.
    """
    timestamp_str = ""
    if _utils and hasattr(_utils, 'format_datetime'):
        timestamp_str = _utils.format_datetime(datetime.datetime.now())

    print("=" * width)
    print(f"|{' ' * (width - 2)}|")
    print(f"|{title.center(width - 2)}|")
    if timestamp_str:
        print(f"|{timestamp_str.center(width - 2)}|")
    print(f"|{' ' * (width - 2)}|")
    print("=" * width)

# --- INICIO MODIFICACIÓN: Eliminar función errónea ---
# La función `add_menu_footer` ha sido eliminada por completo
# porque causaba un AttributeError.
# --- FIN MODIFICACIÓN ---

def get_input(
    prompt: str,
    type_func: Callable = str,
    default: Optional[Any] = None,
    min_val: Optional[float] = None,
    max_val: Optional[float] = None
) -> Any:
    """
    Función robusta para obtener entrada del usuario con validación de tipo,
    valor por defecto y rangos opcionales.
    """
    while True:
        try:
            prompt_full = f"{prompt}"
            if default is not None:
                prompt_full += f" (actual: {default})"
            prompt_full += ": "

            val_str = input(prompt_full).strip()

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
        except (ValueError, TypeError):
            print(f"Error: Entrada inválida. Por favor, introduce un valor de tipo '{type_func.__name__}'.")
        except Exception as e:
            print(f"Error inesperado: {e}")

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
                margin = float(balance_info.get('totalMarginBalance', 0.0))
                available = float(balance_info.get('totalAvailableBalance', 0.0))
                
                print(f"  {acc_name.upper():<15}: ", end="")
                print(f"Equity: {equity:9.2f} USDT | ", end="")
                print(f"En Uso: {margin:8.2f} USDT | ", end="")
                print(f"Disponible: {available:8.2f} USDT")
            else:
                print(f"  {acc_name.upper():<15}: (No se pudieron obtener datos de balance)")
    else:
        max_key_len = max(len(str(k)) for k in data.keys()) if data else 0
        for key, value in data.items():
            print(f"  {str(key):<{max_key_len + 2}}: {value}")

def press_enter_to_continue():
    """Pausa la ejecución y espera a que el usuario presione Enter."""
    input("\nPresiona Enter para continuar...")

# =============== FIN ARCHIVO: core/menu/_helpers.py (CORREGIDO FINAL V2) ===============