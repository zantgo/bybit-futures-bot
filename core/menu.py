# =============== INICIO ARCHIVO: core/menu.py (v8.7.x - Lógica Tamaño Base y Slots + Menú Intervención Simplificado) ===============
"""
Módulo para gestionar los menús interactivos de la aplicación.
v8.7.x: Modificado para pedir tamaño base por posición y número inicial de slots.
        Menú de intervención manual simplificado para solo ajustar slots.
v8.7: Añade funciones interactivas genéricas para modo/capital. Menú principal simplificado.
v8.2.5: Unificada vista detallada en pre-inicio.
"""

import datetime
import time # Asegurar que time está importado
from typing import List, Dict, Optional, Tuple, Any
# Importar config y utils para acceder a datos necesarios y formatear
try:
    # Intentar import relativo primero (asumiendo que menu.py está en core/)
    import config
    from core import utils
except ImportError:
    # Fallback a import directo si el relativo falla
    try:
        import config
        import utils
    except ImportError:
        print("ERROR CRITICO [menu.py]: No se pudieron importar config o utils.")
        # Crear objetos dummy mínimos para evitar errores de atributos si es posible
        config_attrs = {
            'PRICE_PRECISION': 2, 'DEFAULT_QTY_PRECISION': 3, 'PNL_PRECISION': 2,
            'TICKER_SYMBOL': 'N/A', 'POSITION_TRADING_MODE': 'LONG_SHORT',
            'POSITION_BASE_SIZE_USDT': 10.0, # Valor por defecto para la nueva lógica
            'POSITION_MAX_LOGICAL_POSITIONS': 1 # Valor por defecto para la nueva lógica
        }
        config = type('obj', (object,), config_attrs)()
        utils = type('obj', (object,), {'format_datetime': str, 'safe_float_convert': float})()


def print_header(title: str):
    """Imprime una cabecera estándar para los menús."""
    width = 70 # Ancho estándar para la cabecera
    print("\n" + "=" * width)
    print(f"{title.center(width)}")
    if utils and hasattr(utils, 'format_datetime'): # Imprimir fecha/hora si utils está disponible
        try:
            now_str = utils.format_datetime(datetime.datetime.now(), '%Y-%m-%d %H:%M:%S')
            print(f"{now_str.center(width)}")
        except Exception: pass # Ignorar si falla el formato de fecha/hora
    print("=" * width)

def get_main_menu_choice() -> str:
    """Muestra el menú principal simple."""
    print_header("Bybit Futures Bot v8.7.x - Menú Principal")
    print("Seleccione el modo de operación:\n")
    print("  1. Modo Live (Trading Real/Testnet)")
    print("  2. Modo Backtesting (Simulación con datos históricos)")
    print("-" * 70)
    print("  0. Salir")
    print("=" * 70)
    choice = input("Seleccione una opción: ").strip()
    return choice

def get_trading_mode_interactively() -> str:
    """
    Pregunta interactivamente al usuario por el modo de trading.
    Devuelve 'LONG_ONLY', 'SHORT_ONLY', 'LONG_SHORT', o 'CANCEL'.
    """
    print_header("Selección de Modo de Trading para esta Sesión")
    print("Elija cómo operará el bot durante esta ejecución:\n")
    print("  1. LONG ONLY  (Solo abrirá posiciones largas)")
    print("  2. SHORT ONLY (Solo abrirá posiciones cortas)")
    print("  3. BOTH       (Abrirá posiciones largas y cortas)")
    print("-" * 70)
    print("  0. Cancelar Inicio / Volver")
    print("=" * 70)
    while True:
        choice = input("Seleccione una opción (1, 2, 3, 0): ").strip()
        if choice == '1': return "LONG_ONLY"
        elif choice == '2': return "SHORT_ONLY"
        elif choice == '3': return "LONG_SHORT"
        elif choice == '0': return "CANCEL"
        else: print("Opción inválida. Por favor, ingrese 1, 2, 3 o 0."); time.sleep(1)

