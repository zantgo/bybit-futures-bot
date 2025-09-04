"""
Módulo responsable de la secuencia de apagado limpio de una sesión de trading.
"""
import datetime
from typing import Any, Dict
import os

# --- INICIO DE LA MODIFICACIÓN: La importación se mueve a un nivel local si es necesaria ---
# (Se elimina 'from core.logging import memory_logger' de aquí para evitar dependencias globales)
# --- FIN DE LA MODIFICACIÓN ---

def _write_session_summary_to_file(
    final_summary: Dict[str, Any],
    config_module: Any,
    # --- INICIO DE LA MODIFICACIÓN: Se añade el parámetro del logger ---
    memory_logger_module: Any
    # --- FIN DE LA MODIFICACIÓN ---
):
    """
    Formatea el resumen final de la sesión y lo guarda en un archivo de texto.
    """
    from core.strategy.pm import api as pm_api

    if not final_summary or final_summary.get('error'):
        # --- INICIO DE LA MODIFICACIÓN: Reemplazar print con logger ---
        # print("No se generará archivo de resumen debido a un error en los datos.")
        if memory_logger_module:
            memory_logger_module.log("No se generará archivo de resumen debido a un error en los datos.", "WARN")
        # --- FIN DE LA MODIFICACIÓN ---
        return

    try:
        now = datetime.datetime.now(datetime.timezone.utc)
        filename = f"session_summary_{now.strftime('%Y%m%d_%H%M%S')}.txt"
        filepath = os.path.join(config_module.RESULTS_DIR, filename)

        content = []
        
        content.append("="*80)
        content.append("RESUMEN FINAL DE LA SESIÓN DE TRADING".center(80))
        content.append(f"Finalizada el: {now.strftime('%Y-%m-%d %H:%M:%S UTC')}".center(80))
        content.append("="*80)

        content.append("\n--- Configuración del Bot ---")
        bot_cfg = config_module.BOT_CONFIG
        modo_trading_str = "Paper Trading" if bot_cfg["PAPER_TRADING_MODE"] else "Live Trading"
        
        bot_params_to_show = {
            "Exchange": bot_cfg["EXCHANGE_NAME"].upper(),
            "Símbolo Ticker": bot_cfg["TICKER"]["SYMBOL"],
            "Modo de Trading": modo_trading_str,
            "Modo Testnet": "ACTIVADO" if bot_cfg["UNIVERSAL_TESTNET_MODE"] else "DESACTIVADO"
        }
        max_bot_key_len = max(len(k) for k in bot_params_to_show.keys())
        for key, value in bot_params_to_show.items():
            content.append(f"  {key:<{max_bot_key_len}} : {value}")
        
        start_time_obj = pm_api.get_session_start_time()
        duration_str = "N/A"
        if start_time_obj:
            duration = now - start_time_obj
            duration_str = str(datetime.timedelta(seconds=int(duration.total_seconds())))

        content.append(f"\nDuración Total de la Sesión: {duration_str}")

        content.append("\n--- Estado Final de las Operaciones ---")
        sides = ['long', 'short']
        for side in sides:
            op_info = final_summary.get('operations_info', {}).get(side, {})
            balance_info = final_summary.get('logical_balances', {}).get(side, {})
            pnl = final_summary.get(f'operation_{side}_pnl', 0.0)
            roi = final_summary.get(f'operation_{side}_roi', 0.0)
            ganancias_netas = pnl - final_summary.get(f'comisiones_totales_usdt_{side}', 0.0)
            capital_usado = balance_info.get('used_margin', 0.0)
            capital_operativo = balance_info.get('operational_margin', 0.0)
            pos_count = final_summary.get(f'open_{side}_positions_count', 0)
            
            content.append(f"\n  Operación {side.upper()}:")
            content.append(f"    - Estado Final          : {op_info.get('estado', 'DETENIDA').upper()}")
            content.append(f"    - Posiciones Abiertas   : {pos_count}")
            content.append(f"    - Capital (Usado/Total) : ${capital_usado:.2f} / ${capital_operativo:.2f}")
            content.append(f"    - Ganancias Netas       : ${ganancias_netas:+.4f}")
            content.append(f"    - PNL (Realizado+No R.) : {pnl:+.4f} USDT")
            content.append(f"    - ROI                   : {roi:+.2f}%")
        
        content.append("\n" + "="*80)
        content.append("Parámetros Clave de la Sesión".center(80))
        content.append("="*80)
        session_cfg = config_module.SESSION_CONFIG
        
        params_to_show = {
            "Intervalo Ticker (s)": session_cfg['TICKER_INTERVAL_SECONDS'],
            "Período EMA": f"{session_cfg['TA']['EMA_WINDOW']}" if session_cfg['TA']['ENABLED'] else "Desactivado",
            "Margen Compra (%)": f"{session_cfg['SIGNAL']['PRICE_CHANGE_BUY_PERCENTAGE']}" if session_cfg['SIGNAL']['ENABLED'] else "Desactivado",
            "Margen Venta (%)": f"{session_cfg['SIGNAL']['PRICE_CHANGE_SELL_PERCENTAGE']}" if session_cfg['SIGNAL']['ENABLED'] else "Desactivado",
            "Comisión (%)": f"{session_cfg['PROFIT']['COMMISSION_RATE'] * 100:.3f}",
            "Reinvertir Ganancias (%)": session_cfg['PROFIT']['REINVEST_PROFIT_PCT'],
        }
        max_key_len = max(len(k) for k in params_to_show.keys())
        for key, value in params_to_show.items():
            content.append(f"  {key:<{max_key_len}} : {value}")

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write('\n'.join(content))
        
        print(f"\nResumen de la sesión guardado en: {filepath}")
        if memory_logger_module:
            memory_logger_module.log(f"Resumen de la sesión guardado en: {filepath}", "INFO")

    except Exception as e:
        error_msg = f"\nERROR: No se pudo escribir el archivo de resumen de sesión: {e}"
        print(error_msg)
        if memory_logger_module:
            memory_logger_module.log(error_msg, "ERROR")


