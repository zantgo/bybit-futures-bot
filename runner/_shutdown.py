# ./runner/_shutdown.py

"""
Módulo responsable de la secuencia de apagado limpio de una sesión de trading.
"""
import datetime
from typing import Any, Dict
import os

# --- INICIO DE LA MODIFICACIÓN: Nueva función para escribir el resumen ---

def _write_session_summary_to_file(
    final_summary: Dict[str, Any],
    config_module: Any
):
    """
    Formatea el resumen final de la sesión y lo guarda en un archivo de texto.
    """
    if not final_summary or final_summary.get('error'):
        print("No se generará archivo de resumen debido a un error en los datos.")
        return

    try:
        # Crear un nombre de archivo único con timestamp
        now = datetime.datetime.now(datetime.timezone.utc)
        filename = f"session_summary_{now.strftime('%Y%m%d_%H%M%S')}.txt"
        filepath = os.path.join(config_module.RESULTS_DIR, filename)

        # Preparar el contenido del archivo
        content = []
        
        # --- Cabecera ---
        content.append("="*80)
        content.append("RESUMEN FINAL DE LA SESIÓN DE TRADING".center(80))
        content.append(f"Finalizada el: {now.strftime('%Y-%m-%d %H:%M:%S UTC')}".center(80))
        content.append("="*80)

        # --- Rendimiento General ---
        content.append("\n--- Rendimiento General ---")
        realized_pnl = final_summary.get('total_session_pnl', 0.0)
        initial_capital = final_summary.get('total_session_initial_capital', 0.0)
        final_roi = (realized_pnl / initial_capital) * 100 if initial_capital > 0 else 0.0
        
        start_time_obj = final_summary.get('session_start_time')
        duration_str = "N/A"
        if start_time_obj:
            duration = now - start_time_obj
            duration_str = str(datetime.timedelta(seconds=int(duration.total_seconds())))

        content.append(f"  PNL Realizado Total : {realized_pnl:+.4f} USDT")
        content.append(f"  ROI Final (Realizado) : {final_roi:+.2f}%")
        content.append(f"  Duración Total      : {duration_str}")

        # --- Estado Final de las Operaciones ---
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
            max_pos = op_info.get('max_posiciones_logicas', 'N/A')
            
            content.append(f"\n  Operación {side.upper()}:")
            content.append(f"    - Estado Final          : {op_info.get('estado', 'DETENIDA').upper()}")
            content.append(f"    - Posiciones Abiertas   : {pos_count} / {max_pos}")
            content.append(f"    - Capital (Usado/Total) : ${capital_usado:.2f} / ${capital_operativo:.2f}")
            content.append(f"    - Ganancias Netas       : ${ganancias_netas:+.4f}")
            content.append(f"    - PNL (Realizado+No R.) : {pnl:+.4f} USDT")
            content.append(f"    - ROI                   : {roi:+.2f}%")
        
        # --- Parámetros de la Sesión ---
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
            "SL por ROI (%)": f"-{session_cfg['SESSION_LIMITS']['ROI_SL']['PERCENTAGE']}" if session_cfg['SESSION_LIMITS']['ROI_SL']['ENABLED'] else "Desactivado",
            "TP por ROI (%)": f"+{session_cfg['SESSION_LIMITS']['ROI_TP']['PERCENTAGE']}" if session_cfg['SESSION_LIMITS']['ROI_TP']['ENABLED'] else "Desactivado",
        }
        max_key_len = max(len(k) for k in params_to_show.keys())
        for key, value in params_to_show.items():
            content.append(f"  {key:<{max_key_len}} : {value}")

        # --- Escribir al archivo ---
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write('\n'.join(content))
        
        print(f"\nResumen de la sesión guardado en: {filepath}")

    except Exception as e:
        print(f"\nERROR: No se pudo escribir el archivo de resumen de sesión: {e}")

# --- FIN DE LA MODIFICACIÓN ---


def shutdown_session_backend(
    session_manager: Any,
    final_summary: Dict[str, Any],
    config_module: Any,
    open_snapshot_logger_module: Any
):
    """
    Ejecuta la secuencia de limpieza y apagado para una sesión de trading.
    """
    print("\n--- Limpieza Final de la Sesión de Trading (Backend) ---")
    
    if not session_manager:
        print("Advertencia: No se proporcionó un SessionManager para el apagado.")
        return

    if session_manager.is_running():
        print("Deteniendo el Ticker de precios de la sesión...")
        session_manager.stop()
        print("Ticker detenido.")

    print("Obteniendo resumen final para logging...")
    summary = session_manager.get_session_summary()
    
    if summary and not summary.get('error'):
        final_summary.clear()
        final_summary.update(summary)
  
        if open_snapshot_logger_module and config_module.BOT_CONFIG["LOGGING"]["LOG_OPEN_SNAPSHOT"]:
            open_snapshot_logger_module.log_open_positions_snapshot(summary)
        
        print("Resumen final de la sesión obtenido y logueado.")
        
        # --- INICIO DE LA MODIFICACIÓN: Llamar a la nueva función ---
        _write_session_summary_to_file(final_summary, config_module)
        # --- FIN DE LA MODIFICACIÓN ---

    else:
        final_summary['error'] = 'No se pudo obtener el resumen final de la sesión.'
        error_msg = summary.get('error', 'Error desconocido') if summary else 'N/A'
        print(f"No se pudo obtener el resumen final: {error_msg}")
    
    print("Secuencia de apagado de la sesión (Backend) completada.")