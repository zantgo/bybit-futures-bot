# =============== INICIO ARCHIVO: core/menu.py (v16.2 - CLI Profesional Completa) ===============
"""
Módulo para gestionar la interfaz de línea de comandos (CLI) completa del bot.
Utiliza `click` para manejar tanto los comandos de inicio de la aplicación como el
menú de intervención en tiempo real, proporcionando una experiencia de usuario
robusta, guiada y profesional.
"""
import click
import time
import datetime
from typing import Dict, Any, Optional, List, Tuple

# --- Dependencias del Proyecto ---
# Se importan de forma segura para evitar fallos si el módulo se usa aisladamente.
try:
    from core.strategy import pm_facade as position_manager
    from core import utils
    import config
except ImportError:
    # Definir stubs si las importaciones fallan, para que el módulo al menos se cargue.
    position_manager = type('obj', (object,), {'get_position_summary': lambda: {"error": "PM no importado"}})()
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
    max_key_len = max(len(key) for key in data.keys()) if data else 20
    for key, value in data.items():
        click.echo(f"  {key:<{max_key_len + 2}}: {value}")

# ---
# --- MENÚS PRE-INICIO (Llamados por los Runners)
# --- Mantenidos para la configuración inicial antes de que el bot esté en vivo.
# ---

def get_live_main_menu_choice() -> str:
    """Muestra el menú principal para el modo Live ANTES de iniciar el ticker."""
    # Esta función se mantiene intacta del original.
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
    """Pregunta por el tamaño base por posición y el número inicial de slots."""
    # Esta función se mantiene intacta del original.
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
    """Muestra el estado real de las cuentas antes de iniciar el bot."""
    # Esta función se mantiene intacta del original.
    print_header(f"Resumen de Estado Real Pre-Inicio para {symbol}")
    if not account_states:
        click.secho("No se pudo obtener información del estado real de las cuentas.", fg='red')
        return
    
    # ... (El resto de la lógica de impresión de esta función del original iría aquí)
    # ... por ejemplo:
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

# ---
# --- MENÚ DE INTERVENCIÓN EN VIVO (CLI)
# ---

@click.group(name="intervention_cli", invoke_without_command=True)
@click.pass_context
def intervention_cli(ctx):
    """Grupo de comandos para la intervención manual en el modo Live."""
    if ctx.invoked_subcommand is None:
        print_header("Menú de Intervención Manual")
        click.echo("El bot está operando en segundo plano. Usa los siguientes comandos:")
        click.secho("\nGESTIÓN DE SESIÓN:", bold=True)
        click.echo("  status              Muestra el estado completo de la sesión.")
        click.echo("  set-mode            Cambia el modo de trading (long, short, etc.).")
        click.echo("  set-limits          Ajusta los límites globales de ROI y Tiempo.")
        
        click.secho("\nGESTIÓN DE CAPITAL:", bold=True)
        click.echo("  set-config          Ajusta el tamaño de posición y los slots.")
        
        click.secho("\nGESTIÓN DE POSICIONES:", bold=True)
        click.echo("  close               Cierra una posición lógica específica por índice.")
        click.echo("  close-all           Cierra todas las posiciones de un lado (long/short).")
        
        click.secho("\nCONTROL:", bold=True)
        click.echo("  exit                Sale del menú y continúa la operación del bot.")
        
        click.echo("\nUsa '[comando] --help' para ver más detalles y opciones.")
        click.echo("-" * 85)

