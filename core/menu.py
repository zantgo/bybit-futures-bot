# =============== INICIO ARCHIVO: core/menu.py (CORREGIDO Y COMPLETO) ===============
"""
Módulo para gestionar la interfaz de línea de comandos (CLI) completa del bot.
Utiliza `click` para crear un Asistente de Trading Interactivo y profesional.
"""
import click
import time
import datetime
from typing import Dict, Any, Optional, Tuple

# --- Dependencias del Proyecto ---
# Se importan de forma segura para evitar fallos si el módulo se usa aisladamente.
try:
    from core.strategy import pm_facade as position_manager
    from core import utils
    import config
except ImportError:
    # Definir stubs si las importaciones fallan, para que el módulo al menos se cargue.
    position_manager = type('obj', (object,), {
        'get_position_summary': lambda: {"error": "PM no importado"},
        'get_current_price_for_exit': lambda: 0.0,
        'get_unrealized_pnl': lambda p: 0.0,
        'pm_state': type('obj', (object,), {
            'get_individual_stop_loss_pct': lambda: 0.0,
            'get_trailing_stop_params': lambda: {'activation': 0.0, 'distance': 0.0},
            'get_global_tp_pct': lambda: 0.0
        })(),
        'get_global_sl_pct': lambda: 0.0,
        'get_session_time_limit': lambda: {'duration': 0, 'action': 'N/A'},
        'display_logical_positions': lambda: click.echo("  (PM no importado)")
    })()
    utils = None
    config = None

# --- Funciones de Ayuda para Formato ---

def print_header(title: str, width: int = 85):
    """Imprime una cabecera estilizada y consistente."""
    click.echo("\n" + "=" * width)
    click.secho(f"{title.center(width)}", fg='cyan', bold=True)
    if utils and hasattr(utils, 'format_datetime'):
        now_str = utils.format_datetime(datetime.datetime.now())
        click.secho(f"{now_str.center(width)}", fg='white')
    click.echo("=" * width)

def print_status_section(title: str, data: Dict[str, Any], color: str = 'yellow'):
    """Imprime una sección formateada del reporte de estado."""
    click.secho(f"\n--- {title} ---", fg=color, bold=True)
    if not data:
        click.echo("  (No hay datos disponibles)")
        return
    max_key_len = max(len(str(key)) for key in data.keys()) if data else 20
    for key, value in data.items():
        click.echo(f"  {str(key):<{max_key_len + 2}}: {value}")

# ---
# --- Asistente de Inicio / Wizard para el Modo Live (REEMPLAZA MENÚS PRE-INICIO)
# ---

def run_trading_assistant_wizard() -> Tuple[Optional[float], Optional[int]]:
    """Guía al usuario a través de la configuración inicial antes de lanzar el bot."""
    print_header("Asistente de Configuración - Modo Live Interactivo")
    click.secho("¡Bienvenido! Este asistente te guiará para configurar tu sesión de trading.", fg='green')

    # 1. Configurar Símbolo
    click.secho("\nPASO 1: SÍMBOLO DEL TICKER", bold=True)
    click.echo("Este es el par de trading que el bot monitoreará (ej: BTCUSDT, ETHUSDT).")
    default_symbol = getattr(config, 'TICKER_SYMBOL', 'BTCUSDT')
    symbol = click.prompt("Introduce el símbolo del ticker", default=default_symbol).upper()
    setattr(config, 'TICKER_SYMBOL', symbol)
    click.secho(f"Símbolo establecido en: {symbol}\n", fg='green')
    time.sleep(1)

    # 2. Configurar Capital
    print_header("Configuración de Capital para la Sesión")
    click.secho("PASO 2: GESTIÓN DE CAPITAL", bold=True)
    click.echo("Define cuánto capital arriesgar por cada posición y cuántas posiciones simultáneas permitir.")
    
    default_base_size = float(getattr(config, 'POSITION_BASE_SIZE_USDT', 10.0))
    base_size = click.prompt(
        "Tamaño base por posición (USDT)", 
        type=float, 
        default=default_base_size
    )
    
    default_slots = int(getattr(config, 'POSITION_MAX_LOGICAL_POSITIONS', 1))
    slots = click.prompt(
        "Número máximo de posiciones (slots) por lado (long/short)",
        type=click.IntRange(1, 100),
        default=default_slots
    )
    click.secho(f"Configuración de capital: {slots} posiciones de ~{base_size:.2f} USDT cada una.\n", fg='green')
    time.sleep(1)

    # 3. Confirmación Final
    print_header("Confirmación Final")
    click.secho("Revisa la configuración de tu sesión:", bold=True)
    click.echo(f"  - Símbolo:      {symbol}")
    click.echo(f"  - Tamaño Base:  {base_size:.2f} USDT")
    click.echo(f"  - Slots/Lado:   {slots}")
    click.echo(f"  - Apalancamiento: {getattr(config, 'POSITION_LEVERAGE', 1.0)}x")
    
    if not click.confirm("\n¿Es correcta esta configuración para iniciar el bot?", default=True):
        click.secho("Inicio cancelado por el usuario.", fg='red')
        return None, None

    return base_size, slots