# <<< MODIFICADA: get_instance_capital_interactively AHORA ES get_position_setup_interactively >>>
def get_position_setup_interactively() -> Tuple[Optional[float], Optional[int]]:
    """
    Pregunta interactivamente por el tamaño base por posición y el número inicial de slots.
    Devuelve una tupla (base_size_usdt, initial_slots) o (None, None) si se cancela.
    """
    print_header("Configuración de Posiciones para esta Sesión")
    base_size_usdt: Optional[float] = None
    initial_slots: Optional[int] = None

    default_base_size_str = "N/A"
    if hasattr(config, 'POSITION_BASE_SIZE_USDT'):
        default_base_size_str = f"{float(getattr(config, 'POSITION_BASE_SIZE_USDT')):.2f}"

    default_slots_str = "N/A"
    if hasattr(config, 'POSITION_MAX_LOGICAL_POSITIONS'):
        default_slots_str = str(int(getattr(config, 'POSITION_MAX_LOGICAL_POSITIONS')))

    # 1. Pedir Tamaño Base por Posición
    print("Ingrese el tamaño base de margen (en USDT) que se asignará a CADA posición lógica individual.")
    print("Este será el margen inicial para cada operación (antes de la reinversión de PNL si está activa).")
    print("(Ingrese 0 para cancelar la configuración).")
    print("-" * 70)
    while True:
        size_str = input(f"Tamaño base por posición USDT (ej: 10, 25.5) [Default Config: {default_base_size_str}]: ").strip()
        if not size_str and default_base_size_str != "N/A":
            try:
                base_size_usdt = float(default_base_size_str)
                print(f"  Usando tamaño base por defecto de config: {base_size_usdt:.4f} USDT")
                break
            except ValueError:
                print("Error con el valor por defecto de config. Por favor, ingrese un valor.")
        if not size_str:
            print("Por favor, ingrese un valor.")
            continue
        try:
            value = float(size_str)
            if value == 0:
                print("Configuración de posiciones cancelada.")
                return None, None
            elif value > 0:
                base_size_usdt = value
                print(f"  Tamaño base por posición asignado: {base_size_usdt:.4f} USDT")
                break
            else:
                print("El tamaño base debe ser un número positivo mayor que cero.")
        except ValueError:
            print(f"Error: '{size_str}' no es un número válido. Intente de nuevo.")
        except Exception as e:
            print(f"Error inesperado validando tamaño base: {e}")
        time.sleep(0.5)

    # 2. Pedir Número Inicial de Slots (Posiciones Lógicas Máximas)
    print("\n" + "-" * 70)
    print("Ingrese el número INICIAL de posiciones lógicas (slots) que el bot podrá abrir POR LADO.")
    print("Este valor podrá ser ajustado dinámicamente durante la ejecución si el modo interactivo está activo.")
    print("(Ingrese 0 para cancelar la configuración).")
    print("-" * 70)
    while True:
        slots_str = input(f"Número inicial de slots por lado (ej: 1, 3, 5) [Default Config: {default_slots_str}]: ").strip()
        if not slots_str and default_slots_str != "N/A":
            try:
                initial_slots = int(default_slots_str)
                if initial_slots < 1: # Asegurar que el default de config sea al menos 1
                    print(f"  Valor por defecto de config ({initial_slots}) es menor que 1. Usando 1.")
                    initial_slots = 1
                print(f"  Usando número inicial de slots por defecto de config: {initial_slots}")
                break
            except ValueError:
                 print("Error con el valor por defecto de config para slots. Por favor, ingrese un valor.")
        if not slots_str:
            print("Por favor, ingrese un valor.")
            continue
        try:
            value = int(slots_str)
            if value == 0:
                print("Configuración de posiciones cancelada.")
                return None, None
            elif value >= 1:
                initial_slots = value
                print(f"  Número inicial de slots asignado: {initial_slots} por lado.")
                break
            else:
                print("El número de slots debe ser un entero positivo (mínimo 1).")
        except ValueError:
            print(f"Error: '{slots_str}' no es un número entero válido. Intente de nuevo.")
        except Exception as e:
            print(f"Error inesperado validando número de slots: {e}")
        time.sleep(0.5)

    return base_size_usdt, initial_slots


