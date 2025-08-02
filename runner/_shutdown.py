"""
Módulo responsable de la secuencia de apagado limpio de una sesión de trading.

v6.0 (Refactor de Configuración):
- Adaptado para leer la configuración desde la nueva estructura de diccionarios.

v4.0 (Arquitectura de Controladores):
- La responsabilidad de este módulo se ha redefinido. Ahora se centra en el
  apagado de los componentes de una sesión específica, no de todo el bot.
- La lógica es invocada por el BotController cuando una sesión termina.
- Recibe la instancia del SessionManager para orquestar el apagado.
"""
from typing import Any, Dict

def shutdown_session_backend(
    session_manager: Any,
    final_summary: Dict[str, Any],
    # --- Módulos de dependencia inyectados (para soporte) ---
    config_module: Any,
    open_snapshot_logger_module: Any
):
    """
    Ejecuta la secuencia de limpieza y apagado para una sesión de trading.
    
    Args:
        session_manager: La instancia del SessionManager que está finalizando.
        final_summary: Un diccionario para almacenar el resumen final.
        config_module: El módulo de configuración.
        open_snapshot_logger_module: El logger para el snapshot final.
    """
    print("\n--- Limpieza Final de la Sesión de Trading (Backend) ---")
    
    if not session_manager:
        print("Advertencia: No se proporcionó un SessionManager para el apagado.")
        return

    # 1. Detener el ticker de precios de la sesión
    # La responsabilidad de detener el ticker ahora es del SessionManager.
    if session_manager.is_running():
        print("Deteniendo el Ticker de precios de la sesión...")
        session_manager.stop()
        print("Ticker detenido.")

    # 2. Obtener y guardar el resumen final de la sesión
    # --- INICIO DE LA MODIFICACIÓN (Adaptación a Nueva Estructura) ---
    # La variable 'POSITION_MANAGEMENT_ENABLED' ya no existe. El sistema ahora siempre
    # opera con la gestión de posiciones activada. Se puede simplificar la condición a True.
    # --- (COMENTADO) ---
    # if getattr(config_module, 'POSITION_MANAGEMENT_ENABLED', False):
    # --- (CORREGIDO) ---
    if True: # Se asume que la gestión de posiciones está siempre activa.
        print("Obteniendo resumen final para logging...")
        summary = session_manager.get_session_summary()
        
        if summary and not summary.get('error'):
            # --- INICIO DE LA MODIFICACIÓN --- (Mantenida desde tu código original)
            # Aseguramos que el diccionario que recibimos se limpie y se popule.
            # Esto es útil si una capa superior necesita acceder a este resumen.
            final_summary.clear()
            final_summary.update(summary)
            # --- FIN DE LA MODIFICACIÓN --- (Mantenida desde tu código original)

            # Loguear el snapshot final de posiciones abiertas si está configurado
            # --- (COMENTADO) ---
            # if open_snapshot_logger_module and getattr(config_module, 'POSITION_LOG_OPEN_SNAPSHOT', False):
            # --- (CORREGIDO) ---
            if open_snapshot_logger_module and config_module.BOT_CONFIG["LOGGING"]["LOG_OPEN_SNAPSHOT"]:
                # La función de log ahora usa el 'summary' que acabamos de obtener.
                open_snapshot_logger_module.log_open_positions_snapshot(summary)
            
            print("Resumen final de la sesión obtenido y logueado.")
        else:
            final_summary['error'] = 'No se pudo obtener el resumen final de la sesión.'
            error_msg = summary.get('error', 'Error desconocido') if summary else 'N/A'
            print(f"No se pudo obtener el resumen final: {error_msg}")
    
    # --- FIN DE LA MODIFICACIÓN ---
    
    print("Secuencia de apagado de la sesión (Backend) completada.")