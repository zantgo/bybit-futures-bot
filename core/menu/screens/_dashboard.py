"""
Módulo para la Pantalla del Dashboard de Sesión.

v8.1 (Refactor de Configuración):
- Adaptado para leer el `TICKER_SYMBOL` desde la nueva estructura de `config.py`.

v8.0 (Capital Lógico y Nuevo UI):
- La pantalla ha sido rediseñada completamente para mostrar el estado de la sesión
  y los balances lógicos de las operaciones LONG y SHORT de forma separada y clara.
- El menú de acciones ahora permite el acceso directo a la gestión de la operación
  LONG o SHORT, eliminando menús intermedios.
- Se añade una opción para refrescar la vista del dashboard en tiempo real.
- La opción "Ver/Gestionar Posiciones" se elimina del dashboard.
"""
import time
import datetime
from datetime import timezone
from typing import Dict, Any

try:
    from simple_term_menu import TerminalMenu
except ImportError:
    TerminalMenu = None

from .._helpers import (
    clear_screen,
    print_tui_header,
    press_enter_to_continue
)
from .. import _helpers as helpers_module
from . import _log_viewer, operation_manager
# --- INICIO DE LA MODIFICACIÓN --- (Mantenida desde tu código original)
# Se comenta la importación de _position_viewer ya que no se usará desde aquí.
# from . import _position_viewer
# --- FIN DE LA MODIFICACIÓN ---


try:
    # from core.exchange._models import StandardBalance # No se usa directamente aquí
    from core.strategy.sm import api as sm_api
    from core.strategy.pm import api as pm_api # Aún necesario para algunos datos como el start time
except ImportError:
    # StandardBalance = None # Comentado
    sm_api = pm_api = None


# --- Inyección de Dependencias ---
_deps: Dict[str, Any] = {}

def init(dependencies: Dict[str, Any]):
    """Recibe las dependencias inyectadas desde el controlador principal."""
    global _deps
    _deps = dependencies


def _display_final_summary(summary: Dict[str, Any]):
    """Muestra una pantalla de resumen clara al finalizar la sesión."""
    clear_screen()
    print_tui_header("Resumen Final de la Sesión")

    if not summary or summary.get('error'):
        print("\nNo se pudo generar el resumen final.")
        press_enter_to_continue()
        return

    # --- INICIO DE LA MODIFICACIÓN --- (Mantenida desde tu código original)
    # Usar los nuevos datos agregados por el SessionManager
    realized_pnl = summary.get('total_session_pnl', 0.0)
    initial_capital = summary.get('total_session_initial_capital', 0.0)
    # --- FIN DE LA MODIFICACIÓN --- (Mantenida desde tu código original)
    final_roi = (realized_pnl / initial_capital) * 100 if initial_capital > 0 else 0.0
    start_time = pm_api.get_session_start_time()
    duration_str = "N/A"
    if start_time:
        duration = datetime.datetime.now(timezone.utc) - start_time
        duration_str = str(datetime.timedelta(seconds=int(duration.total_seconds())))

    print("\n--- Rendimiento General ---")
    print(f"  PNL Realizado Total: {realized_pnl:+.4f} USDT")
    print(f"  ROI Final (Realizado): {final_roi:+.2f}%")
    print(f"  Duración Total: {duration_str}")

    open_longs = summary.get('open_long_positions', [])
    open_shorts = summary.get('open_short_positions', [])
    
    if open_longs or open_shorts:
        print("\n--- Posiciones que Quedaron Abiertas ---")
        if open_longs:
            print(f"  LONGs ({len(open_longs)}):")
            for pos in open_longs:
                print(f"    - ID: {pos.get('id', 'N/A')}, Entrada: {pos.get('entry_price', 0.0):.4f}, Tamaño: {pos.get('size_contracts', 0.0):.4f}")
        if open_shorts:
            print(f"  SHORTs ({len(open_shorts)}):")
            for pos in open_shorts:
                print(f"    - ID: {pos.get('id', 'N/A')}, Entrada: {pos.get('entry_price', 0.0):.4f}, Tamaño: {pos.get('size_contracts', 0.0):.4f}")
    else:
        print("\n--- No quedaron posiciones abiertas ---")

    press_enter_to_continue()


# --- INICIO DE LA MODIFICACIÓN: Nuevas funciones de renderizado por bloques ---

