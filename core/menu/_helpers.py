"""
Módulo de Ayuda para la TUI (Terminal User Interface).

Contiene funciones de utilidad reutilizables para la TUI, como limpiar la pantalla,
imprimir cabeceras estilizadas, obtener entrada del usuario de forma robusta,
y formatear secciones de información.

v3.1: Actualizado el formato de fecha a UTC estándar para trading.
"""
import os
import datetime
# ¡Importante! Añadimos timezone para la conversión a UTC.
from datetime import timezone
import textwrap
from typing import Dict, Any, Optional, Callable

# --- Dependencias del Proyecto (importaciones seguras) ---
# Se mantiene igual, no necesita cambios.
try:
    from core import _utils
except ImportError:
    _utils = None

# --- Estilo Visual Consistente para simple-term-menu ---
# Se mantiene igual, no necesita cambios.
MENU_STYLE = {
    "menu_cursor": "> ",
    "menu_cursor_style": ("fg_yellow", "bold"),
    "menu_highlight_style": ("bg_cyan", "fg_black"),
    "cycle_cursor": True,
    "clear_screen": True,
}

# --- Sistema de Ayuda en Pantalla ---
# Se mantiene igual, no necesita cambios.
HELP_TEXTS = {
    # Pantalla Dashboard
    "dashboard_main": textwrap.dedent("""
        El Dashboard es el centro de control principal. Muestra el estado
        en tiempo real de tu sesión de trading y te da acceso a todas las
        demás funcionalidades.
        
        - PNL Total: Suma del beneficio/pérdida de trades cerrados (realizado)
          y de tus posiciones actualmente abiertas (no realizado).
        - ROI Actual: El retorno de la inversión total basado en tu capital inicial.
        - Límites de Sesión: Disyuntores de seguridad que detienen el trading
          (o lo pausan) si se alcanzan ciertos umbrales de pérdida/ganancia o tiempo.
    """),
    
    # Pantalla de Posiciones
    "position_viewer": textwrap.dedent("""
        Esta pantalla te permite ver y gestionar tus 'posiciones lógicas' abiertas.
        Cada vez que el bot compra o vende, crea una nueva posición lógica.
        
        - PNL: Beneficio o pérdida no realizado para esa posición específica
          al precio de mercado actual.
        - SL: El precio de 'Stop Loss' fijo. Si el mercado llega a este precio,
          la posición se cerrará automáticamente para limitar pérdidas.
        - TS (Trailing Stop): Un stop loss dinámico. Se activa cuando la posición
          alcanza un cierto % de ganancia y luego 'sigue' al precio para asegurar
          beneficios si el mercado se revierte.
        - Puedes forzar el cierre de cualquier posición manualmente desde aquí.
    """),
    
    # Pantalla Modo Manual
    "manual_mode": textwrap.dedent("""
        El Modo Manual Guiado te permite dirigir la estrategia del bot.
        
        - LONG_ONLY: El bot solo buscará y abrirá posiciones de compra (largos).
        - SHORT_ONLY: El bot solo buscará y abrirá posiciones de venta (cortos).
        - LONG_SHORT: El bot puede abrir ambos tipos de posiciones.
        - NEUTRAL: El bot no abrirá ninguna posición nueva, pero gestionará las
          existentes (SL, TS, etc.).
          
        Puedes establecer 'Límites para la Próxima Tendencia'. Estos límites (de
        tiempo, trades o ROI) se activarán automáticamente la próxima vez que
        cambies de NEUTRAL a un modo de trading activo.
    """),

    # Pantalla Modo Automático
    "auto_mode": textwrap.dedent("""
        El Modo Automático te permite construir un 'Árbol de Decisiones' para que
        el bot reaccione a condiciones de mercado específicas.
        
        - Hito (Milestone): Es una regla 'SI... ENTONCES...'.
        - Condición: 'SI el precio sube por encima de X...'
        - Acción: 'ENTONCES iniciar una tendencia LONG_ONLY'.
        
        Puedes anidar Hitos. Un hito de Nivel 2 solo se activará si su hito
        padre de Nivel 1 se cumple primero. Cuando un hito se cumple, sus
        'hermanos' (los otros hitos del mismo nivel) se cancelan.
    """),

    # Pantalla Editor de Configuración
    "config_editor": textwrap.dedent("""
        Aquí puedes ajustar los parámetros del bot para la sesión actual.
        Los cambios que hagas aquí NO se guardan permanentemente en tu archivo
        config.py, solo afectan a esta ejecución del bot.
        
        - Ticker: Símbolo del activo y frecuencia de actualización.
        - Estrategia: Parámetros numéricos que definen cuándo se genera
          una señal de compra o venta (EMA, márgenes, etc.).
        - Gestión de Capital: Define cuánto capital usar por operación (Tamaño Base),
          cuántas operaciones simultáneas tener (Máx. Posiciones) y el apalancamiento.
        - Gestión de Riesgo: Define los Stop Loss y Trailing Stops individuales.
        - Límites de Sesión: Define los disyuntores globales para toda la cuenta.
    """)
}