# ---
# --- CLI de Intervención en Vivo (NUEVA VERSIÓN MEJORADA)
# ---
@click.group(name="cli", invoke_without_command=True, chain=True)
@click.pass_context
def intervention_cli(ctx):
    """Grupo de comandos para la intervención manual en el modo Live."""
    if ctx.invoked_subcommand is None:
        print_header("Asistente de Trading Interactivo")
        click.echo("El bot está operando. Usa los siguientes comandos para gestionar la sesión:")
        click.secho("\nESTADO Y CONTROL:", bold=True)
        click.echo("  status              Muestra el estado completo de la sesión.")
        click.echo("  set-mode            Cambia el modo de trading (long, short, neutral...).")
        
        click.secho("\nGESTIÓN DE RIESGO:", bold=True)
        click.echo("  set-risk            Ajusta los parámetros de Stop Loss y Trailing Stop.")
        click.echo("  set-limits          Ajusta los límites globales de ROI y Tiempo de la sesión.")
        
        click.secho("\nGESTIÓN DE CAPITAL:", bold=True)
        click.echo("  set-capital         Ajusta el tamaño de posición y el número de slots.")
        
        click.secho("\nOPERACIONES:", bold=True)
        click.echo("  close               Cierra una posición específica por índice.")
        click.echo("  close-all           Cierra todas las posiciones de un lado (long/short).")

        click.secho("\nASISTENTES:", bold=True)
        click.echo("  trail-roi           Inicia el asistente para ajustar el TP Global como un Trailing Stop.")
        
        click.secho("\nSISTEMA:", bold=True)
        click.echo("  exit                Sale del menú y continúa la operación del bot.")
        
        click.echo("\nUsa '[comando] --help' para ver más detalles.")

