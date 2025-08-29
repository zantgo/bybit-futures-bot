"""
Módulo de Ayuda para la TUI (Terminal User Interface).

v4.4 (Ayuda y Robustez Completas):
- Se han añadido textos de ayuda detallados para TODAS las pantallas de la TUI,
  incluyendo el menú principal y los submenús del asistente de configuración.
- La función `get_input` ha sido mejorada para filtrar caracteres de escape
  (ANSI escape codes), evitando errores al pegar texto en la terminal.
- Se ha revisado la consistencia de los estilos y funciones.

v4.2 (get_input Definitivo):
- Refactorizada la función get_input para ser explícita en su comportamiento.
"""
import os
import datetime
from datetime import timezone
import textwrap
from typing import Dict, Any, Optional, Callable
import shutil
import re
import time

# --- Estilo Visual Consistente para simple-term-menu ---
MENU_STYLE = {
    "menu_cursor": "> ",
    "menu_cursor_style": ("fg_yellow", "bold"),
    "menu_highlight_style": ("bg_cyan", "fg_black"),
    "cycle_cursor": True,
    "clear_screen": False, # Se gestionará manualmente para evitar errores
}

RESET_COLOR = "\033[0m"

# ==============================================================================
# --- DICCIONARIO DE AYUDA COMPLETAMENTE ACTUALIZADO ---
# ==============================================================================