# --- Funciones de Menú Live (sin cambios funcionales, se mantienen como estaban) ---
def display_live_pre_start_overview(account_states: Dict[str, Dict], symbol: Optional[str]):
    print_header(f"Bybit Futures Bot v8.7.x - Resumen Estado Real Pre-Inicio")
    if not account_states:
        print("No se pudo obtener información del estado real de las cuentas."); print("-" * 70); input("Enter..."); return
    total_physical_positions = 0; symbol_base = symbol.replace('USDT', '') if symbol else '???'
    price_prec = getattr(config, 'PRICE_PRECISION', 2); qty_prec = getattr(config, 'DEFAULT_QTY_PRECISION', 3); pnl_prec = getattr(config, 'PNL_PRECISION', 2)
    print("Estado actual DETALLADO de las cuentas conectadas (API Bybit):\n")
    order = ['main', 'longs', 'shorts', 'profit']; sorted_account_names = sorted(account_states.keys(), key=lambda x: order.index(x) if x in order else len(order))
    for acc_name in sorted_account_names:
        state = account_states.get(acc_name, {}); unified_balance = state.get('unified_balance'); funding_balance = state.get('funding_balance'); positions = state.get('positions', [])
        print(f"--- Cuenta: {acc_name} ---"); print("--- Balance Cuenta Unificada (UTA) ---")
        if unified_balance:
            total_equity_str = f"{utils.safe_float_convert(unified_balance.get('totalEquity'), 0.0):,.{price_prec}f}" if utils else "N/A"
            avail_balance_str = f"{utils.safe_float_convert(unified_balance.get('totalAvailableBalance'), 0.0):,.{price_prec}f}" if utils else "N/A"
            wallet_balance_str = f"{utils.safe_float_convert(unified_balance.get('totalWalletBalance'), 0.0):,.{price_prec}f}" if utils else "N/A"
            usdt_balance_str = f"{utils.safe_float_convert(unified_balance.get('usdt_balance'), 0.0):,.4f}" if utils else "N/A"
            usdt_available_str = f"{utils.safe_float_convert(unified_balance.get('usdt_available'), 0.0):,.4f}" if utils else "N/A"
            print(f"  Equidad Total (USD)       : {total_equity_str:>18}"); print(f"  Balance Disponible (USD)  : {avail_balance_str:>18}")
            print(f"  Balance Wallet Total (USD): {wallet_balance_str:>18}"); print(f"  USDT en Wallet            : {usdt_balance_str:>18}")
            print(f"  USDT Disponible           : {usdt_available_str:>18}")
        else: print("  (No se pudo obtener información de balance unificado)")
        print("\n--- Balance Cuenta de Fondos ---")
        if funding_balance is not None:
            if funding_balance:
                 print("  {:<10} {:<18}".format("Moneda", "Balance Wallet")); print("  {:<10} {:<18}".format("--------", "------------------")); found_assets = False
                 for coin, data in sorted(funding_balance.items()):
                     wallet_bal = utils.safe_float_convert(data.get('walletBalance'), 0.0) if utils else 0.0
                     if wallet_bal > 1e-9: print("  {:<10} {:<18.8f}".format(coin, wallet_bal)); found_assets = True
                 if not found_assets: print("  (No se encontraron activos con balance significativo)")
            else: print("  (Cuenta de fondos vacía)")
        else: print("  (No se pudo obtener información de balance de fondos)")
        print(f"\n--- Posiciones Abiertas ({symbol} en esta cuenta) ---"); long_pos = None; short_pos = None; current_account_physical_positions = 0
        if positions:
            for pos in positions:
                total_physical_positions += 1; current_account_physical_positions += 1
                if pos.get('positionIdx') == 1: long_pos = pos
                elif pos.get('positionIdx') == 2: short_pos = pos
        print("\n  --- LONG (PosIdx=1) ---")
        if long_pos:
            size = utils.safe_float_convert(long_pos.get('size'), 0.0); entry = utils.safe_float_convert(long_pos.get('avgPrice'), 0.0)
            pnl = utils.safe_float_convert(long_pos.get('unrealisedPnl'), 0.0); mark = utils.safe_float_convert(long_pos.get('markPrice'), 0.0)
            liq = utils.safe_float_convert(long_pos.get('liqPrice'), 0.0); margin = utils.safe_float_convert(long_pos.get('positionIM', long_pos.get('positionMM', 0.0)), 0.0)
            print(f"  Tamaño          : {size:.{qty_prec}f} {symbol_base}"); print(f"  Entrada Prom.   : {entry:.{price_prec}f} USDT")
            print(f"  Margen Usado    : {margin:.{pnl_prec}f} USDT"); print(f"  P/L No Realizado: {pnl:+,.{pnl_prec}f} USDT (Marca: {mark:.{price_prec}f})")
            print(f"  Liq. Estimada   : {liq:.{price_prec}f} USDT")
        else: print("  (No hay posición LONG abierta)")
        print("\n  --- SHORT (PosIdx=2) ---")
        if short_pos:
            size = utils.safe_float_convert(short_pos.get('size'), 0.0); entry = utils.safe_float_convert(short_pos.get('avgPrice'), 0.0)
            pnl = utils.safe_float_convert(short_pos.get('unrealisedPnl'), 0.0); mark = utils.safe_float_convert(short_pos.get('markPrice'), 0.0)
            liq = utils.safe_float_convert(short_pos.get('liqPrice'), 0.0); margin = utils.safe_float_convert(short_pos.get('positionIM', short_pos.get('positionMM', 0.0)), 0.0)
            print(f"  Tamaño          : {size:.{qty_prec}f} {symbol_base}"); print(f"  Entrada Prom.   : {entry:.{price_prec}f} USDT")
            print(f"  Margen Usado    : {margin:.{pnl_prec}f} USDT"); print(f"  P/L No Realizado: {pnl:+,.{pnl_prec}f} USDT (Marca: {mark:.{price_prec}f})")
            print(f"  Liq. Estimada   : {liq:.{price_prec}f} USDT")
        else: print("  (No hay posición SHORT abierta)")
        if current_account_physical_positions == 0: print(f"\n  (Ninguna posición física activa para {symbol} en cuenta)")
        print("\n" + "-" * 70)
    print(f"Total Posiciones FÍSICAS Abiertas ({symbol}, todas cuentas): {total_physical_positions}")
    if total_physical_positions > 0: print("\nADVERTENCIA: Posiciones abiertas detectadas. Cierra manualmente ANTES de iniciar.");
    else: print("No se detectaron posiciones FÍSICAS abiertas para este símbolo.")
    print("-" * 70); input("Presione Enter para continuar al menú principal live...")