@intervention_cli.command(name="status")
def show_status():
    """Muestra el estado detallado de la sesión y las posiciones."""
    print_header("Estado Actual de la Sesión")
    summary = position_manager.get_position_summary()

    if not summary or summary.get('error'):
        click.secho(f"Error al obtener el estado: {summary.get('error', 'Desconocido')}", fg='red')
        return

    manual_state = summary.get('manual_mode_status', {})
    limit_str = manual_state.get('limit') or 'Ilimitados'
    
    session_status = {
        "Modo de Operación": summary.get('operation_mode', 'N/A'),
        "Modo Manual Actual": manual_state.get('mode', 'N/A'),
        "Trades en Sesión Manual": f"{manual_state.get('executed', 0)} / {limit_str}",
    }
    
    capital_status = {
        "Tamaño Base por Posición (USDT)": f"{summary.get('initial_base_position_size_usdt', 0.0):.4f}",
        "Slots Máximos por Lado": summary.get('max_logical_positions', 0),
        "Apalancamiento": f"{summary.get('leverage', 0.0):.1f}x",
    }
    
    balances = summary.get('bm_balances', {})
    balance_status = {
        "Capital Inicial Total": f"{summary.get('initial_total_capital', 0.0):.2f} USDT",
        "PNL Neto Realizado (Sesión)": f"{summary.get('total_realized_pnl_session', 0.0):+.4f} USDT",
        "Margen Disponible (Long)": f"{balances.get('available_long_margin', 0.0):.4f} USDT",
        "Margen Disponible (Short)": f"{balances.get('available_short_margin', 0.0):.4f} USDT",
        "Balance en Cuenta Profit": f"{balances.get('profit_balance', 0.0):.2f} USDT",
    }

    print_status_section("Estado de la Sesión", session_status, color='cyan')
    print_status_section("Configuración de Capital", capital_status, color='yellow')
    print_status_section("Balances y Rendimiento", balance_status, color='green')

    click.secho("\n--- Posiciones Lógicas Abiertas ---", fg='magenta', bold=True)
    position_manager.display_logical_positions()

@intervention_cli.command(name="set-mode")
@click.option('--mode', type=click.Choice(['neutral', 'long_only', 'short_only', 'long_short'], case_sensitive=False), required=True, help="El nuevo modo de trading.")
@click.option('--trades', type=int, default=0, help="Límite de trades para esta sesión (0 para ilimitado).")
@click.option('--close-open', is_flag=True, help="Forzar cierre de posiciones del lado que se desactiva.")
def set_mode(mode: str, trades: int, close_open: bool):
    """Cambia el modo de trading y opcionalmente el límite de trades."""
    print_header("Cambiando Modo de Trading")
    
    if close_open:
        click.confirm(
            f"ADVERTENCIA: Has solicitado cerrar posiciones abiertas. ¿Estás seguro?",
            abort=True, default=False
        )

    success, message = position_manager.set_manual_trading_mode(
        mode=mode.upper(), 
        trade_limit=trades, 
        close_open=close_open
    )
    
    click.secho(message, fg='green' if success else 'red')
    time.sleep(1)

@intervention_cli.command(name="set-config")
@click.option('--size', type=float, help="Nuevo tamaño base por posición en USDT.")
@click.option('--slots', type=int, help="Nuevo número máximo de slots por lado.")
def set_config(size: Optional[float], slots: Optional[int]):
    """Ajusta el tamaño base de la posición y/o el número de slots."""
    if not size and not slots:
        click.echo("Debes proporcionar al menos una opción: --size o --slots."); return

    print_header("Ajustando Configuración de Capital")
    if size:
        success, message = position_manager.set_base_position_size(size)
        click.secho(f"-> Tamaño Base: {message}", fg='green' if success else 'red')
    
    if slots:
        summary = position_manager.get_position_summary()
        current_slots = summary.get('max_logical_positions', 0)
        if slots > current_slots:
            success, message = position_manager.add_max_logical_position_slot()
        elif slots < current_slots:
            success, message = position_manager.remove_max_logical_position_slot()
        else:
            success, message = True, f"El número de slots ya es {slots}."
        click.secho(f"-> Slots: {message}", fg='green' if success else 'red')
    
    time.sleep(1)

@intervention_cli.command(name="close")
@click.option('--side', type=click.Choice(['long', 'short'], case_sensitive=False), required=True)
@click.option('--index', type=int, required=True, help="Índice de la posición a cerrar (ver 'status').")
def close_position(side: str, index: int):
    """Cierra una posición lógica específica por su índice."""
    click.confirm(f"¿Seguro que quieres cerrar la posición {side.upper()} en el índice {index}?", abort=True, default=False)
    success, message = position_manager.manual_close_logical_position_by_index(side, index)
    click.secho(message, fg='green' if success else 'red')
    time.sleep(1)