def _render_session_status_block(summary: Dict[str, Any]):
    """Imprime el bloque de Estado de Sesión."""
    print("=" * 90)
    print("-------- Estado de Sesión " + "-" * 67)
    
    session_start_time = pm_api.get_session_start_time()
    start_time_str = "N/A"
    duration_str = "00:00:00"
    if session_start_time:
        start_time_str = session_start_time.strftime('%Y-%m-%d %H:%M:%S (UTC)')
        now_utc = datetime.datetime.now(timezone.utc)
        start_time_utc = session_start_time.replace(tzinfo=timezone.utc)
        duration_seconds = (now_utc - start_time_utc).total_seconds()
        duration_str = str(datetime.timedelta(seconds=int(duration_seconds)))
    
    total_pnl = summary.get('total_session_pnl', 0.0)
    total_roi = summary.get('total_session_roi', 0.0)
    pnl_color = "\033[92m" if total_pnl >= 0 else "\033[91m"
    
    transferido_val = summary.get('total_realized_pnl_session', 0.0)

    print(f"  Inicio Sesión: {start_time_str}")
    print(f"  Duración: {duration_str}")
    print(f"  ROI Sesión: {pnl_color}{total_roi:+.2f}%{helpers_module.RESET_COLOR}")
    print(f"  PNL Total: {pnl_color}{total_pnl:+.4f} USDT{helpers_module.RESET_COLOR}")
    print(f"  Total Transferido a PROFIT  : {pnl_color}{transferido_val:+.4f} USDT{helpers_module.RESET_COLOR}")

def _render_signal_status_block(summary: Dict[str, Any], config_module: Any):
    """Imprime el bloque de Estado de Señal."""
    print("=" * 90)
    print("-------- Estado de Señal " + "-" * 68)
    
    ticker_symbol = config_module.BOT_CONFIG["TICKER"]["SYMBOL"]
    latest_signal_info = summary.get('latest_signal', {})
    
    price_str = latest_signal_info.get('price', 'N/A')
    ema_val = latest_signal_info.get('ema', 'N/A')
    w_inc_val = latest_signal_info.get('weighted_increment', 'N/A')
    w_dec_val = latest_signal_info.get('weighted_decrement', 'N/A')
    inc_pct_val = latest_signal_info.get('increment_pct', 'N/A')
    dec_pct_val = latest_signal_info.get('decrement_pct', 'N/A')
    signal_str = latest_signal_info.get('signal', 'N/A')
    signal_reason = latest_signal_info.get('signal_reason', '')

    ema_str = f"{ema_val:.4f}" if isinstance(ema_val, (int, float)) else str(ema_val)
    w_inc_str = f"{w_inc_val:.4f}" if isinstance(w_inc_val, (int, float)) else str(w_inc_val)
    w_dec_str = f"{w_dec_val:.4f}" if isinstance(w_dec_val, (int, float)) else str(w_dec_val)
    inc_pct_str = f"{inc_pct_val:.4f}" if isinstance(inc_pct_val, (int, float)) else str(inc_pct_val)
    dec_pct_str = f"{dec_pct_val:.4f}" if isinstance(dec_pct_val, (int, float)) else str(dec_pct_val)
    
    print(f"  Ticker: {ticker_symbol}")
    print(f"  Precio Actual : {price_str}")
    print("  Indicadores TA:")
    print(f"    EMA       : {ema_str:<15} W.Inc : {w_inc_str:<8} W.Dec : {w_dec_str:<8}")
    print(f"    Inc %     : {inc_pct_str:<15} Dec % : {dec_pct_str:<8}")
    print(f"  Señal Generada: {signal_str}")
    print(f"  Estado: {signal_reason}")