@intervention_cli.command(name="status")
def show_status():
    """Muestra el estado detallado de la sesión y las posiciones."""
    print_header("Estado Actual de la Sesión")
    summary = position_manager.get_position_summary()
    if not summary or summary.get('error'):
        click.secho(f"Error al obtener estado: {summary.get('error', 'Desconocido')}", fg='red'); return

    manual_state = summary.get('manual_mode_status', {})
    limit_str = manual_state.get('limit') or 'Ilimitados'
    
    current_price = position_manager.get_current_price_for_exit() or 0.0
    unrealized_pnl = position_manager.get_unrealized_pnl(current_price)
    total_pnl = summary.get('total_realized_pnl_session', 0.0) + unrealized_pnl
    initial_capital = summary.get('initial_total_capital', 0.0)
    current_roi = (total_pnl / initial_capital) * 100 if initial_capital > 0 else 0.0

    session_status = {
        "Modo Manual Actual": f"{manual_state.get('mode', 'N/A')} (Trades: {manual_state.get('executed', 0)}/{limit_str})",
        "Precio Actual de Mercado": f"{current_price:.4f} USDT",
    }
    capital_status = {
        "Tamaño Base (USDT)": f"{summary.get('initial_base_position_size_usdt', 0.0):.4f}",
        "Slots Máximos / Lado": summary.get('max_logical_positions', 0),
        "Apalancamiento": f"{summary.get('leverage', 0.0):.1f}x",
    }
    balances = summary.get('bm_balances', {})
    perf_status = {
        "Capital Inicial Total": f"{initial_capital:.2f} USDT",
        "PNL Realizado (Sesión)": f"{summary.get('total_realized_pnl_session', 0.0):+.4f} USDT",
        "PNL No Realizado (Actual)": f"{unrealized_pnl:+.4f} USDT",
        "PNL Total (Estimado)": f"{total_pnl:+.4f} USDT",
        "ROI Actual (Estimado)": f"{current_roi:+.2f}%",
        "Balance Profit Acumulado": f"{balances.get('profit_balance', 0.0):.4f} USDT",
    }
    risk_status = {
        "Stop Loss Individual": f"{position_manager.pm_state.get_individual_stop_loss_pct() or 0.0:.2f}%",
        "Trailing Stop Activación": f"{position_manager.pm_state.get_trailing_stop_params()['activation']:.2f}%",
        "Trailing Stop Distancia": f"{position_manager.pm_state.get_trailing_stop_params()['distance']:.2f}%",
        "SL Global (ROI)": f"-{position_manager.get_global_sl_pct() or 0.0:.2f}%",
        "TP Global (ROI)": f"+{position_manager.pm_state.get_global_tp_pct() or 0.0:.2f}%",
        "Límite de Tiempo": f"{position_manager.get_session_time_limit()['duration']} min (Acción: {position_manager.get_session_time_limit()['action']})",
    }

    print_status_section("Estado de la Sesión", session_status, color='cyan')
    print_status_section("Configuración de Capital", capital_status, color='yellow')
    print_status_section("Rendimiento y Balances", perf_status, color='green')
    print_status_section("Parámetros de Riesgo Actuales", risk_status, color='magenta')

    click.secho("\n--- Posiciones Lógicas Abiertas ---", fg='white', bold=True)
    position_manager.display_logical_positions()

@intervention_cli.command(name="set-mode")
@click.option('--mode', type=click.Choice(['neutral', 'long_only', 'short_only', 'long_short'], case_sensitive=False), required=True)
@click.option('--trades', type=int, default=0, help="Límite de trades (0 para ilimitado).")
@click.option('--close-open', is_flag=True, help="Forzar cierre de posiciones del lado desactivado.")
def set_mode(mode, trades, close_open):
    """Cambia el modo de trading y opcionalmente el límite de trades."""
    if close_open:
        click.confirm(f"ADVERTENCIA: ¿Seguro que quieres cerrar posiciones abiertas al cambiar de modo?", abort=True)
    success, message = position_manager.set_manual_trading_mode(mode.upper(), trades, close_open)
    click.secho(message, fg='green' if success else 'red')

@intervention_cli.command(name="set-capital")
@click.option('--size', type=float, help="Nuevo tamaño base por posición en USDT.")
@click.option('--slots', type=int, help="Nuevo número máximo de slots por lado.")
def set_capital(size, slots):
    """Ajusta el tamaño base de la posición y/o el número de slots."""
    if not size and not slots:
        click.echo("Debes proporcionar --size o --slots."); return
    if size:
        success, msg = position_manager.set_base_position_size(size)
        click.secho(f"-> Tamaño Base: {msg}", fg='green' if success else 'red')
    if slots:
        current_slots = position_manager.get_position_summary().get('max_logical_positions', 0)
        if slots > current_slots:
            for _ in range(slots - current_slots): success, msg = position_manager.add_max_logical_position_slot()
        elif slots < current_slots:
            for _ in range(current_slots - slots): success, msg = position_manager.remove_max_logical_position_slot()
        click.secho(f"-> Slots: {msg}", fg='green' if success else 'red')

