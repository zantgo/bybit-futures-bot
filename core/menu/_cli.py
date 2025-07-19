# =============== INICIO ARCHIVO: core/menu/_cli.py (CORREGIDO) ===============
"""
Módulo de la Interfaz de Línea de Comandos (CLI).

Define los puntos de entrada para el bot utilizando la librería `click`.
Cada comando corresponde a un modo de operación y su única responsabilidad
es llamar al orquestador principal en `main.py` con el modo correcto.
"""
import click

# --- Dependencias del Proyecto ---
# NOTA: `run_selected_mode` se importa DENTRO de las funciones para evitar
# una importación circular con `main.py`.

# --- Definición del Grupo de Comandos Principal ---

@click.group(
    name="main_cli",
    help="""Punto de entrada principal del Bot de Trading.
    Selecciona un modo de operación para empezar.
    Ejemplo: python main.py live
    """
)
def main_cli():
    """Grupo de comandos principal para el bot."""
    pass

# --- Comandos Específicos para cada Modo de Operación ---

@main_cli.command(
    name="live",
    help="▶ Inicia el bot en modo LIVE INTERACTIVO con el Asistente de Trading."
)
def run_live_interactive_command():
    """Comando para ejecutar el modo Live Interactivo."""
    # <<< INICIO DE LA CORRECCIÓN: Importación local para romper el ciclo >>>
    from main import run_selected_mode
    # <<< FIN DE LA CORRECCIÓN >>>
    run_selected_mode("live_interactive")

@main_cli.command(
    name="backtest",
    help="[NO FUNCIONAL] Inicia el bot en modo BACKTEST INTERACTIVO."
)
def run_backtest_interactive_command():
    """Comando para ejecutar el modo Backtest Interactivo."""
    click.secho("ADVERTENCIA: El modo 'backtest' no está activo en esta versión.", fg="yellow")
    click.echo("Esta funcionalidad está en desarrollo.")
    # from main import run_selected_mode
    # run_selected_mode("backtest_interactive")

@main_cli.command(
    name="auto",
    help="[NO FUNCIONAL] Inicia el bot en modo AUTOMÁTICO en vivo."
)
def run_automatic_live_command():
    """Comando para ejecutar el modo Automático en vivo."""
    click.secho("ADVERTENCIA: El modo 'auto' no está activo en esta versión.", fg="yellow")
    click.echo("Esta funcionalidad está en desarrollo.")
    # from main import run_selected_mode
    # run_selected_mode("automatic")

@main_cli.command(
    name="backtest-auto",
    help="[NO FUNCIONAL] Inicia el bot en modo BACKTEST AUTOMÁTICO."
)
def run_automatic_backtest_command():
    """Comando para ejecutar el modo Backtest Automático."""
    click.secho("ADVERTENCIA: El modo 'backtest-auto' no está activo en esta versión.", fg="yellow")
    click.echo("Esta funcionalidad está en desarrollo.")
    # from main import run_selected_mode
    # run_selected_mode("automatic_backtest")

# =============== FIN ARCHIVO: core/menu/_cli.py (CORREGIDO) ===============