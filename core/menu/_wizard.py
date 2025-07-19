# =============== INICIO ARCHIVO: core/menu/_wizard.py ===============
"""
Módulo del Asistente de Configuración Inicial (Wizard) para la TUI.

Contiene toda la lógica para guiar al usuario a través de la configuración
inicial antes de lanzar el bot en modo live. Este flujo es lineal y se asegura
de que el bot tenga los parámetros mínimos necesarios para operar.
"""
import time
from typing import Optional, Tuple, Dict, Any

try:
    from simple_term_menu import TerminalMenu
except ImportError:
    # Si la librería no está, se define un fallback para evitar errores de importación.
    # El programa principal debería detectar esto y terminar.
    TerminalMenu = None

# --- Dependencias del Proyecto ---
try:
    import config
    # Importar helpers del mismo paquete
    from ._helpers import clear_screen, print_tui_header, get_input, MENU_STYLE, press_enter_to_continue
except ImportError:
    # Definir fallbacks si las importaciones fallan
    config = None
    # Definir funciones dummy para que el resto del código no falle
    def clear_screen(): print("\033c", end="")
    def print_tui_header(title): print(f"--- {title} ---")
    def get_input(prompt, type_func, default): return default
    def press_enter_to_continue(): input("Press Enter...")
    MENU_STYLE = {}

# --- Lógica de los Pasos del Asistente (Funciones Privadas) ---

def _wizard_step_symbol() -> str:
    """Paso 1: Configurar el símbolo del ticker."""
    clear_screen()
    print_tui_header("PASO 1 de 4: SÍMBOLO DEL TICKER")
    print("\nEste es el par de trading que el bot monitoreará (ej: BTCUSDT, ETHUSDT).")

    default_symbol = getattr(config, 'TICKER_SYMBOL', 'BTCUSDT')
    symbol = get_input("\nIntroduce el símbolo del ticker", str, default_symbol).upper()

    setattr(config, 'TICKER_SYMBOL', symbol)
    print(f"\n✅ Símbolo establecido en: {symbol}")
    time.sleep(1.5)
    return symbol

def _wizard_step_capital() -> Tuple[float, int]:
    """Paso 2: Configurar el capital (tamaño base y slots)."""
    clear_screen()
    print_tui_header("PASO 2 de 4: GESTIÓN DE CAPITAL")
    print("\nDefine cuánto capital arriesgar y cuántas posiciones simultáneas permitir.")

    default_base_size = float(getattr(config, 'POSITION_BASE_SIZE_USDT', 10.0))
    base_size = get_input("\nTamaño base por posición (USDT)", float, default_base_size, min_val=1.0)

    default_slots = int(getattr(config, 'POSITION_MAX_LOGICAL_POSITIONS', 1))
    slots = get_input("Número máximo de posiciones (slots) por lado", int, default_slots, min_val=1)

    print(f"\n✅ Configuración de capital: {slots} posiciones de ~{base_size:.2f} USDT cada una.")
    time.sleep(1.5)
    return base_size, slots