# La función show_help_popup se mantiene igual.
def show_help_popup(help_key: str):
    """Muestra una ventana de ayuda con el texto correspondiente a la clave."""
    if help_key not in HELP_TEXTS:
        text = "No hay ayuda disponible para esta sección."
    else:
        text = HELP_TEXTS[help_key]
    
    clear_screen()
    print_tui_header(f"Ayuda: {help_key.replace('_', ' ').title()}")
    print(text)
    press_enter_to_continue()


def press_enter_to_continue():
    """Pausa la ejecución y espera a que el usuario presione Enter."""
    input("\nPresiona Enter para continuar...")
    

# --- Funciones de Utilidad de la Terminal ---

def clear_screen():
    """Limpia la pantalla de la terminal."""
    os.system('cls' if os.name == 'nt' else 'clear')


# --- INICIO DEL CÓDIGO CORREGIDO ---

# A diferencia de la importación desde _utils, esta función ahora vive aquí
# para ser usada por print_tui_header, garantizando el formato UTC.
def format_datetime_utc(dt_object: Optional[datetime.datetime], fmt: str = '%H:%M:%S %d-%m-%Y (UTC)') -> str:
    """
    Formatea un objeto datetime a string en formato UTC, manejando None.
    """
    # Usamos el objeto global _utils si está disponible, si no, lo hacemos manualmente.
    # Esto es por si esta función se necesita antes de que _utils esté completamente inicializado.
    
    # Primero, validamos que el input es un objeto datetime
    if not isinstance(dt_object, datetime.datetime):
        return "N/A"

    try:
        # Convertir a UTC. Si el objeto es "naive" (sin tzinfo), se asume que es
        # la hora local del sistema y se convierte a UTC.
        # Si ya tiene zona horaria, se convierte correctamente a UTC.
        dt_utc = dt_object.astimezone(timezone.utc)
        return dt_utc.strftime(fmt)
    except (ValueError, TypeError):
        # En caso de cualquier error de formateo, devolvemos un mensaje claro.
        return "Invalid DateTime"

def print_tui_header(title: str, width: int = 80):
    """
    Imprime una cabecera estilizada y consistente para cada pantalla de la TUI.
    Ahora utiliza la nueva función de formateo UTC.
    """
    # Llamamos a nuestra nueva función local para obtener el timestamp en UTC.
    timestamp_str = format_datetime_utc(datetime.datetime.now())

    print("=" * width)
    print(f"|{' ' * (width - 2)}|")
    print(f"|{title.center(width - 2)}|")
    if timestamp_str:
        print(f"|{timestamp_str.center(width - 2)}|")
    print(f"|{' ' * (width - 2)}|")
    print("=" * width)

# --- FIN DEL CÓDIGO CORREGIDO ---


# --- El resto de las funciones se mantienen 100% idénticas ---

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