# =============== INICIO ARCHIVO: core/menu.py (v13.1 - Con Backtest Automático) ===============
"""
Módulo para gestionar los menús interactivos de la aplicación.

v13.1:
- Añadida la opción "Modo Automático (Backtest)" al menú principal.
v13:
- Añade la opción "Modo Automático" al menú principal.
- Introduce `get_automatic_mode_intervention_menu`.
"""
import datetime
import time
import os
import numpy as np
from typing import List, Dict, Optional, Tuple, Any

# Importar config y utils para acceder a datos necesarios y formatear
try:
    import config
    from core import utils
except ImportError:
    print("ERROR CRITICO [menu.py]: No se pudieron importar config o utils.")
    config = type('obj', (object,), {})()
    utils = type('obj', (object,), {})()


def print_header(title: str, width: int = 80):
    """Imprime una cabecera estándar para los menús con ancho personalizable."""
    print("\n" + "=" * width)
    print(f"{title.center(width)}")
    if utils and hasattr(utils, 'format_datetime'):
        try:
            now_str = utils.format_datetime(datetime.datetime.now(), '%Y-%m-%d %H:%M:%S')
            print(f"{now_str.center(width)}")
        except Exception: pass
    print("=" * width)

# --- MENÚS PRINCIPALES Y DE CONFIGURACIÓN ---

def get_main_menu_choice() -> str:
    """Muestra el menú principal, ahora con la opción de Modo Automático."""
    print_header("Bybit Futures Bot v13.1 - Menú Principal")
    print("Seleccione el modo de operación:\n")
    print("  1. Modo Live Interactivo (Control Manual y Estrategia Bajo Nivel)")
    print("  2. Modo Backtesting (Simulación con Estrategia de Bajo Nivel)")
    print("  3. Modo Automático (Live, Dirigido por Estrategia de Alto Nivel)")
    print("  4. Modo Automático (Backtest, Simulación de Estrategia de Alto Nivel)")
    print("-" * 80)
    print("  0. Salir")
    print("=" * 80)
    choice = input("Seleccione una opción: ").strip()
    return choice

# (El resto del archivo no necesita cambios)

def get_trading_mode_interactively() -> str:
    """Pregunta por el modo de trading (para modo Live Interactivo y Backtest)."""
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
        if choice in ['1', '2', '3', '0']:
            return {"1": "LONG_ONLY", "2": "SHORT_ONLY", "3": "LONG_SHORT", "0": "CANCEL"}[choice]
        else:
            print("Opción inválida. Por favor, ingrese 1, 2, 3 o 0."); time.sleep(1)

def get_position_setup_interactively() -> Tuple[Optional[float], Optional[int]]:
    """Pregunta por el tamaño base por posición y el número inicial de slots."""
    print_header("Configuración de Posiciones para esta Sesión")
    base_size_usdt: Optional[float] = None
    initial_slots: Optional[int] = None
    default_base_size_str = f"{float(getattr(config, 'POSITION_BASE_SIZE_USDT', 10.0)):.2f}"
    default_slots_str = str(int(getattr(config, 'POSITION_MAX_LOGICAL_POSITIONS', 1)))

    print("Ingrese el tamaño base de margen (en USDT) que se asignará a CADA posición lógica individual.")
    print("(Ingrese 0 para cancelar la configuración).")
    print("-" * 70)
    while base_size_usdt is None:
        size_str = input(f"Tamaño base por posición USDT [Default: {default_base_size_str}]: ").strip()
        if not size_str: size_str = default_base_size_str
        try:
            value = float(size_str)
            if value == 0: return None, None
            if value > 0: base_size_usdt = value; break
            else: print("El tamaño base debe ser positivo.")
        except ValueError: print(f"'{size_str}' no es un número válido.")
    
    print("\n" + "-" * 70)
    print("Ingrese el número INICIAL de posiciones lógicas (slots) que el bot podrá abrir POR LADO.")
    print("(Ingrese 0 para cancelar la configuración).")
    print("-" * 70)
    while initial_slots is None:
        slots_str = input(f"Número inicial de slots por lado [Default: {default_slots_str}]: ").strip()
        if not slots_str: slots_str = default_slots_str
        try:
            value = int(slots_str)
            if value == 0: return None, None
            if value >= 1: initial_slots = value; break
            else: print("El número de slots debe ser mínimo 1.")
        except ValueError: print(f"'{slots_str}' no es un número entero válido.")

    return base_size_usdt, initial_slots

