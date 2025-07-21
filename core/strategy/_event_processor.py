# core/strategy/_event_processor.py

"""
Orquestador Principal del Procesamiento de Eventos.

Este módulo recibe cada tick de precio y orquesta el flujo de trabajo
llamando a los módulos especializados del paquete `workflow` en el orden correcto.
También gestiona la visualización en consola del estado del tick.
"""
import sys
import os
import datetime
import traceback
import pandas as pd
import numpy as np
import json
import threading
from typing import Optional, Dict, Any

# --- INICIO DE CAMBIOS: Importaciones Adaptadas ---

# Ajustar sys.path para importaciones absolutas
if __name__ != "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(script_dir)))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

# Importar dependencias con rutas absolutas desde la raíz del proyecto
try:
    import config
    from core import utils
    from core.logging import memory_logger
    from core.strategy import pm as position_manager
    from core.strategy import ta, signal
    
    # Importar el paquete workflow completo
    from . import workflow

except ImportError as e:
    print(f"ERROR CRÍTICO [Event Proc Import]: Falló importación de dependencias: {e}")
    config=None; utils=None; memory_logger=None; position_manager=None;
    ta=None; signal=None; workflow=None
    traceback.print_exc()
    sys.exit(1)

# --- FIN DE CAMBIOS: Importaciones Adaptadas ---


# --- Estado del Módulo ---
_operation_mode = "unknown"
_global_stop_loss_event: Optional[threading.Event] = None

# --- Inicialización ---
def initialize(
    operation_mode: str,
    global_stop_loss_event: Optional[threading.Event] = None
):
    """
    Inicializa el orquestador de eventos y sus módulos de flujo de trabajo dependientes.
    """
    global _operation_mode, _global_stop_loss_event

    if not all([config, utils, ta, signal, workflow, memory_logger]):
        raise RuntimeError("Event Processor no pudo inicializarse por dependencias faltantes.")

    memory_logger.log("Event Processor: Inicializando orquestador...", level="INFO")
    _operation_mode = operation_mode
    _global_stop_loss_event = global_stop_loss_event
    
    # Inicializar los módulos del workflow que tienen estado
    workflow._data_processing.initialize_data_processing()
    workflow._limit_checks.initialize_limit_checks()

    # Inicializar TA (que a su vez inicializa sus componentes internos)
    ta.initialize()

    # Inicializar el logger de señales si está configurado
    if getattr(config, 'LOG_SIGNAL_OUTPUT', False):
        try:
            from core.logging import signal_logger
            signal_logger.initialize_logger()
        except Exception as e:
            memory_logger.log(f"ERROR: Inicializando signal_logger: {e}", level="ERROR")

    memory_logger.log("Event Processor: Orquestador inicializado.", level="INFO")


# --- Procesamiento Principal de Evento (Orquestador) ---
def process_event(intermediate_ticks_info: list, final_price_info: dict):
    """
    Orquesta el flujo de trabajo para procesar un único evento de precio.
    """
    # Evitar procesamiento si el stop loss global ya se activó
    if workflow.limit_checks.has_global_stop_loss_triggered():
        return

    if not final_price_info:
        memory_logger.log("Evento de precio final vacío, saltando tick.", level="WARN")
        return

    # 1. Validar datos de entrada
    current_timestamp = final_price_info.get("timestamp")
    current_price = utils.safe_float_convert(final_price_info.get("price"), default=np.nan)

    if not isinstance(current_timestamp, (datetime.datetime, pd.Timestamp)) or pd.isna(current_price) or current_price <= 0:
        memory_logger.log(f"Timestamp/Precio inválido. Saltando. TS:{current_timestamp}, P:{current_price}", level="WARN")
        return

    try:
        # 2. Comprobar Triggers Condicionales
        workflow.triggers.check_conditional_triggers(current_price, current_timestamp)

        # 3. Procesar datos y generar señal
        signal_data = workflow.data_processing.process_tick_and_generate_signal(current_timestamp, current_price)

        # 4. Interacción con el Position Manager
        workflow.pm_interaction.update_pm_with_tick(current_price, current_timestamp)
        workflow.pm_interaction.send_signal_to_pm(signal_data, current_price, current_timestamp, _operation_mode)

        # 5. Comprobar Límites de Tendencia y Sesión
        workflow.limit_checks.check_trend_limits(current_price, current_timestamp, _operation_mode)
        workflow.limit_checks.check_session_limits(current_price, current_timestamp, _operation_mode, _global_stop_loss_event)

        # 6. (Opcional) Imprimir estado en consola
        _print_tick_status_to_console(signal_data, current_timestamp, current_price)

    except workflow.limit_checks.GlobalStopLossException as e:
        # La excepción se lanza desde _limit_checks para detener el bot.
        # Aquí solo la registramos y la dejamos propagar si es necesario.
        memory_logger.log(f"GlobalStopLossException capturada en Event Processor: {e}", level="ERROR")
        # En un entorno real, no se relanza para que el hilo no muera.
        # En backtest, el runner la capturará para detener la simulación.
    except Exception as e:
        memory_logger.log(f"ERROR INESPERADO en el flujo de trabajo de process_event: {e}", level="ERROR")
        memory_logger.log(f"Traceback: {traceback.format_exc()}", level="ERROR")


