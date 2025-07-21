# core/strategy/workflow/_pm_interaction.py

"""
Módulo para la Interacción con el Position Manager (PM).

Responsabilidad: Centralizar todas las llamadas desde el flujo de trabajo
del Event Processor hacia la fachada del Position Manager. Esto incluye
actualizar el PM con nuevos precios y enviarle las señales generadas.
"""
import sys
import os
import datetime
import traceback
from typing import Dict, Any, Optional

# --- INICIO DE CAMBIOS: Importaciones Adaptadas ---

# Ajustar sys.path para importaciones absolutas
if __name__ != "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(script_dir))))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

# Importar dependencias con rutas absolutas desde la raíz del proyecto
try:
    import config
    from core.strategy import pm as position_manager
    from core.logging import memory_logger
except ImportError as e:
    print(f"ERROR [Workflow PM Interaction Import]: Falló importación de dependencias: {e}")
    config = None; position_manager = None
    class MemoryLoggerFallback:
        def log(self, msg, level="INFO"): print(f"[{level}] {msg}")
    memory_logger = MemoryLoggerFallback()

# --- FIN DE CAMBIOS: Importaciones Adaptadas ---


# --- Funciones de Interacción con el PM ---

def update_pm_with_tick(current_price: float, timestamp: datetime.datetime):
    """
    Actualiza el Position Manager con el precio actual para que compruebe
    y gestione las posiciones abiertas (SL, TS, etc.).
    """
    pm_enabled_runtime = getattr(config, 'POSITION_MANAGEMENT_ENABLED', False)
    if not (pm_enabled_runtime and position_manager and position_manager.is_initialized()):
        return

    try:
        position_manager.check_and_close_positions(current_price, timestamp)
    except Exception as pm_err:
        memory_logger.log(f"ERROR llamando a PM.check_and_close_positions: {pm_err}", level="ERROR")
        memory_logger.log(f"Traceback: {traceback.format_exc()}", level="ERROR")

def send_signal_to_pm(
    signal_data: Optional[Dict[str, Any]],
    current_price: float,
    timestamp: datetime.datetime,
    operation_mode: str
):
    """
    Envía la señal generada al Position Manager para que evalúe si debe
    abrir una nueva posición.
    """
    pm_enabled_runtime = getattr(config, 'POSITION_MANAGEMENT_ENABLED', False)
    if not (pm_enabled_runtime and position_manager and position_manager.is_initialized()):
        return

    if not signal_data:
        return
        
    try:
        # En la refactorización, solo nos queda el modo 'live_interactive'.
        # La lógica de 'market_context' para modos automáticos se elimina.
        if operation_mode == "live_interactive":
            position_manager.handle_low_level_signal(
                signal=signal_data.get("signal"),
                entry_price=current_price,
                timestamp=timestamp
            )
        # El bloque 'else' para el modo automático ha sido eliminado.
        
    except Exception as pm_err:
        memory_logger.log(f"ERROR llamando a PM.handle_low_level_signal: {pm_err}", level="ERROR")
        memory_logger.log(f"Traceback: {traceback.format_exc()}", level="ERROR")