HELP_TEXTS = {
    # --- Pantallas Principales ---
    "welcome_screen": textwrap.dedent("""
        AYUDA: PANTALLA DE BIENVENIDA

        Este es el punto de partida del bot. Se encarga de la preparación
        y validación antes de iniciar cualquier operación.

        Funcionalidades Clave:
        - Estado de Conexión: Verifica si tus claves API son válidas.
        - Balances: Muestra los fondos disponibles en cada cuenta.
        - Configuración General: Resume los parámetros globales del bot.

        Acciones Disponibles:
        - Iniciar Sesión: Comienza el monitoreo del mercado y te lleva al Dashboard.
        - Pruebas (Transferencias/Posiciones): Herramientas de diagnóstico para
          asegurar que tus cuentas y permisos API funcionan correctamente.
        - Configuración General: Edita parámetros como el Símbolo del Ticker
          o el modo Paper/Live Trading.
    """),

    "dashboard_main": textwrap.dedent("""
        AYUDA: DASHBOARD DE LA SESIÓN

        Este es tu centro de mando durante una sesión de trading activa. Ofrece
        una vista en tiempo real de toda la operación.

        Funcionalidades Clave:
        - Paneles de Información: Muestran el rendimiento global (PNL, Equity),
          la señal de trading actual (BUY/SELL/HOLD) basada en los indicadores
          técnicos, y una comparativa de tus estrategias LONG y SHORT.

        Acciones Disponibles:
        - Gestionar Operación: Profundiza en una estrategia (LONG o SHORT) para
          ver su panel de control detallado.
        - Editar Configuración de Sesión: Ajusta los parámetros de la estrategia
          (ej. períodos de EMA) en tiempo real, sin reiniciar.
    """),

    # --- Pantallas de Gestión de Operación ---
    "auto_mode": textwrap.dedent("""
        AYUDA: PANEL DE CONTROL DE OPERACIÓN

        Esta es la vista de gestión detallada para UNA ÚNICA estrategia.
        Aquí controlas y monitoreas su ciclo de vida completo.

        Funcionalidades Clave:
        - Paneles de Información: Desglose completo de capital, rendimiento (PNL, ROI),
          riesgo (precio de liquidación estimado) y parámetros actuales.
        - Lista de Posiciones: Muestra cada "posición lógica" (lote de capital),
          diferenciando entre las ABIERTAS y las PENDIENTES.

        Acciones (varían según el estado de la operación):
        - Configurar e Iniciar: Lanza el asistente para crear una nueva estrategia.
        - Gestionar Posiciones Manualmente: Permite abrir/cerrar posiciones de
          forma inmediata, ideal para intervenciones rápidas.
        - Pausar/Reanudar: Controla si la estrategia puede abrir nuevas posiciones.
        - Modificar Parámetros: Abre el asistente para ajustar la estrategia actual.
        - Detener Operación: Cierra todas las posiciones y resetea la estrategia.
    """),

    "wizard_main": textwrap.dedent("""
        AYUDA: ASISTENTE DE CONFIGURACIÓN DE OPERACIÓN

        Este es el asistente principal para crear o modificar una estrategia.
        Cada opción te llevará a un submenú para ajustar una parte específica
        de la configuración de tu operación.

        Categorías de Configuración:
        - Gestionar Lista de Posiciones: Define tu gestión de capital: número
          de entradas y el capital asignado a cada una. Es la sección más
          importante para controlar tu exposición y riesgo.
        - Estrategia Global: Ajusta parámetros que afectan a toda la operación,
          como el apalancamiento y la distancia entre promediaciones.
        - Riesgo por Posición Individual: Define los "salvavidas" para cada
          entrada individual (Stop Loss y Trailing Stop Loss).
        - Gestión de Riesgo de Operación: Define "salvavidas" para el rendimiento
          TOTAL de la operación, basados en el ROI global.
        - Condiciones de Entrada/Salida: Automatiza cuándo debe empezar, pausarse
          o detenerse tu estrategia basándose en precios, tiempo o número de trades.
    """),

    # --- Ayuda para Submenús del Asistente ---
    "wizard_position_editor": textwrap.dedent("""
        AYUDA: EDITOR DE POSICIONES Y RIESGO

        Esta pantalla es clave para tu GESTIÓN DE CAPITAL Y RIESGO.

        Funcionalidades:
        - Lista de Posiciones: Añade, modifica o elimina "posiciones lógicas"
          pendientes. Cada posición representa un lote de capital que el bot
          puede usar para entrar al mercado.
        - Panel de Riesgo: Esta es una herramienta de SIMULACIÓN en tiempo real.
          Muestra cómo tus cambios en el capital y el número de posiciones
          afectan a métricas críticas como:
          - Precio de Liquidación Proyectado: El precio al que tu posición
            total sería liquidada si todas las posiciones se abrieran.
          - Cobertura: El rango de precios que tu estrategia puede "soportar"
            antes de alcanzar la liquidación.
          - Distancia a Liquidación: Tu margen de seguridad actual.

        Usa esta pantalla para balancear tu exposición al riesgo antes de lanzar
        la operación.
    """),
        
    "wizard_strategy_global": textwrap.dedent("""
        AYUDA: ESTRATEGIA GLOBAL

        Aquí se definen los parámetros fundamentales que aplican a toda la operación.

        Opciones:
        - Apalancamiento: Multiplicador fijo para todas las posiciones. Un mayor
          apalancamiento aumenta tanto las ganancias como las pérdidas potenciales.
        - Distancia de Promediación: El porcentaje que debe moverse el precio
          en tu contra desde la última entrada para que el bot considere abrir
          una nueva posición. Un valor más alto es más conservador.
        - Reinversión Automática: Si se activa, una porción de las ganancias de
          cada trade cerrado se añadirá automáticamente al capital de las
          posiciones pendientes, creando un efecto de interés compuesto.
    """),

    "wizard_risk_individual": textwrap.dedent("""
        AYUDA: RIESGO POR POSICIÓN INDIVIDUAL

        Define las redes de seguridad para cada entrada individual en el mercado.

        Opciones:
        - SL Individual (%): Stop Loss basado en un porcentaje de pérdida sobre
          el capital de esa posición. Si se alcanza, solo esa posición se cierra.
        - Activación TSL (%): Trailing Stop Loss. Define el porcentaje de ganancia
          al que se activará el trailing stop.
        - Distancia TSL (%): Una vez activado, el TSL seguirá el precio a esta
          distancia porcentual, asegurando ganancias si el precio se revierte.
    """),

    "wizard_risk_operation": textwrap.dedent("""
        AYUDA: GESTIÓN DE RIESGO DE OPERACIÓN (BASADO EN ROI)

        Define las redes de seguridad para el rendimiento GLOBAL de toda la operación,
        basándose en el Retorno sobre la Inversión (ROI).

        Opciones:
        - Límite SL/TP por ROI: Establece un objetivo de pérdida máxima (SL) o
          ganancia (TP) para toda la estrategia. Puede ser un % fijo o dinámico
          (que sigue tus ganancias realizadas).
        - Límite TSL por ROI: Un trailing stop sobre el ROI total. Permite que
          tus ganancias crezcan mientras protege una parte de ellas.
        - Acción al alcanzar Límite: Define qué hará el bot si se activa uno de
          estos límites: 'PAUSAR' (deja de abrir nuevas posiciones) o 'DETENER'
          (cierra todo y resetea la operación).
    """),

    "wizard_entry_conditions": textwrap.dedent("""
        AYUDA: CONDICIONES DE ENTRADA

        Define las reglas que deben cumplirse para que la operación se active
        y empiece a buscar oportunidades de trading. Si no se define ninguna,
        la operación se activa de forma inmediata (a mercado).

        Opciones (se activa con la primera que se cumpla):
        - Precio SUPERIOR a: La operación se activa si el precio del mercado
          supera el valor que establezcas.
        - Precio INFERIOR a: La operación se activa si el precio cae por debajo
          del valor que establezcas.
        - Temporizador: La operación se activa después de que haya transcurrido
          un número determinado de minutos.
    """),

    "wizard_exit_conditions": textwrap.dedent("""
        AYUDA: CONDICIONES DE SALIDA

        Define reglas automáticas para pausar o detener la operación basadas en
        límites operativos, no en el rendimiento.

        Opciones (se ejecuta la primera que se cumpla):
        - Salida por Precio: Pausa o detiene la operación si el precio del mercado
          alcanza un nivel de precio específico. Útil para invalidar una
          estrategia si el contexto del mercado cambia drásticamente.
        - Límite de Duración: Establece un tiempo máximo de vida para la operación.
        - Límite de Trades: Fija un número máximo de trades cerrados.
    """),
        
    # --- Ayudas Genéricas ---
    "general_config_editor": textwrap.dedent("""
        AYUDA: EDITOR DE CONFIGURACIÓN GENERAL

        Aquí puedes ajustar los parámetros GLOBALES del bot. Estos cambios
        afectan a toda la aplicación y se aplican inmediatamente.

        Parámetros Clave:
        - Exchange: Define con qué plataforma de trading operará el bot.
        - Modo (Live/Paper): Cambia entre operar con dinero real (Live) o en un
          entorno simulado sin riesgo (Paper Trading).
        - Testnet: Activa el modo de prueba del exchange (requiere claves API
          de Testnet).
        - Símbolo del Ticker: Cambia el activo que el bot operará. El nuevo
          símbolo se valida en tiempo real para asegurar que existe.
    """),
    
    "session_config_editor": textwrap.dedent("""
        AYUDA: EDITOR DE CONFIGURACIÓN DE SESIÓN

        Este editor te permite ajustar los parámetros que definen el
        comportamiento de tu ESTRATEGIA de trading en tiempo real.

        Los cambios realizados aquí afectan a la sesión actual inmediatamente
        pero NO se guardan permanentemente en tu archivo 'config.py'.

        Parámetros Clave:
        - Ticker: Intervalo de actualización de precios.
        - Análisis Técnico (TA): Períodos para indicadores como la EMA.
        - Señal: Umbrales que determinan cuándo se genera una señal de compra/venta.
        - Profit y Riesgo: Configuración de comisiones, reinversión y tasas
          de margen de mantenimiento.
    """)
}