@intervention_cli.command(name="set-risk")
@click.option('--sl-ind', type=float, help="Stop Loss Individual por posición en % (ej: 2.5).")
@click.option('--ts-act', type=float, help="Activación del Trailing Stop en % (ej: 0.5).")
@click.option('--ts-dist', type=float, help="Distancia del Trailing Stop en % (ej: 0.15).")
def set_risk(sl_ind, ts_act, ts_dist):
    """Ajusta los parámetros de riesgo por posición (SL y TS)."""
    if all(arg is None for arg in [sl_ind, ts_act, ts_dist]):
        click.echo("Debes proporcionar al menos una opción."); return
    if sl_ind is not None:
        success, msg = position_manager.set_individual_stop_loss_pct(sl_ind)
        click.secho(f"-> SL Individual: {msg}", fg='green' if success else 'red')
    if ts_act is not None or ts_dist is not None:
        params = position_manager.pm_state.get_trailing_stop_params()
        new_act = ts_act if ts_act is not None else params['activation']
        new_dist = ts_dist if ts_dist is not None else params['distance']
        success, msg = position_manager.set_trailing_stop_params(new_act, new_dist)
        click.secho(f"-> Trailing Stop: {msg}", fg='green' if success else 'red')

@intervention_cli.command(name="set-limits")
@click.option('--sl-roi', type=float, help="Stop Loss Global por ROI % (ej: 2.5 para -2.5%). 0 para desactivar.")
@click.option('--tp-roi', type=float, help="Take Profit Global por ROI % (ej: 5 para +5%). 0 para desactivar.")
@click.option('--time-limit', type=int, help="Límite de tiempo de sesión en minutos. 0 para desactivar.")
def set_limits(sl_roi, tp_roi, time_limit):
    """Ajusta los límites globales de la sesión (ROI y Tiempo)."""
    if all(arg is None for arg in [sl_roi, tp_roi, time_limit]):
        click.echo("Debes proporcionar al menos una opción."); return
    if sl_roi is not None:
        success, msg = position_manager.set_global_stop_loss_pct(abs(sl_roi))
        click.secho(f"-> Límite SL por ROI: {msg}", fg='green' if success else 'red')
    if tp_roi is not None:
        success, msg = position_manager.set_global_take_profit_pct(abs(tp_roi))
        click.secho(f"-> Límite TP por ROI: {msg}", fg='green' if success else 'red')
    if time_limit is not None:
        action = "STOP" if time_limit > 0 and click.confirm("¿La acción al alcanzar el tiempo debe ser una parada de emergencia (STOP)?", default=False) else "NEUTRAL"
        success, msg = position_manager.set_session_time_limit(time_limit, action)
        click.secho(f"-> Límite por Tiempo: {msg}", fg='green' if success else 'red')

@intervention_cli.command(name="close")
@click.option('--side', type=click.Choice(['long', 'short']), required=True)
@click.option('--index', type=int, required=True, help="Índice de la posición a cerrar (ver 'status').")
def close_position(side, index):
    """Cierra una posición lógica específica por su índice."""
    click.confirm(f"¿Seguro que quieres cerrar la posición {side.upper()} en el índice {index}?", abort=True)
    success, msg = position_manager.manual_close_logical_position_by_index(side, index)
    click.secho(msg, fg='green' if success else 'red')