def _print_tick_status_to_console(signal_data: Optional[Dict], current_timestamp: datetime.datetime, current_price: float):
    """
    Función de ayuda para imprimir el estado del tick en la consola si está habilitado.
    Esta es una responsabilidad de "presentación" que se queda en el orquestador.
    """
    # La TUI ahora gestiona la visualización, por lo que esta función podría ser eliminada
    # o simplificada en el futuro. Por ahora, se mantiene la lógica original.
    if _operation_mode.startswith(('live', 'automatic')) and getattr(config, 'PRINT_TICK_LIVE_STATUS', False):
        try:
            # Reutiliza el TA data del signal_data si está disponible
            processed_data_for_print = {
                'ema': signal_data.get('ema'),
                'weighted_increment': signal_data.get('weighted_increment'),
                'weighted_decrement': signal_data.get('weighted_decrement'),
                'inc_price_change_pct': signal_data.get('inc_price_change_pct'),
                'dec_price_change_pct': signal_data.get('dec_price_change_pct'),
            }

            ts_str_fmt = utils.format_datetime(current_timestamp)
            price_prec = getattr(config, 'PRICE_PRECISION', 4)
            current_price_fmt_str = f"{current_price:.{price_prec}f}"
            
            hdr = "="*25 + f" TICK STATUS @ {ts_str_fmt} " + "="*25
            print("\n" + hdr)
            print(f"  Precio Actual : {current_price_fmt_str:<15}")
            print("  Indicadores TA:")
            if processed_data_for_print and signal_data:
                 ema_val = processed_data_for_print.get('ema')
                 winc_val = processed_data_for_print.get('weighted_increment')
                 wdec_val = processed_data_for_print.get('weighted_decrement')
                 inc_pct_val = signal_data.get('inc_price_change_pct') # Usar el formateado de la señal
                 dec_pct_val = signal_data.get('dec_price_change_pct')

                 print(f"    EMA       : {ema_val:<15} W.Inc : {winc_val:<8} W.Dec : {wdec_val:<8}")
                 print(f"    Inc %     : {inc_pct_val:<15} Dec % : {dec_pct_val:<8}")
            else:
                print("    (No disponibles)")
                
            print("  Señal Generada:")
            if signal_data:
                print(f"    Signal: {signal_data.get('signal', 'N/A'):<15} Reason: {signal_data.get('signal_reason', 'N/A')}")
            else:
                print("    (No generada)")
                
            print("  Estado Posiciones:")
            if getattr(config, 'POSITION_MANAGEMENT_ENABLED', False) and position_manager and position_manager.is_initialized():
                summary = position_manager.get_position_summary()
                if summary and 'error' not in summary:
                    manual_status = summary.get('manual_mode_status', {})
                    limit_str = manual_status.get('limit') or 'inf'
                    
                    print(f"    Modo Op: {summary.get('operation_mode', 'N/A')}")
                    if summary.get('operation_mode') == 'live_interactive':
                        print(f"    Modo Manual: {manual_status.get('mode', 'N/A')} (Trades: {manual_status.get('executed', 0)}/{limit_str})")
                    
                    print(f"    Longs: {summary.get('open_long_positions_count', 0)}/{summary.get('max_logical_positions', 0)} | Shorts: {summary.get('open_short_positions_count', 0)}/{summary.get('max_logical_positions', 0)}")
                    print(f"    PNL Sesión: {summary.get('total_realized_pnl_session', 0.0):+.4f} USDT")

                elif summary and 'error' in summary:
                    print(f"    Error resumen PM: {summary.get('error', 'N/A')}")
                else:
                    print(f"    Error resumen PM (Respuesta inválida).")
            else:
                print("    (Gestión desactivada o PM no inicializado)")
            print("=" * len(hdr))
        except Exception as e_print:
            print(f"ERROR [Print Tick Status]: {e_print}")
            traceback.print_exc()