def get_live_main_menu_choice() -> str:
    print_header("Bybit Futures Bot v8.7.x - Modo Live - Principal")
    print("Seleccione una acción:\n"); print("  1. Ver/Gestionar Estado DETALLADO de Cuentas Individuales")
    print("  2. Iniciar el Bot (Trading Automático)"); print("  3. Probar Ciclo Completo (Apertura/Cierre) LONG & SHORT")
    print("  4. Ver Tabla de Posiciones Lógicas Actuales"); print("-" * 70)
    print("  0. Salir del Modo Live"); print("=" * 70)
    return input("Seleccione una opción: ").strip()

def get_account_selection_menu_choice(accounts: List[str]) -> Tuple[Optional[str], Optional[str]]:
    print_header("Bybit Futures Bot v8.7.x - Live - Selección de Cuenta Detallada")
    if not accounts: print("No hay cuentas API inicializadas."); print("-" * 70); print("  0. Volver"); print("=" * 70); input("Enter..."); return '0', None
    print("Seleccione la cuenta a inspeccionar/gestionar:\n"); account_map = {}
    order = ['main', 'longs', 'shorts', 'profit']; sorted_accounts = sorted(accounts, key=lambda x: order.index(x) if x in order else len(order))
    for i, acc_name in enumerate(sorted_accounts): option_num = str(i + 1); print(f"  {option_num}. {acc_name}"); account_map[option_num] = acc_name
    print("-" * 70); print("  0. Volver al Menú Live Principal"); print("=" * 70)
    choice = input("Seleccione una opción: ").strip()
    if choice == '0': return '0', None
    elif choice in account_map: return choice, account_map[choice]
    else: print("Opción inválida."); time.sleep(1); return None, None