def show_help_popup(help_key: str):
    text = HELP_TEXTS.get(help_key, "No hay ayuda disponible para esta sección.")
    # --- SOLUCIÓN AL ERROR AssertionError ---
    # La pantalla de ayuda debe limpiar la pantalla para mostrarse correctamente.
    clear_screen()
    print_tui_header(f"Ayuda: {help_key.replace('_', ' ').title()}")
    print(textwrap.dedent(text))
    press_enter_to_continue()

def press_enter_to_continue():
    input("\nPresiona Enter para continuar...")

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def _get_terminal_width():
    try:
        return shutil.get_terminal_size().columns
    except:
        return 90

def _clean_ansi_codes(text: str) -> str:
    ansi_escape = re.compile(r'\x1B\[[0-?]*[ -/]*[@-~]')
    return ansi_escape.sub('', str(text))

def _truncate_text(text: str, max_length: int) -> str:
    clean_text = _clean_ansi_codes(text)
    if len(clean_text) <= max_length:
        return text
    
    truncated_clean = clean_text[:max_length-3] + "..."
    color_codes = re.findall(r'(\x1B\[[0-?]*[ -/]*[@-~])', text)
    if color_codes:
        return color_codes[0] + truncated_clean + RESET_COLOR
    return truncated_clean

def _create_config_box_line(content: str, width: int) -> str:
    clean_content = _clean_ansi_codes(content)
    padding = ' ' * max(0, width - len(clean_content) - 4)
    return f"│ {content}{padding} │"

def format_datetime_utc(dt_object: Optional[datetime.datetime], fmt: str = '%H:%M:%S %d-%m-%Y (UTC)') -> str:
    if not isinstance(dt_object, datetime.datetime): return "N/A"
    try:
        return dt_object.astimezone(timezone.utc).strftime(fmt)
    except (ValueError, TypeError):
        return "Invalid DateTime"

def print_tui_header(title: str, subtitle: Optional[str] = None, width: int = 90):
    effective_width = _get_terminal_width()
    print("=" * effective_width)
    print(f"{title.center(effective_width)}")
    if subtitle:
        print(f"{subtitle.center(effective_width)}")
    print("=" * effective_width)

class UserInputCancelled(Exception):
    """Excepción para ser lanzada cuando el usuario cancela un wizard de entrada."""
    pass

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
                print("\n  \033[91mError: Este campo es obligatorio.\033[0m"); time.sleep(1.5); continue

            # Filtra secuencias de escape ANSI antes de la conversión
            cleaned_val_str = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', val_str)
            if not cleaned_val_str:
                 print("\n  \033[91mError: Entrada inválida.\033[0m"); time.sleep(1.5); continue

            value = type_func(cleaned_val_str)

            if min_val is not None and value < min_val:
                print(f"\n  \033[91mError: El valor debe ser >= {min_val}.\033[0m"); time.sleep(1.5); continue
            if max_val is not None and value > max_val:
                print(f"\n  \033[91mError: El valor debe ser <= {max_val}.\033[0m"); time.sleep(1.5); continue
            
            return value

        except UserInputCancelled:
            raise
        except (ValueError, TypeError):
            print(f"\n  \033[91mError: Entrada inválida. Tipo esperado: '{type_func.__name__}'.\033[0m"); time.sleep(1.5)
        except Exception as e:
            print(f"\n  \033[91mError inesperado: {e}\033[0m"); time.sleep(1.5)

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
                print(f"  {acc_name.upper():<15}: (No se pudieron obtener datos)")
    else:
        max_key_len = max(len(str(k)) for k in data.keys()) if data else 0
        for key, value in data.items():
            print(f"  {str(key):<{max_key_len + 2}}: {value}")