@intervention_cli.command(name="close-all")
@click.option('--side', type=click.Choice(['long', 'short']), required=True)
def close_all_positions(side):
    """Cierra TODAS las posiciones lógicas abiertas de un lado."""
    count = position_manager.get_position_summary().get(f'open_{side}_positions_count', 0)
    if count == 0:
        click.echo(f"No hay posiciones {side.upper()} abiertas."); return
    click.confirm(f"ADVERTENCIA: ¿Seguro que quieres cerrar {count} posición(es) {side.upper()}?", abort=True)
    success = position_manager.close_all_logical_positions(side, reason="MANUAL_ALL")
    click.secho(f"Órdenes de cierre enviadas.", fg='green' if success else 'red')

@intervention_cli.command(name="trail-roi")
def trail_roi_assistant():
    """Asistente interactivo para ajustar el TP Global basado en el ROI actual."""
    print_header("Asistente de Trailing ROI Global")
    click.secho("Este modo te permite ajustar el Take Profit Global de la sesión dinámicamente.", fg='yellow')
    click.secho("Presiona Enter para actualizar, escribe un nuevo % de TP para ajustarlo, o 'exit' para salir.", fg='yellow')
    
    while True:
        summary = position_manager.get_position_summary()
        current_price = position_manager.get_current_price_for_exit() or 0.0
        unrealized_pnl = position_manager.get_unrealized_pnl(current_price)
        realized_pnl = summary.get('total_realized_pnl_session', 0.0)
        initial_capital = summary.get('initial_total_capital', 0.0)
        current_roi = ((realized_pnl + unrealized_pnl) / initial_capital) * 100 if initial_capital > 0 else 0.0
        current_tp_roi = position_manager.pm_state.get_global_tp_pct() or 0.0
        
        click.echo("\n" + "-"*50)
        click.echo(f" PNL Realizado: {realized_pnl:+.4f} | PNL No Realizado: {unrealized_pnl:+.4f}")
        click.secho(f" ROI Actual (Estimado): {current_roi:+.2f}%", bold=True, fg='cyan')
        click.secho(f" TP Global Configurado: +{current_tp_roi:.2f}%", fg='yellow')
        click.echo("-"*50)

        user_input = click.prompt("Nuevo TP % (o Enter para refrescar, 'exit' para salir)", default="", show_default=False)

        if user_input.lower().strip() in ['exit', 'quit', 'q']:
            break
        if user_input == "":
            continue
        try:
            new_tp = float(user_input)
            if new_tp < 0:
                click.secho("El TP debe ser un número positivo.", fg='red'); continue
            success, msg = position_manager.set_global_take_profit_pct(new_tp)
            click.secho(msg, fg='green' if success else 'red')
        except ValueError:
            click.secho("Entrada inválida. Por favor, introduce un número o 'exit'.", fg='red')

def run_cli_menu_loop():
    """Ejecuta el bucle del menú interactivo de intervención."""
    ctx = click.Context(intervention_cli, info_name='cli')
    intervention_cli.invoke(ctx) # Muestra la ayuda la primera vez
    while True:
        try:
            command_str = input("\n(asistente) > ")
            if command_str.lower().strip() in ['exit', 'quit', 'q', '0']:
                break
            if not command_str.strip():
                continue
            # Corregir la llamada para que el nombre del programa no aparezca en errores
            args = command_str.split()
            intervention_cli(args, standalone_mode=False, prog_name="")
        except click.exceptions.UsageError as e:
            click.secho(f"Error de uso: {e.message}", fg='red')
        except click.exceptions.Abort:
            click.secho("Operación cancelada.", fg='yellow')
        except Exception as e:
            click.secho(f"Error inesperado en el menú: {e}", fg='red')

# --- Grupo principal de comandos para `main.py` (Mantenido para compatibilidad) ---
@click.group(name="main_cli")
def main_cli():
    """Punto de entrada principal del Bot de Trading. Selecciona un modo para empezar."""
    pass

@main_cli.command(name="live")
def run_live_interactive_command():
    """Inicia el bot en modo Live Interactivo con el Asistente de Trading."""
    from main import run_selected_mode
    run_selected_mode("live_interactive")