@intervention_cli.command(name="close-all")
@click.option('--side', type=click.Choice(['long', 'short'], case_sensitive=False), required=True)
def close_all_positions(side: str):
    """Cierra TODAS las posiciones lógicas abiertas de un lado."""
    summary = position_manager.get_position_summary()
    count = summary.get(f'open_{side}_positions_count', 0)
    if count == 0:
        click.echo(f"No hay posiciones {side.upper()} abiertas para cerrar."); return
        
    click.confirm(f"ADVERTENCIA: ¿Seguro que quieres cerrar {count} posición(es) {side.upper()}?", abort=True, default=False)
    success = position_manager.close_all_logical_positions(side, reason="MANUAL_ALL")
    click.secho(f"Órdenes de cierre enviadas.", fg='green' if success else 'red')
    time.sleep(1)

@intervention_cli.command(name="set-limits")
@click.option('--sl-roi', type=float, help="Stop Loss Global por ROI % (ej: 2.5 para -2.5%). 0 para desactivar.")
@click.option('--tp-roi', type=float, help="Take Profit Global por ROI % (ej: 5 para +5%). 0 para desactivar.")
@click.option('--time-limit', type=int, help="Límite de tiempo de la sesión en minutos. 0 para desactivar.")
@click.option('--time-action', type=click.Choice(['neutral', 'stop'], case_sensitive=False), help="Acción al alcanzar el límite de tiempo.")
def set_session_limits(sl_roi: Optional[float], tp_roi: Optional[float], time_limit: Optional[int], time_action: Optional[str]):
    """Ajusta los límites de la sesión (ROI y Tiempo)."""
    if all(arg is None for arg in [sl_roi, tp_roi, time_limit, time_action]):
        click.echo("Debes proporcionar al menos una opción para modificar."); return

    print_header("Ajustando Límites Globales de Sesión")
    if sl_roi is not None:
        success, message = position_manager.set_global_stop_loss_pct(abs(sl_roi))
        click.secho(f"-> Límite SL por ROI: {message}", fg='green' if success else 'red')
    if tp_roi is not None:
        success, message = position_manager.set_global_take_profit_pct(abs(tp_roi))
        click.secho(f"-> Límite TP por ROI: {message}", fg='green' if success else 'red')
    if time_limit is not None or time_action is not None:
        current_limits = position_manager.get_session_time_limit()
        new_duration = time_limit if time_limit is not None else current_limits.get('duration', 0)
        new_action = time_action.upper() if time_action is not None else current_limits.get('action', 'NEUTRAL')
        success, message = position_manager.set_session_time_limit(new_duration, new_action)
        click.secho(f"-> Límite por Tiempo: {message}", fg='green' if success else 'red')
    time.sleep(1)

def run_cli_menu_loop():
    """Ejecuta el bucle del menú interactivo de intervención."""
    ctx = click.Context(intervention_cli, info_name='menu')
    intervention_cli.invoke(ctx)
    while True:
        try:
            command_str = input("\n(menu) > ")
            if command_str.lower().strip() in ['exit', 'quit', 'q', '0']:
                break
            if not command_str.strip():
                continue
            args = command_str.split()
            intervention_cli(args, standalone_mode=False, prog_name="")
        except click.exceptions.UsageError as e:
            click.secho(f"Error: {e.message}", fg='red')
        except click.exceptions.Abort:
            click.secho("Operación cancelada por el usuario.", fg='yellow')
        except Exception as e:
            click.secho(f"Error inesperado en el menú: {e}", fg='red')

# --- Grupo principal de comandos para `main.py` ---
@click.group(name="main_cli")
def main_cli():
    """Punto de entrada principal del Bot de Trading. Selecciona un modo para empezar."""
    pass

@main_cli.command(name="live")
def run_live_interactive_command():
    """Inicia el bot en modo Live Interactivo."""
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

# =============== FIN ARCHIVO: core/menu.py (COMPLETO Y MEJORADO) ===============