def _render_operations_status_block(summary: Dict[str, Any]):
    """Imprime el bloque de Estado de Operaciones en dos columnas."""
    print("=" * 90)
    print("-------- Estado de Operaciones " + "-" * 64)
    print(f"  {'LONG':<43}| {'SHORT':<43}")
    print("-" * 90)

    # Preparar datos para ambas columnas
    sides = ['long', 'short']
    data = {side: {} for side in sides}

    for side in sides:
        op_info = summary.get('operations_info', {}).get(side, {})
        balance_info = summary.get('logical_balances', {}).get(side, {})
        
        capital_inicial = op_info.get('capital_inicial_usdt', 0.0)
        pnl = summary.get(f'operation_{side}_pnl', 0.0)
        roi = (pnl / capital_inicial) * 100 if capital_inicial > 0 else 0.0
        comisiones = summary.get(f'comisiones_totales_usdt_{side}', 0.0)
        ganancias_netas = pnl - comisiones
        
        pnl_color = "\033[92m" if pnl >= 0 else "\033[91m"
        netas_color = "\033[92m" if ganancias_netas >= 0 else "\033[91m"

        capital_usado = balance_info.get('used_margin', 0.0)

        data[side] = {
            'Estado': op_info.get('estado', 'DETENIDO').upper(),
            'Posiciones': f"{summary.get(f'open_{side}_positions_count', 0)} / {op_info.get('max_posiciones_logicas', 0)}",
            'Capital': f"${capital_usado:.4f} / ${capital_inicial:.4f}",
            'Comisiones Totales': f"${comisiones:.4f}",
            'Ganancias Netas': f"{netas_color}${ganancias_netas:.4f}{helpers_module.RESET_COLOR}",
            'PNL': f"{pnl_color}{pnl:.4f}{helpers_module.RESET_COLOR}",
            'ROI': f"{pnl_color}{roi:+.2f}%{helpers_module.RESET_COLOR}",
            'Avg Ent Price': f"{summary.get(f'avg_entry_price_{side}', 'N/A')}",
            'Avg Liq Price': f"{summary.get(f'avg_liq_price_{side}', 'N/A')}",
        }

    # Imprimir las filas
    labels = [
        'Estado', 'Posiciones', 'Capital', 'Comisiones Totales',
        'Ganancias Netas', 'PNL', 'ROI', 'Avg Ent Price', 'Avg Liq Price'
    ]
    for label in labels:
        long_val = data['long'].get(label, 'N/A')
        short_val = data['short'].get(label, 'N/A')
        
        # Formateo para Avg Ent Price y Avg Liq Price si son numéricos
        if label.startswith("Avg") and isinstance(long_val, (int, float)):
            long_val = f"{long_val:.4f}"
        if label.startswith("Avg") and isinstance(short_val, (int, float)):
            short_val = f"{short_val:.4f}"
        
        print(f"  {label+':':<22} {long_val:<20}|  {label+':':<22} {short_val:<20}")

    print("=" * 90)
    print("=" * 90)

# --- FIN DE LA MODIFICACIÓN ---