def get_automatic_mode_intervention_menu(
    pm_summary: Dict[str, Any],
    tick_visualization_status: Dict[str, bool]
) -> str:
    os.system('cls' if os.name == 'nt' else 'clear')
    width = 80
    print_header("BOT EN VIVO - MENÚ DE INTERVENCIÓN MANUAL", width)
    
    bot_state = pm_summary.get('bot_state', 'Desconocido')
    trading_mode = pm_summary.get('trading_mode', 'N/A')
    slots = pm_summary.get('max_logical_positions', 0)
    base_size = pm_summary.get('initial_base_position_size_usdt', 0.0)
    
    print(" [ Panel de Estado ]".center(width, "-"))
    print(f"| Estado General: {str(bot_state):<18} | Modo Trading Actual: {str(trading_mode):<18} |".center(width))
    print(f"| Slots Máx/Lado: {str(slots):<18} | Tamaño Base/Pos: {base_size:<15.2f} USDT |".center(width))
    print("-" * width)
    
    print("\n [ Opciones de Control ]".center(width))
    vis_low_level = "ACTIVA" if tick_visualization_status.get('low_level', False) else "INACTIVA"
    vis_ut_bot = "ACTIVA" if tick_visualization_status.get('ut_bot', False) else "INACTIVA"
    
    print(f"  [1] Ver Estadísticas en Vivo")
    print(f"  [2] Cambiar Vis. Ticks (Bajo Nivel)  (Actual: {vis_low_level})")
    print(f"  [3] Cambiar Vis. Ticks (UT Bot)      (Actual: {vis_ut_bot})")
    print("-" * width)
    print(f"  [4] Aumentar Slots Máximos (+1)")
    print(f"  [5] Disminuir Slots Máximos (-1)")
    print(f"  [6] Cambiar Tamaño Base por Posición")
    print("-" * width)
    print(f"  [0] Volver (Continuar Operación del Bot)")
    print("=" * width)
    
    choice = input("Seleccione una opción: ").strip()
    return choice

def display_live_stats(pm_summary: Dict[str, Any]):
    os.system('cls' if os.name == 'nt' else 'clear')
    width = 80
    print_header("Estadísticas en Vivo", width)

    if not pm_summary or 'error' in pm_summary:
        print("No se pudo obtener el resumen de estado.".center(width))
        input("\nPresione Enter para volver...".center(width))
        return

    longs_count = pm_summary.get('open_long_positions_count', 0)
    shorts_count = pm_summary.get('open_short_positions_count', 0)
    pnl_long = pm_summary.get('total_realized_pnl_long', 0.0)
    pnl_short = pm_summary.get('total_realized_pnl_short', 0.0)
    total_pnl = pnl_long + pnl_short
    profit_balance = pm_summary.get('bm_profit_balance', 0.0)
    initial_capital = pm_summary.get('initial_total_capital', 0.0)
    
    equity_final = initial_capital + total_pnl
    roi = utils.safe_division(total_pnl, initial_capital, 0.0) * 100

    print(" [ Rendimiento General ] ".center(width, "-"))
    print(f"  PNL Neto Total Realizado: {total_pnl:+.4f} USDT")
    print(f"  Capital Inicial Total:    {initial_capital:.2f} USDT")
    print(f"  Equity Lógico Actual:     {equity_final:.2f} USDT")
    print(f"  Retorno sobre Capital:    {roi:+.2f}%")
    print(f"  Balance en Cuenta Profit: {profit_balance:.2f} USDT")
    print("-" * width)
    print(" [ Estado Posiciones Actuales ] ".center(width, "-"))
    print(f"  Posiciones LONG abiertas:  {longs_count}")
    print(f"  Posiciones SHORT abiertas: {shorts_count}")
    print("-" * width)
    
    input("\nPresione Enter para volver al menú de intervención...")

