# runner/_shutdown.py

"""
Módulo responsable de la secuencia de apagado limpio del bot.

Su única responsabilidad es detener hilos, guardar estados finales y
liberar recursos de manera ordenada.
"""
from typing import Any, Dict

def perform_shutdown(
    final_summary: Dict[str, Any],
    bot_started: bool,
    # Módulos de dependencia inyectados
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
        # Comprobación segura del hilo del ticker
        is_alive = False
        if hasattr(connection_ticker_module, '_ticker_thread'):
            thread = connection_ticker_module._ticker_thread
            if thread and hasattr(thread, 'is_alive') and callable(thread.is_alive):
                is_alive = thread.is_alive()
        
        if is_alive:
            print("Deteniendo el Ticker de precios...")
            connection_ticker_module.stop_ticker_thread()
            print("Ticker detenido.")

    # 2. Obtener y guardar el resumen final del Position Manager
    if bot_started and getattr(config_module, 'POSITION_MANAGEMENT_ENABLED', False):
        print("Obteniendo resumen final del Position Manager...")
        summary = position_manager_module.api.get_position_summary()
        
        if summary and not summary.get('error'):
            final_summary.clear()
            final_summary.update(summary)

            # Loguear la instantánea final de posiciones abiertas
            if open_snapshot_logger_module and getattr(config_module, 'POSITION_LOG_OPEN_SNAPSHOT', False):
                open_snapshot_logger_module.log_open_positions_snapshot(summary)
            
            print("Resumen final obtenido.")
        else:
            final_summary['error'] = 'No se pudo obtener el resumen final del PM.'
            print("No se pudo obtener el resumen final del PM.")
    
    print("Secuencia de apagado completada.")