def _render_dashboard_view(summary: Dict[str, Any], config_module: Any):
    """Función dedicada a imprimir el layout completo del dashboard."""
    
    # --- INICIO DE LA MODIFICACIÓN: La lógica de impresión se mueve a funciones auxiliares ---
    
    # --- CÓDIGO ANTIGUO COMENTADO, SEGÚN INSTRUCCIONES ---
    # # --- 1. Extraer datos del resumen ---
    # current_price = summary.get('current_market_price', 0.0)
    # 
    # # Datos de sesión
    # total_pnl = summary.get('total_session_pnl', 0.0)
    # total_roi = summary.get('total_session_roi', 0.0)
    # session_start_time = pm_api.get_session_start_time()
    # 
    # start_time_str = "N/A"
    # duration_str = "00:00:00"
    # if session_start_time:
    #     start_time_str = session_start_time.strftime('%Y-%m-%d %H:%M:%S (UTC)')
    #     now_utc = datetime.datetime.now(timezone.utc)
    #     start_time_utc = session_start_time.replace(tzinfo=timezone.utc)
    #     duration_seconds = (now_utc - start_time_utc).total_seconds()
    #     duration_str = str(datetime.timedelta(seconds=int(duration_seconds)))
    #     
    # # Datos de operaciones
    # op_infos = summary.get('operations_info', {})
    # long_op_info = op_infos.get('long', {})
    # short_op_info = op_infos.get('short', {})
    # long_op_status = f"LONG: {long_op_info.get('estado', 'N/A')}"
    # short_op_status = f"SHORT: {short_op_info.get('estado', 'N/A')}"
    # 
    # # Datos de señal
    # latest_signal_info = summary.get('latest_signal', {})
    # signal_str = latest_signal_info.get('signal', 'N/A')
    # signal_reason = latest_signal_info.get('signal_reason', '')
    # 
    # # Datos de posiciones
    # longs_count = summary.get('open_long_positions_count', 0)
    # shorts_count = summary.get('open_short_positions_count', 0)
    # 
    # # Datos de balances lógicos
    # logical_balances = summary.get('logical_balances', {})
    # long_balance = logical_balances.get('long', {})
    # short_balance = logical_balances.get('short', {})
    # long_pnl = summary.get('operation_long_pnl', 0.0)
    # short_pnl = summary.get('operation_short_pnl', 0.0)
    # 
    # # --- INICIO DE LA CORRECCIÓN: Recalcular margen disponible para evitar inconsistencias ---
    # long_op_margin = long_balance.get('operational_margin', 0.0)
    # long_used_margin = long_balance.get('used_margin', 0.0)
    # long_avail_margin = long_op_margin - long_used_margin
    # 
    # short_op_margin = short_balance.get('operational_margin', 0.0)
    # short_used_margin = short_balance.get('used_margin', 0.0)
    # short_avail_margin = short_op_margin - short_used_margin
    # # --- FIN DE LA CORRECCIÓN ---
    # 
    # # Cálculo de ROI por lado
    # long_capital = long_op_info.get('capital_inicial_usdt', 0.0)
    # short_capital = short_op_info.get('capital_inicial_usdt', 0.0)
    # long_roi = (long_pnl / long_capital) * 100 if long_capital > 0 else 0.0
    # short_roi = (short_pnl / short_capital) * 100 if short_capital > 0 else 0.0
    # 
    # # Extracción de precios de liquidación
    # avg_liq_l = summary.get('avg_liq_price_long', 'N/A')
    # avg_liq_s = summary.get('avg_liq_price_short', 'N/A')
    # 
    # # --- 2. Renderizar la pantalla ---
    # ticker_symbol = config_module.BOT_CONFIG["TICKER"]["SYMBOL"]
    # 
    # # Formato de cabecera mejorado
    # now_str = datetime.datetime.now(timezone.utc).strftime('%H:%M:%S %d-%m-%Y (UTC)')
    # price_str_header = f"{current_price:.4f} USDT"
    # header_title = f"Dashboard Sesión: {ticker_symbol} @ {price_str_header}"
    # sub_header = f"{now_str}"
    # 
    # # Se construye la cabecera manualmente para lograr el formato de dos líneas
    # width = 80
    # print("=" * width)
    # print(f"|{header_title.center(width - 2)}|")
    # print(f"|{sub_header.center(width - 2)}|")
    # print("=" * width)
    # 
    # print("\n--- Estado de la Sesión en Tiempo Real " + "-"*40)
    # print(f"  Inicio Sesión: {start_time_str}  |  Duración: {duration_str}")
    # pnl_color = "\033[92m" if total_pnl >= 0 else "\033[91m"
    # print(f"  PNL Total: {pnl_color}{total_pnl:+.4f} USDT\033[0m  |  ROI Sesión: {pnl_color}{total_roi:+.2f}%\033[0m")
    # 
    # print(f"\n  Operaciones: [{long_op_status}] | [{short_op_status}]")
    # print(f"  Posiciones Abiertas: LONGs: {longs_count} | SHORTs: {shorts_count}")
    # 
    # print("\n--- Balances de Operaciones Lógicas " + "-"*45)
    # header = f"  {'Operación':<15} | {'Capital Lógico':>15} | {'Usado':>15} | {'Disponible':>15} | {'Ganancias Netas':>15}"
    # print(header)
    # print("  " + "-" * (len(header) - 2))
    # 
    # pnl_long_color = "\033[92m" if long_pnl >= 0 else "\033[91m"
    # # --- INICIO DE LA CORRECCIÓN: Usar los valores recalculados ---
    # print(f"  {'LONG':<15} | {long_op_margin:15.2f} | {long_used_margin:15.2f} | {long_avail_margin:15.2f} | {pnl_long_color}{long_pnl:15.4f}\033[0m")
    # 
    # pnl_short_color = "\033[92m" if short_pnl >= 0 else "\033[91m"
    # print(f"  {'SHORT':<15} | {short_op_margin:15.2f} | {short_used_margin:15.2f} | {short_avail_margin:15.2f} | {pnl_short_color}{short_pnl:15.4f}\033[0m")
    # # --- FIN DE LA CORRECCIÓN ---
    # 
    # print("\n" + "=" * 80)
    # ts_str = latest_signal_info.get('timestamp', 'HH:MM:SS')
    # print(f"--- TICK STATUS @ {ts_str} " + "-"*53)
    # 
    # if latest_signal_info:
    #     price_str_tick = latest_signal_info.get('price', 'N/A')
    #     print(f"  Precio Actual : {price_str_tick}")
    # 
    #     print("  Indicadores TA:")
    #     
    #     ema_val = latest_signal_info.get('ema', 'N/A')
    #     w_inc_val = latest_signal_info.get('weighted_increment', 'N/A')
    #     w_dec_val = latest_signal_info.get('weighted_decrement', 'N/A')
    #     inc_pct_val = latest_signal_info.get('increment_pct', 'N/A')
    #     dec_pct_val = latest_signal_info.get('decrement_pct', 'N/A')
    # 
    #     ema_str = f"{ema_val:.4f}" if isinstance(ema_val, (int, float)) else str(ema_val)
    #     w_inc_str = f"{w_inc_val:.4f}" if isinstance(w_inc_val, (int, float)) else str(w_inc_val)
    #     w_dec_str = f"{w_dec_val:.4f}" if isinstance(w_dec_val, (int, float)) else str(w_dec_val)
    #     inc_pct_str = f"{inc_pct_val:.4f}" if isinstance(inc_pct_val, (int, float)) else str(inc_pct_val)
    #     dec_pct_str = f"{dec_pct_val:.4f}" if isinstance(dec_pct_val, (int, float)) else str(dec_pct_val)
    # 
    #     print(f"    EMA       : {ema_str:<15} W.Inc : {w_inc_str:<8} W.Dec : {w_dec_str:<8}")
    #     print(f"    Inc %     : {inc_pct_str:<15} Dec % : {dec_pct_str:<8}")
    # 
    #     print("  Señal Generada:")
    #     print(f"    Signal: {signal_str:<15} Reason: {signal_reason}")
    # 
    #     print("  Estado Posiciones:")
    #     max_pos_l = long_op_info.get('max_posiciones_logicas', 'N/A') if long_op_info.get('estado') != 'DETENIDA' else 'N/A'
    #     max_pos_s = short_op_info.get('max_posiciones_logicas', 'N/A') if short_op_info.get('estado') != 'DETENIDA' else 'N/A'
    #     print(f"    Longs: {longs_count}/{max_pos_l} | Shorts: {shorts_count}/{max_pos_s}")
    #     
    #     # --- INICIO DE LA CORRECCIÓN: Usar los valores recalculados ---
    #     long_disp_str = f"{long_avail_margin:.4f}"
    #     long_used_str = f"{long_used_margin:.4f}"
    #     short_disp_str = f"{short_avail_margin:.4f}"
    #     short_used_str = f"{short_used_margin:.4f}"
    #     # --- FIN DE LA CORRECCIÓN ---
    #     print(f"    Margen Disp(L): {long_disp_str:<15} Usado(L): {long_used_str}")
    #     print(f"    Margen Disp(S): {short_disp_str:<15} Usado(S): {short_used_str}")
    #     
    #     print(f"    Ganancias Netas(L): {pnl_long_color}{long_pnl: <+10.4f}\033[0m | ROI(L): {pnl_long_color}{long_roi: >+7.2f}%\033[0m")
    #     print(f"    Ganancias Netas(S): {pnl_short_color}{short_pnl: <+10.4f}\033[0m | ROI(S): {pnl_short_color}{short_roi: >+7.2f}%\033[0m")
    # 
    #     transferido_val = summary.get('total_realized_pnl_session', 0.0)
    #     transferido_str = f"{transferido_val:+.4f}"
    #     
    #     liq_l_str = f"{avg_liq_l:.4f}" if isinstance(avg_liq_l, (int, float)) else "N/A"
    #     liq_s_str = f"{avg_liq_s:.4f}" if isinstance(avg_liq_s, (int, float)) else "N/A"
    #     
    #     # --- INICIO DE LA CORRECCIÓN: Cambios visuales solicitados ---
    #     print(f"    Avg LiqP Long : {liq_l_str}")
    #     print(f"    Avg LiqP Short: {liq_s_str}")
    #     print(f"    Total Transferido   : {transferido_str} USDT")
    #     # --- FIN DE LA CORRECCIÓN ---
    # else:
    #     print("  (Esperando primer evento de precio...)")

    # --- NUEVA LÓGICA DE RENDERIZADO ---
    now_str = datetime.datetime.now(timezone.utc).strftime('%H:%M:%S %d-%m-%Y (UTC)')
    print("=" * 90)
    print(f"{'Dashboard de la Sesión'.center(90)}")
    print(f"{now_str.center(90)}")
    
    # Llamar a las nuevas funciones de renderizado de bloques
    _render_session_status_block(summary)
    _render_signal_status_block(summary, config_module)
    _render_operations_status_block(summary)
    
    # --- FIN DE LA MODIFICACIÓN ---