def _wizard_step_risk_profile() -> Dict[str, Any]:
    """Paso 3: Seleccionar un perfil de riesgo inicial."""
    clear_screen()
    print_tui_header("PASO 3 de 4: PERFIL DE RIESGO INICIAL")
    print("\nSelecciona un perfil de riesgo para los parámetros iniciales.")
    print("Esto ajustará el Stop Loss y Trailing Stop. Podrás modificarlos más tarde.")

    risk_profiles = {
        "Conservador": {"sl": 5.0, "ts_act": 2.0, "ts_dist": 1.0},
        "Moderado": {"sl": 10.0, "ts_act": 1.0, "ts_dist": 0.5},
        "Agresivo": {"sl": 15.0, "ts_act": 0.5, "ts_dist": 0.2},
    }

    menu_items = [
        f"[1] Conservador (SL: {risk_profiles['Conservador']['sl']:.1f}%, TS: {risk_profiles['Conservador']['ts_act']:.1f}%/{risk_profiles['Conservador']['ts_dist']:.1f}%)",
        f"[2] Moderado    (SL: {risk_profiles['Moderado']['sl']:.1f}%, TS: {risk_profiles['Moderado']['ts_act']:.1f}%/{risk_profiles['Moderado']['ts_dist']:.1f}%)",
        f"[3] Agresivo    (SL: {risk_profiles['Agresivo']['sl']:.1f}%, TS: {risk_profiles['Agresivo']['ts_act']:.1f}%/{risk_profiles['Agresivo']['ts_dist']:.1f}%)",
    ]

    terminal_menu = TerminalMenu(
        menu_items,
        title="Elige un perfil de riesgo para empezar:",
        **MENU_STYLE
    )
    choice_index = terminal_menu.show()

    if choice_index == 0:
        profile_name = "Conservador"
    elif choice_index == 1:
        profile_name = "Moderado"
    elif choice_index == 2:
        profile_name = "Agresivo"
    else:
        # Si el usuario cancela (ESC), se asume moderado por defecto.
        print("\nSelección cancelada. Se aplicará el perfil 'Moderado' por defecto.")
        profile_name = "Moderado"

    selected_profile_params = risk_profiles[profile_name]

    # Actualizar la configuración global del bot
    setattr(config, 'POSITION_INDIVIDUAL_STOP_LOSS_PCT', selected_profile_params['sl'])
    setattr(config, 'TRAILING_STOP_ACTIVATION_PCT', selected_profile_params['ts_act'])
    setattr(config, 'TRAILING_STOP_DISTANCE_PCT', selected_profile_params['ts_dist'])

    print(f"\n✅ Perfil de riesgo '{profile_name}' aplicado.")
    time.sleep(1.5)
    return {"name": profile_name, **selected_profile_params}

def _wizard_step_confirmation(config_summary: Dict[str, Any]) -> bool:
    """Paso 4: Mostrar el resumen y pedir confirmación final."""
    clear_screen()
    print_tui_header("PASO 4 de 4: CONFIRMACIÓN FINAL")
    print("\nRevisa la configuración de tu sesión de trading:")

    # Formatear el resumen para mostrarlo
    risk_profile = config_summary['risk_profile']
    print("\n" + "="*40)
    print(f"  Símbolo:        {config_summary['symbol']}")
    print(f"  Tamaño Base:    {config_summary['base_size']:.2f} USDT")
    print(f"  Slots por Lado: {config_summary['slots']}")
    print("-" * 40)
    print(f"  Perfil Riesgo:  {risk_profile['name']}")
    print(f"    - SL Fijo:    {risk_profile['sl']:.2f}%")
    print(f"    - Trail Stop: Activ. {risk_profile['ts_act']:.2f}% / Dist. {risk_profile['ts_dist']:.2f}%")
    print("-" * 40)
    print(f"  Apalancamiento: {getattr(config, 'POSITION_LEVERAGE', 1.0)}x (Leído de config.py)")
    print("="*40 + "\n")

    confirm_menu = TerminalMenu(
        ["[1] Iniciar Bot con esta Configuración", "[2] Cancelar y Salir"],
        title="¿Es correcta esta configuración?",
        **MENU_STYLE
    )
    choice_index = confirm_menu.show()

    return choice_index == 0

# --- Función Pública Principal ---

def run_trading_assistant_wizard() -> Optional[Tuple[float, int]]:
    """
    Ejecuta el asistente de configuración completo, paso a paso.

    Returns:
        Optional[Tuple[float, int]]: Una tupla con (base_size, slots) si el usuario
                                     confirma, o None si cancela.
    """
    if not TerminalMenu or not config:
        print("ERROR: Dependencias 'simple-term-menu' o 'config' no disponibles.")
        return None, None

    clear_screen()
    print_tui_header("Asistente de Configuración - Modo Live Interactivo")
    print("\n¡Bienvenido! Este asistente te guiará para configurar tu sesión de trading.")
    press_enter_to_continue()

    # Ejecutar cada paso y recolectar la configuración
    symbol = _wizard_step_symbol()
    base_size, slots = _wizard_step_capital()
    risk_profile = _wizard_step_risk_profile()

    config_summary = {
        "symbol": symbol,
        "base_size": base_size,
        "slots": slots,
        "risk_profile": risk_profile
    }

    # Pedir confirmación final
    if _wizard_step_confirmation(config_summary):
        return base_size, slots
    else:
        clear_screen()
        print("\nInicio cancelado por el usuario.")
        time.sleep(2)
        return None, None

# =============== FIN ARCHIVO: core/menu/_wizard.py ===============