def display_account_management_status(account_name: str, unified_balance: Optional[dict], funding_balance: Optional[dict], positions: Optional[List[dict]]):
    print_header(f"Bybit Futures Bot v8.7.x - Live - Gestión Cuenta: {account_name}")
    print("--- Balance Cuenta Unificada (UTA) ---")
    if unified_balance:
        price_prec = getattr(config, 'PRICE_PRECISION', 2); total_equity_str = f"{utils.safe_float_convert(unified_balance.get('totalEquity'), 0.0):,.{price_prec}f}"
        avail_balance_str = f"{utils.safe_float_convert(unified_balance.get('totalAvailableBalance'), 0.0):,.{price_prec}f}"; wallet_balance_str = f"{utils.safe_float_convert(unified_balance.get('totalWalletBalance'), 0.0):,.{price_prec}f}"
        usdt_balance_str = f"{utils.safe_float_convert(unified_balance.get('usdt_balance'), 0.0):,.4f}"; usdt_available_str = f"{utils.safe_float_convert(unified_balance.get('usdt_available'), 0.0):,.4f}"
        print(f"  Equidad Total (USD)       : {total_equity_str:>18}"); print(f"  Balance Disponible (USD)  : {avail_balance_str:>18}")
        print(f"  Balance Wallet Total (USD): {wallet_balance_str:>18}"); print(f"  USDT en Wallet            : {usdt_balance_str:>18}")
        print(f"  USDT Disponible           : {usdt_available_str:>18}")
    else: print("  (No se pudo obtener info balance unificado)")
    print("\n--- Balance Cuenta de Fondos ---")
    if funding_balance is not None:
        if funding_balance:
             print("  {:<10} {:<18}".format("Moneda", "Balance Wallet")); print("  {:<10} {:<18}".format("--------", "------------------")); found_assets = False
             for coin, data in sorted(funding_balance.items()):
                 wallet_bal = utils.safe_float_convert(data.get('walletBalance'), 0.0)
                 if wallet_bal > 1e-9: print("  {:<10} {:<18.8f}".format(coin, wallet_bal)); found_assets = True
             if not found_assets: print("  (No activos con balance significativo)")
        else: print("  (Cuenta de fondos vacía)")
    else: print("  (No se pudo obtener info balance fondos)")
    symbol = getattr(config, 'TICKER_SYMBOL', 'N/A'); print(f"\n--- Posiciones Abiertas ({symbol} en cuenta) ---")
    long_pos = None; short_pos = None
    if positions:
        for pos in positions:
            size_val = utils.safe_float_convert(pos.get('size'), 0.0)
            if size_val > 1e-12:
                if pos.get('positionIdx') == 1: long_pos = pos
                elif pos.get('positionIdx') == 2: short_pos = pos
    qty_prec = getattr(config, 'DEFAULT_QTY_PRECISION', 3); price_prec = getattr(config, 'PRICE_PRECISION', 2)
    pnl_prec = getattr(config, 'PNL_PRECISION', 2); symbol_base = symbol.replace('USDT', '') if symbol != 'N/A' else '???'
    print("\n  --- LONG (PosIdx=1) ---")
    if long_pos:
        size = utils.safe_float_convert(long_pos.get('size'), 0.0); entry = utils.safe_float_convert(long_pos.get('avgPrice'), 0.0)
        pnl = utils.safe_float_convert(long_pos.get('unrealisedPnl'), 0.0); mark = utils.safe_float_convert(long_pos.get('markPrice'), 0.0)
        liq = utils.safe_float_convert(long_pos.get('liqPrice'), 0.0); margin = utils.safe_float_convert(long_pos.get('positionIM', long_pos.get('positionMM', 0.0)), 0.0)
        print(f"  Tamaño          : {size:.{qty_prec}f} {symbol_base}"); print(f"  Entrada Prom.   : {entry:.{price_prec}f} USDT")
        print(f"  Margen Usado    : {margin:.{pnl_prec}f} USDT"); print(f"  P/L No Realizado: {pnl:+,.{pnl_prec}f} USDT (Marca: {mark:.{price_prec}f})")
        print(f"  Liq. Estimada   : {liq:.{price_prec}f} USDT")
    else: print("  (No hay posición LONG abierta)")
    print("\n  --- SHORT (PosIdx=2) ---")
    if short_pos:
        size = utils.safe_float_convert(short_pos.get('size'), 0.0); entry = utils.safe_float_convert(short_pos.get('avgPrice'), 0.0)
        pnl = utils.safe_float_convert(short_pos.get('unrealisedPnl'), 0.0); mark = utils.safe_float_convert(short_pos.get('markPrice'), 0.0)
        liq = utils.safe_float_convert(short_pos.get('liqPrice'), 0.0); margin = utils.safe_float_convert(short_pos.get('positionIM', short_pos.get('positionMM', 0.0)), 0.0)
        print(f"  Tamaño          : {size:.{qty_prec}f} {symbol_base}"); print(f"  Entrada Prom.   : {entry:.{price_prec}f} USDT")
        print(f"  Margen Usado    : {margin:.{pnl_prec}f} USDT"); print(f"  P/L No Realizado: {pnl:+,.{pnl_prec}f} USDT (Marca: {mark:.{price_prec}f})")
        print(f"  Liq. Estimada   : {liq:.{price_prec}f} USDT")
    else: print("  (No hay posición SHORT abierta)")
    print("\n" + "-" * 70)