# --- Lógica Principal de la Pantalla ---
def show_dashboard_screen(session_manager: Any):
    from ._session_config_editor import show_session_config_editor_screen

    config_module = _deps.get("config_module")
    if not TerminalMenu or not config_module or not sm_api or not session_manager:
        print("ERROR CRÍTICO: Dependencias del Dashboard no disponibles.")
        time.sleep(3)
        return

    sm_api.init_sm_api(session_manager)
    session_manager.start()

    clear_screen()
    print("Dashboard: Esperando la recepción del primer tick de precio del mercado...")
    
    wait_animation = ['|', '/', '-', '\\']
    i = 0
    while True:
        current_price = pm_api.get_current_market_price()
        if current_price and current_price > 0:
            print("\n¡Precio recibido! Cargando dashboard...")
            time.sleep(1.5)
            break
        print(f"\rEsperando... {wait_animation[i % len(wait_animation)]}", end="")
        i += 1
        time.sleep(0.2)

    # --- BUCLE PRINCIPAL DEL DASHBOARD (CICLO DE VIDA DE LA SESIÓN) ---
    while True:
        error_message = None
        summary = {}
        try:
            summary = sm_api.get_session_summary()
            if not summary or summary.get('error'):
                error_message = f"ADVERTENCIA: No se pudo obtener el estado de la sesión: {summary.get('error', 'Reintentando...')}"
        except Exception as e:
            error_message = f"ERROR CRÍTICO: Excepción inesperada en el dashboard: {e}"
        
        clear_screen()
        if error_message:
            print(f"\033[91m{error_message}\033[0m")
        
        if summary and not summary.get('error'):
            _render_dashboard_view(summary, config_module)
        
        # --- INICIO DE LA MODIFICACIÓN: Separador movido a _render_operations_status_block ---
        # print("=" * 80)
        # --- FIN DE LA MODIFICACIÓN ---
        
        menu_items = [
            "[1] Gestionar Operación LONG", 
            "[2] Gestionar Operación SHORT",
            "[3] Editar Configuración de Sesión", 
            "[4] Ver Logs en Tiempo Real",
            None,
            "[r] Refrescar",
            "[h] Ayuda", 
            "[q] Finalizar Sesión y Volver al Menú Principal"
        ]
        action_map = {
            0: 'manage_long', 1: 'manage_short', 2: 'edit_config', 3: 'view_logs',
            5: 'refresh', 6: 'help', 7: 'exit_session'
        }
        
        menu_options = helpers_module.MENU_STYLE.copy()
        menu_options['clear_screen'] = False
        menu_options['menu_cursor_style'] = ("fg_cyan", "bold")

        menu = TerminalMenu(menu_items, title="Acciones de la Sesión:", **menu_options)
        choice = menu.show()
        action = action_map.get(choice)
        
        if action == 'manage_long':
            operation_manager.show_operation_manager_screen(side_filter='long')
        elif action == 'manage_short':
            operation_manager.show_operation_manager_screen(side_filter='short')
        elif action == 'edit_config':
            changes_made = show_session_config_editor_screen(config_module)
            if changes_made:
                # Al guardar, notificamos al SessionManager. Pasamos el dict de claves que cambiaron.
                sm_api.update_session_parameters(changes_made) 
        elif action == 'view_logs': 
            _log_viewer.show_log_viewer()
        elif action == 'refresh':
            time.sleep(0.1)
            continue
        elif action == 'help': 
            helpers_module.show_help_popup("dashboard_main")
        elif action == 'exit_session' or choice is None:
            confirm_menu = TerminalMenu(["[1] Sí, finalizar sesión", "[2] No, continuar"], title="¿Confirmas finalizar la sesión actual?", **helpers_module.MENU_STYLE)
            if confirm_menu.show() == 0: 
                break
    
    final_summary_data = sm_api.get_session_summary()
    _display_final_summary(final_summary_data)
    
    if session_manager.is_running():
        session_manager.stop()
    
    from runner import shutdown_session_backend
    shutdown_session_backend(
        session_manager=session_manager,
        final_summary=final_summary_data,
        config_module=_deps.get("config_module"),
        open_snapshot_logger_module=_deps.get("open_snapshot_logger_module")
    )