def display_live_pre_start_overview(account_states: Dict[str, Dict], symbol: Optional[str]):
    print_header(f"Resumen Estado Real Pre-Inicio")
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
            liq = utils.safe_float_convert(short_pos.get('liqPrice'), 0.0); margin = utils.safe_float_convert(long_pos.get('positionIM', long_pos.get('positionMM', 0.0)), 0.0)
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
    print_header("Modo Live Interactivo - Menú Principal")
    print("Seleccione una acción:\n")
    print("  1. Ver/Gestionar Estado DETALLADO de Cuentas Individuales")
    print("  2. Iniciar el Bot (Trading con Estrategia de Bajo Nivel)")
    print("  3. Probar Ciclo Completo (Apertura/Cierre) LONG & SHORT")
    print("  4. Ver Tabla de Posiciones Lógicas Actuales")
    print("-" * 70)
    print("  0. Salir del Modo Live")
    print("=" * 70)
    return input("Seleccione una opción: ").strip()

def get_account_selection_menu_choice(accounts: List[str]) -> Tuple[Optional[str], Optional[str]]:
    print_header("Live - Selección de Cuenta Detallada")
    if not accounts:
        print("No hay cuentas API inicializadas."); print("-" * 70); print("  0. Volver"); print("=" * 70); input("Enter..."); return '0', None
    print("Seleccione la cuenta a inspeccionar/gestionar:\n")
    account_map = {}
    order = ['main', 'longs', 'shorts', 'profit']
    sorted_accounts = sorted(accounts, key=lambda x: order.index(x) if x in order else len(order))
    for i, acc_name in enumerate(sorted_accounts):
        option_num = str(i + 1); print(f"  {option_num}. {acc_name}"); account_map[option_num] = acc_name
    print("-" * 70); print("  0. Volver al Menú Live Principal"); print("=" * 70)
    choice = input("Seleccione una opción: ").strip()
    if choice == '0': return '0', None
    elif choice in account_map: return choice, account_map[choice]
    else: print("Opción inválida."); time.sleep(1); return None, None

def display_account_management_status(account_name: str, unified_balance: Optional[dict], funding_balance: Optional[dict], positions: Optional[List[dict]]):
    print_header(f"Live - Gestión Cuenta: {account_name}")
    # ...

def get_account_management_menu_choice(account_name: str, has_long: bool, has_short: bool) -> str:
    symbol = getattr(config, 'TICKER_SYMBOL', '???')
    print(f"Acciones para Cuenta '{account_name}' y Símbolo '{symbol}':\n")
    print(f"  1. Refrescar Información")
    print(f"  2. Cerrar TODAS las posiciones ({'Activas' if has_long or has_short else 'Ninguna'})")
    print(f"  3. Cerrar posición LONG {'(Activa)' if has_long else '(Inexistente)'}")
    print(f"  4. Cerrar posición SHORT {'(Activa)' if has_short else '(Inexistente)'}")
    print("-" * 70); print("  0. Volver a Selección de Cuenta"); print("=" * 70)
    return input("Seleccione una opción: ").strip()

def get_backtest_trading_mode_choice() -> str:
    print_header("Backtest - Selección de Modo de Trading")
    print("Seleccione el modo de trading a simular:\n")
    print("  1. LONG ONLY")
    print("  2. SHORT ONLY")
    print("  3. LONG & SHORT")
    print("-" * 70); print("  0. Cancelar Backtest"); print("=" * 70)
    while True:
        choice = input("Seleccione una opción: ").strip()
        if choice in ['1', '2', '3', '0']:
            return {"1": "LONG_ONLY", "2": "SHORT_ONLY", "3": "LONG_SHORT", "0": "CANCEL"}[choice]
        else:
            print("Opción no válida."); time.sleep(1)

def get_post_backtest_menu_choice() -> str:
    print_header("Backtest Finalizado")
    print("Opciones disponibles:\n")
    print("  1. Ver Reporte de Resultados")
    print("  2. Ver Gráfico")
    print("-" * 70); print("  0. Salir"); print("=" * 70)
    return input("Seleccione una opción: ").strip()

def get_live_manual_intervention_menu(*args, **kwargs):
    print_header("Menú de Intervención Manual (OBSOLETO)")
    print("Esta función ha sido reemplazada. Presione 0 para continuar.")
    print("-" * 70); print("  0. Volver")
    input("Seleccione una opción: ").strip()
    return "0"