def get_account_management_menu_choice(account_name: str, has_long: bool, has_short: bool) -> str:
    symbol = getattr(config, 'TICKER_SYMBOL', '???')
    print(f"Acciones para Cuenta '{account_name}' y Símbolo '{symbol}':\n"); print(f"  1. Refrescar Información")
    print(f"  2. Cerrar TODAS las posiciones ({'Activas' if has_long or has_short else 'Ninguna'})")
    print(f"  3. Cerrar posición LONG {'(Activa)' if has_long else '(Inexistente)'}")
    print(f"  4. Cerrar posición SHORT {'(Activa)' if has_short else '(Inexistente)'}")
    print("-" * 70); print("  0. Volver a Selección de Cuenta"); print("=" * 70)
    return input("Seleccione una opción: ").strip()

def get_backtest_trading_mode_choice() -> str: # Para Backtest, se mantiene igual
    print_header("Backtest - Selección de Modo de Trading")
    print("Seleccione el modo de trading a simular:\n"); print("  1. LONG ONLY"); print("  2. SHORT ONLY"); print("  3. LONG & SHORT")
    print("-" * 70); print("  0. Cancelar Backtest"); print("=" * 70)
    while True:
        choice = input("Seleccione una opción: ").strip()
        if choice == '1': return "LONG_ONLY"
        elif choice == '2': return "SHORT_ONLY"
        elif choice == '3': return "LONG_SHORT"
        elif choice == '0': return "CANCEL"
        else: print("Opción no válida."); time.sleep(1)

def get_post_backtest_menu_choice() -> str:
    print_header("Bybit Futures Bot v8.7.x - Backtest Finalizado")
    print("Opciones disponibles:\n"); print("  1. Ver Reporte de Resultados"); print("  2. Ver Gráfico"); print("-" * 70); print("  0. Salir"); print("=" * 70)
    return input("Seleccione una opción: ").strip()

# --- FUNCIÓN DE MENÚ DE INTERVENCIÓN MANUAL (SIMPLIFICADA) ---
def get_live_manual_intervention_menu(
    current_max_logical_positions: int,
    base_position_size_usdt: Optional[float] = None, # Para mostrar info al usuario
    # Podríamos añadir aquí el capital disponible actual por lado para que el menú de advertencia sea más preciso
    available_long_margin: Optional[float] = None,
    available_short_margin: Optional[float] = None
) -> str:
    """
    Muestra el menú de intervención manual simplificado (solo ajustar slots).
    Devuelve una acción ("ADDSLOT", "REMOVESLOT", "0").
    """
    print_header("Menú de Intervención Manual - Ajustar Slots")
    print("Seleccione una acción:\n")
    print(f"  1. Aumentar Slots Máximos de Posiciones Lógicas (Actual: {current_max_logical_positions})")
    if base_position_size_usdt is not None:
        # Estimación simple del capital adicional por slot (sin considerar apalancamiento aquí, solo margen base)
        print(f"     (Tamaño base por posición: {base_position_size_usdt:.2f} USDT)")
        # La advertencia más detallada sobre el capital total se hará en live_runner
        # antes de confirmar la acción.
    print(f"  2. Disminuir Slots Máximos de Posiciones Lógicas (Actual: {current_max_logical_positions})")
    print("-" * 70)
    print("  0. Volver (Continuar Operación Automática del Bot)")
    print("=" * 70)

    while True:
        choice = input("Seleccione una opción (0, 1, 2): ").strip()
        if choice == '1':
            return "ADDSLOT"
        elif choice == '2':
            return "REMOVESLOT"
        elif choice == '0':
            return "0" # Mantener el 0 para volver
        else:
            print("Opción inválida. Por favor, ingrese 0, 1 o 2.")
            time.sleep(1)


# --- Funciones de Menú Anteriores (Legado, comentadas o eliminadas si no se usan) ---
# La función original `get_live_manual_position_menu_choice` que incluía abrir/cerrar
# y `get_manual_position_side_choice` se eliminan/comentan si ya no se usan
# por la simplificación del menú de intervención.

