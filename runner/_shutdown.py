"""
Módulo responsable de la secuencia de apagado limpio del bot.

Su única responsabilidad es detener hilos, guardar estados finales y
liberar recursos de manera ordenada.
"""
from typing import Any, Dict

def perform_shutdown(
    final_summary: Dict[str, Any],
    bot_started: bool,
    # --- Módulos de dependencia inyectados ---
    config_module: Any,
    connection_ticker_module: Any,
    position_manager_module: Any,
    open_snapshot_logger_module: Any
):
    """
    Ejecuta la secuencia de limpieza y apagado del bot.
    """
    print("\n--- Limpieza Final del Runner ---")

    # 1. Detener el ticker de precios si estaba corriendo
    if bot_started and connection_ticker_module:
        print("Deteniendo el Ticker de precios...")
        # La lógica de si está vivo o no está encapsulada en la función stop
        connection_ticker_module.stop_ticker_thread()
        print("Ticker detenido.")

    # 2. Obtener y guardar el resumen final del Position Manager
    if bot_started and getattr(config_module, 'POSITION_MANAGEMENT_ENABLED', False):
        if not position_manager_module or not hasattr(position_manager_module, 'is_initialized') or not position_manager_module.is_initialized():
            print("PM no inicializado, no se puede obtener resumen final.")
        else:
            print("Obteniendo resumen final del Position Manager...")
            summary = position_manager_module.get_position_summary()
            
            if summary and not summary.get('error'):
                final_summary.clear()
                final_summary.update(summary)

                if open_snapshot_logger_module and getattr(config_module, 'POSITION_LOG_OPEN_SNAPSHOT', False):
                    open_snapshot_logger_module.log_open_positions_snapshot(summary)
                
                print("Resumen final obtenido.")
            else:
                final_summary['error'] = 'No se pudo obtener el resumen final del PM.'
                print(f"No se pudo obtener el resumen final del PM: {summary.get('error', 'Error desconocido')}")
    
    print("Secuencia de apagado completada.")