@main_cli.command(name="backtest")
def run_backtest_interactive_command():
    """Inicia el bot en modo Backtest Interactivo."""
    from main import run_selected_mode
    run_selected_mode("backtest_interactive")

@main_cli.command(name="auto")
def run_automatic_live_command():
    """Inicia el bot en modo Automático (Live)."""
    from main import run_selected_mode
    run_selected_mode("automatic")

@main_cli.command(name="backtest-auto")
def run_automatic_backtest_command():
    """Inicia el bot en modo Backtest Automático."""
    from main import run_selected_mode
    run_selected_mode("automatic_backtest")


# --- CÓDIGO OBSOLETO COMENTADO (Para referencia) ---
# Las siguientes funciones han sido reemplazadas por el `run_trading_assistant_wizard`
# y el nuevo bucle de la CLI, pero se mantienen aquí comentadas por si se necesitaran
# en otros contextos o para consulta histórica.
"""
def get_live_main_menu_choice() -> str:
    # OBSOLETO: Reemplazado por el flujo del Asistente de Trading.
    print_header("Modo Live - Menú Pre-Inicio")
    click.echo("Seleccione una acción:\n")
    click.echo("  1. Ver Estado Detallado de Cuentas (API)")
    click.echo("  2. Iniciar el Bot (Modo Interactivo)")
    click.echo("  3. Probar Ciclo Completo (Apertura/Cierre)")
    click.echo("  4. Ver Tabla de Posiciones Lógicas (Si hay alguna)")
    click.echo("-" * 85)
    click.echo("  0. Salir del Modo Live")
    click.echo("=" * 85)
    return click.prompt("Seleccione una opción", type=str, default="2")

def get_position_setup_interactively() -> Tuple[Optional[float], Optional[int]]:
    # OBSOLETO: Reemplazado por `run_trading_assistant_wizard`.
    print_header("Configuración de Capital para la Sesión")
    base_size_usdt: Optional[float] = None
    initial_slots: Optional[int] = None
    default_base_size = float(getattr(config, 'POSITION_BASE_SIZE_USDT', 10.0))
    default_slots = int(getattr(config, 'POSITION_MAX_LOGICAL_POSITIONS', 1))

    base_size_usdt = click.prompt(
        "Tamaño base por posición (USDT)", 
        type=float, 
        default=default_base_size
    )
    if base_size_usdt <= 0:
        click.secho("Configuración cancelada.", fg='yellow')
        return None, None
        
    initial_slots = click.prompt(
        "Número inicial de slots por lado",
        type=click.IntRange(1, 100), # Rango para evitar valores absurdos
        default=default_slots
    )
    if initial_slots <= 0:
        click.secho("Configuración cancelada.", fg='yellow')
        return None, None
        
    return base_size_usdt, initial_slots

def display_live_pre_start_overview(account_states: Dict[str, Any], symbol: Optional[str]):
    # OBSOLETO: La información ahora se muestra en el comando `status` de forma más completa.
    print_header(f"Resumen de Estado Real Pre-Inicio para {symbol}")
    if not account_states:
        click.secho("No se pudo obtener información del estado real de las cuentas.", fg='red')
        return
    
    for acc_name, state in account_states.items():
        click.secho(f"\n--- Cuenta: {acc_name} ---", bold=True)
        unified = state.get('unified_balance', {})
        positions = state.get('positions', [])
        if unified:
             click.echo(f"  Equidad Total (USDT): {unified.get('totalEquity', 0.0):.2f}")
        if positions:
            click.secho(f"  Posiciones Abiertas para {symbol}: {len(positions)}", fg='yellow')
        else:
            click.echo(f"  Sin posiciones abiertas para {symbol}.")

    click.echo("\n" + "=" * 85)
    input("Presione Enter para continuar al menú...")
"""
# =============== FIN ARCHIVO: core/menu.py (CORREGIDO Y COMPLETO) ===============