def display_live_pre_start_status_legacy(api_status: Dict[str, Any], positions: Optional[List[Dict]]):
    print("-" * 70); print(f"Conexión API     : {'OK' if api_status.get('connection_ok', False) else 'ERROR'}")
    if api_status.get('accounts'): print(f"Cuentas Activas  : {', '.join(api_status.get('accounts', []))}")
    symbol = api_status.get('symbol', 'N/A'); print(f"Símbolo          : {symbol}")
    print(f"Modo Posición    : {api_status.get('position_mode', 'Desconocido')}"); print(f"Apalancamiento   : {api_status.get('leverage', 'N/A')}x (Cuenta: {api_status.get('leverage_account', 'N/A')})")
    print("-" * 70); print(f"Posiciones Físicas Abiertas ({symbol}):")
    long_pos, short_pos = None, None
    if positions:
        for pos in positions:
             size_val = utils.safe_float_convert(pos.get('size'), 0.0) if utils else 0.0
             if size_val > 1e-12:
                 if pos.get('positionIdx') == 1: long_pos = pos
                 elif pos.get('positionIdx') == 2: short_pos = pos
    qty_prec = getattr(config, 'DEFAULT_QTY_PRECISION', 3); price_prec = getattr(config, 'PRICE_PRECISION', 2); pnl_prec = getattr(config, 'PNL_PRECISION', 2)
    symbol_base = symbol.replace('USDT', '') if symbol != 'N/A' else '???'
    print("\n  --- LONG (PosIdx=1) ---")
    if long_pos:
        size = utils.safe_float_convert(long_pos.get('size'), 0.0); entry = utils.safe_float_convert(long_pos.get('avgPrice'), 0.0)
        pnl = utils.safe_float_convert(long_pos.get('unrealisedPnl'), 0.0); mark = utils.safe_float_convert(long_pos.get('markPrice'), 0.0)
        liq = utils.safe_float_convert(long_pos.get('liqPrice'), 0.0);
        print(f"  Tamaño          : {size:.{qty_prec}f} {symbol_base}"); print(f"  Entrada Prom.   : {entry:.{price_prec}f} USDT")
        print(f"  P/L No Realizado: {pnl:+,.{pnl_prec}f} USDT (Marca: {mark:.{price_prec}f})"); print(f"  Liq. Estimada   : {liq:.{price_prec}f} USDT")
    else: print("  (No hay posición LONG abierta)")
    print("\n  --- SHORT (PosIdx=2) ---")
    if short_pos:
        size = utils.safe_float_convert(short_pos.get('size'), 0.0); entry = utils.safe_float_convert(short_pos.get('avgPrice'), 0.0)
        pnl = utils.safe_float_convert(short_pos.get('unrealisedPnl'), 0.0); mark = utils.safe_float_convert(short_pos.get('markPrice'), 0.0)
        liq = utils.safe_float_convert(short_pos.get('liqPrice'), 0.0);
        print(f"  Tamaño          : {size:.{qty_prec}f} {symbol_base}"); print(f"  Entrada Prom.   : {entry:.{price_prec}f} USDT")
        print(f"  P/L No Realizado: {pnl:+,.{pnl_prec}f} USDT (Marca: {mark:.{price_prec}f})"); print(f"  Liq. Estimada   : {liq:.{price_prec}f} USDT")
    else: print("  (No hay posición SHORT abierta)")
    print("\n" + "-" * 70)

def get_live_pre_start_menu_choice_legacy(has_long: bool, has_short: bool) -> str:
    print("Seleccione una acción:\n"); print(f"  1. Refrescar Estado / Ver Detalles Posiciones")
    print(f"  2. Cerrar TODAS las posiciones ({'Activas' if has_long or has_short else 'Ninguna'})")
    print(f"  3. Cerrar posición LONG {'(Activa)' if has_long else '(Inexistente)'}")
    print(f"  4. Cerrar posición SHORT {'(Activa)' if has_short else '(Inexistente)'}"); print("-" * 70)
    print(f"  5. Iniciar el Bot (Trading Automático)"); print("-" * 70); print("  0. Volver / Salir"); print("=" * 70)
    return input("Seleccione una opción: ").strip()

# =============== FIN ARCHIVO: core/menu.py (v8.7.x - Lógica Tamaño Base y Slots + Menú Intervención Simplificado) ===============