def shutdown_session_backend(
    session_manager: Any,
    final_summary: Dict[str, Any],
    config_module: Any,
    open_snapshot_logger_module: Any,
    # --- INICIO DE LA MODIFICACIÓN: Se añade el parámetro del logger ---
    memory_logger_module: Any
    # --- FIN DE LA MODIFICACIÓN ---
):
    """
    Ejecuta la secuencia de limpieza y apagado para una sesión de trading.
    """
    # --- INICIO DE LA MODIFICACIÓN: Reemplazar print con logger ---
    # print("\n--- Limpieza Final de la Sesión de Trading (Backend) ---")
    if memory_logger_module:
        memory_logger_module.log("--- Limpieza Final de la Sesión de Trading (Backend) ---", "INFO")
    
    if not session_manager:
        # print("Advertencia: No se proporcionó un SessionManager para el apagado.")
        if memory_logger_module:
            memory_logger_module.log("Advertencia: No se proporcionó un SessionManager para el apagado.", "WARN")
        return

    if session_manager.is_running():
        # print("Deteniendo el Ticker de precios de la sesión...")
        if memory_logger_module:
            memory_logger_module.log("Deteniendo el Ticker de precios de la sesión...", "INFO")
        session_manager.stop()
        # print("Ticker detenido.")
        if memory_logger_module:
            memory_logger_module.log("Ticker detenido.", "INFO")

    # print("Obteniendo resumen final para logging...")
    if memory_logger_module:
        memory_logger_module.log("Obteniendo resumen final para logging...", "INFO")
    summary = session_manager.get_session_summary()
    
    if summary and not summary.get('error'):
        final_summary.clear()
        final_summary.update(summary)
  
        if open_snapshot_logger_module and config_module.BOT_CONFIG["LOGGING"]["LOG_OPEN_SNAPSHOT"]:
            open_snapshot_logger_module.log_open_positions_snapshot(summary)
        
        # print("Resumen final de la sesión obtenido y logueado.")
        if memory_logger_module:
            memory_logger_module.log("Resumen final de la sesión obtenido y logueado.", "INFO")
        
        _write_session_summary_to_file(final_summary, config_module, memory_logger_module)

    else:
        final_summary['error'] = 'No se pudo obtener el resumen final de la sesión.'
        error_msg = summary.get('error', 'Error desconocido') if summary else 'N/A'
        # print(f"No se pudo obtener el resumen final: {error_msg}")
        if memory_logger_module:
            memory_logger_module.log(f"No se pudo obtener el resumen final: {error_msg}", "ERROR")
    
    # print("Secuencia de apagado de la sesión (Backend) completada.")
    if memory_logger_module:
        memory_logger_module.log("Secuencia de apagado de la sesión (Backend) completada.", "INFO")
    # --- FIN DE LA MODIFICACIÓN ---