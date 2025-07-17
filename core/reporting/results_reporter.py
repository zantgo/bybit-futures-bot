# =============== INICIO ARCHIVO: core/reporting/results_reporter.py (v14 - Reporte con SL Individual y TS) ===============
"""
Módulo para generar un reporte final en formato TXT con la configuración
y los resultados de la ejecución (backtest/live).

v14:
- Actualizado para mostrar los nuevos parámetros de configuración:
  Stop Loss Individual y Trailing Stop.
- Eliminadas las referencias a Take Profit fijo y SL físico.
- Modificado el resumen de posiciones abiertas para mostrar el SL y el estado del TS.
v13:
- Adaptado para mostrar información específica del modo automático.
"""
import json
import os
import traceback
import pandas as pd
import numpy as np
import datetime
from typing import Optional, Dict, Any

try:
    import sys
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if project_root not in sys.path: sys.path.insert(0, project_root)
    import config as global_config_for_load_closed
    from core import utils as global_utils_for_load_closed
    try:
        from core.strategy import balance_manager
    except ImportError:
        print("WARN [Results Reporter Import]: Módulo balance_manager no encontrado. ROI puede usar fallback.")
        balance_manager = None
except ImportError as e:
    print(f"ERROR [Results Reporter Import]: No se pudo importar core.config o core.utils: {e}")
    global_config_for_load_closed = type('obj', (object,), {
        'POSITION_MANAGEMENT_ENABLED': False, 'POSITION_CLOSED_LOG_FILE': 'logs/closed_positions.jsonl',
    })()
    global_utils_for_load_closed = type('obj', (object,), {
        'format_datetime': lambda dt, fmt=None: str(dt),
        'safe_float_convert': lambda v, default=0.0: float(v) if v is not None else default
    })()
    balance_manager = None
except Exception as e_imp:
     print(f"ERROR inesperado importando en results_reporter: {e_imp}")
     global_config_for_load_closed = type('obj', (object,), {})()
     global_utils_for_load_closed = None
     balance_manager = None


def _safe_division(numerator, denominator, default=0.0):
    try:
        num = float(numerator)
        den = float(denominator)
        if den is None or not np.isfinite(den) or abs(den) < 1e-12:
            return default
        result = num / den
        return result if np.isfinite(result) else default
    except (TypeError, ValueError, ZeroDivisionError):
        return default

def _load_closed_positions(filepath: str, utils_module: Optional[Any]) -> pd.DataFrame:
    data = []
    required_cols = ['side', 'pnl_net_usdt']
    print(f"[Results Reporter] Cargando posiciones cerradas desde: {os.path.basename(filepath)}")
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line_number, line in enumerate(f):
                try:
                    if not line.strip(): continue
                    closed_pos = json.loads(line)
                    if all(col in closed_pos for col in required_cols):
                         pnl_value = closed_pos.get('pnl_net_usdt')
                         closed_pos['pnl_net_usdt_float'] = utils_module.safe_float_convert(pnl_value, default=0.0) if utils_module else 0.0
                         data.append(closed_pos)
                except json.JSONDecodeError: pass
                except Exception: pass

        if not data:
            print("  Info: No se encontraron datos válidos de posiciones cerradas en el log.")
            return pd.DataFrame()

        df = pd.DataFrame(data)
        print(f"  Log de Posiciones Cerradas procesado: {len(df)} trades.")
        return df

    except FileNotFoundError:
        print(f"  Info: Archivo de posiciones cerradas no encontrado: {os.path.basename(filepath)}")
        return pd.DataFrame()
    except Exception as e:
        print(f"  ERROR cargando log de posiciones cerradas: {e}")
        traceback.print_exc()
        return pd.DataFrame()

def generate_backtest_report_from_summary(
    pm_summary: Dict[str, Any],
    operation_mode: str,
    config_module: Optional[Any],
    utils_module: Optional[Any]
):
    global balance_manager

    print("\n--- Generando Reporte Final de Sesión ---")
    if not config_module or not utils_module:
        print("ERROR: Módulos config o utils no proporcionados a reporter."); return
    if not pm_summary or 'error' in pm_summary:
        print(f"ERROR: Resumen de Position Manager inválido: {pm_summary.get('error', 'N/A')}"); return

    report_lines = []
    now = utils_module.format_datetime(datetime.datetime.now())
    pos_enabled = pm_summary.get('management_enabled', False)

    report_lines.append("=" * 80); report_lines.append(f"Reporte de Ejecución - Bot v14".center(80));
    report_lines.append(f"Generado: {now}".center(80)); report_lines.append(f"Modo: {operation_mode.upper()}".center(80));
    report_lines.append("=" * 80); report_lines.append("")

    report_lines.append("--- Configuración de la Sesión ".ljust(79, "-"))
    report_lines.append(f"  Símbolo: {getattr(config_module, 'TICKER_SYMBOL', 'N/A')}")
    report_lines.append(f"  Gestión de Posiciones: {'Activada' if pos_enabled else 'Desactivada'}")

    initial_capital_report = pm_summary.get('initial_total_capital', 0.0)

    if pos_enabled:
        trading_mode_session = pm_summary.get('trading_mode', getattr(config_module, 'POSITION_TRADING_MODE', 'N/A'))

        report_lines.append(f"  Modo Trading (final): {trading_mode_session}")
        report_lines.append(f"  Capital Inicial Asignado: {initial_capital_report:.2f} USDT")
        report_lines.append(f"  Apalancamiento: {pm_summary.get('leverage', 0.0):.1f}x")
        report_lines.append(f"  Max Pos Lógicas (Final): {pm_summary.get('max_logical_positions', 0)} (por lado)")

        # <<< INICIO DE CAMBIOS >>>
        report_lines.append(f"  Stop Loss Individual (%): {getattr(config_module, 'POSITION_INDIVIDUAL_STOP_LOSS_PCT', 0.0):.2f}%")
        report_lines.append(f"  Trailing Stop Activación (%): {getattr(config_module, 'TRAILING_STOP_ACTIVATION_PCT', 0.0):.2f}%")
        report_lines.append(f"  Trailing Stop Distancia (%): {getattr(config_module, 'TRAILING_STOP_DISTANCE_PCT', 0.0):.2f}%")
        # <<< FIN DE CAMBIOS >>>

        report_lines.append(f"  Comisión %: {getattr(config_module, 'POSITION_COMMISSION_RATE', 0.0)*100:.3f}%")
        report_lines.append(f"  Reinvertir PNL Operacional %: {getattr(config_module, 'POSITION_REINVEST_PROFIT_PCT', 0.0):.2f}%")

        if "automatic" in operation_mode.lower():
            report_lines.append("\n  --- Parámetros del Modo Automático ---")
            report_lines.append(f"    Intervalo Señal UT Bot: {getattr(config_module, 'UT_BOT_SIGNAL_INTERVAL_SECONDS', 'N/A')} seg")
            report_lines.append(f"    UT Bot Key Value:       {getattr(config_module, 'UT_BOT_KEY_VALUE', 'N/A')}")
            report_lines.append(f"    UT Bot ATR Period:      {getattr(config_module, 'UT_BOT_ATR_PERIOD', 'N/A')}")
            report_lines.append(f"    Flip Abre Posiciones:   {getattr(config_module, 'AUTOMATIC_FLIP_OPENS_NEW_POSITIONS', 'N/A')}")
            report_lines.append(f"    Cooldown Post-SL:       {getattr(config_module, 'AUTOMATIC_SL_COOLDOWN_SECONDS', 'N/A')} seg")
            # La línea de SL Físico se elimina
    report_lines.append("")

    total_closed = 0; total_winners = 0; total_losers = 0; total_pnl_net = 0.0
    total_pnl_winners = 0.0; total_pnl_losers = 0.0; long_closed = 0; long_winners = 0
    long_pnl_net = 0.0; short_closed = 0; short_winners = 0; short_pnl_net = 0.0
    profit_factor = 0.0; win_rate = 0.0; avg_win = 0.0; avg_loss = 0.0
    if pos_enabled:
        report_lines.append("--- Resumen Trades Cerrados ".ljust(79, "-"))
        closed_log_path = getattr(config_module, 'POSITION_CLOSED_LOG_FILE', 'logs/closed_positions.jsonl')
        df_closed = _load_closed_positions(closed_log_path, utils_module)
        if not df_closed.empty and 'pnl_net_usdt_float' in df_closed.columns:
            total_closed = len(df_closed)
            df_closed['is_winner'] = df_closed['pnl_net_usdt_float'] > 1e-9
            total_winners = int(df_closed['is_winner'].sum()); total_losers = total_closed - total_winners
            total_pnl_net = df_closed['pnl_net_usdt_float'].sum()
            total_pnl_winners = df_closed.loc[df_closed['is_winner'], 'pnl_net_usdt_float'].sum()
            total_pnl_losers = df_closed.loc[~df_closed['is_winner'], 'pnl_net_usdt_float'].sum()
            long_trades = df_closed[df_closed['side'] == 'long']; short_trades = df_closed[df_closed['side'] == 'short']
            long_closed = len(long_trades); short_closed = len(short_trades)
            long_winners = int(long_trades['is_winner'].sum()); short_winners = int(short_trades['is_winner'].sum())
            long_pnl_net = long_trades['pnl_net_usdt_float'].sum(); short_pnl_net = short_trades['pnl_net_usdt_float'].sum()
            win_rate = _safe_division(total_winners, total_closed) * 100
            avg_win = _safe_division(total_pnl_winners, total_winners)
            avg_loss = _safe_division(total_pnl_losers, total_losers)
            profit_factor = _safe_division(abs(total_pnl_winners), abs(total_pnl_losers), default=float('inf'))
            report_lines.append(f"  Total Trades Cerrados: {total_closed} (Long: {long_closed}, Short: {short_closed})")
            report_lines.append(f"  Trades Ganadores:      {total_winners} ({win_rate:.2f}%) (Long: {long_winners}, Short: {short_winners})")
            report_lines.append(f"  Trades Perdedores:     {total_losers}")
            report_lines.append(f"  PNL Neto Total:        {total_pnl_net:+.4f} USDT (Long: {long_pnl_net:+.4f}, Short: {short_pnl_net:+.4f})")
            report_lines.append(f"  Ganancia Promedio:     {avg_win:+.4f} USDT")
            report_lines.append(f"  Pérdida Promedio:      {avg_loss:+.4f} USDT")
            report_lines.append(f"  Profit Factor:         {'inf' if profit_factor == float('inf') else f'{profit_factor:.2f}'}")
        else:
            report_lines.append("  No se cerraron trades durante esta sesión o no se pudo leer el log.")
        report_lines.append("")

    report_lines.append("--- Estado Final ".ljust(79, "-"))
    if pos_enabled and pm_summary:
        op_long_final = pm_summary.get('bm_operational_long_margin', 0.0)
        op_short_final = pm_summary.get('bm_operational_short_margin', 0.0)
        profit_balance_final = pm_summary.get('bm_profit_balance', 0.0)

        pnl_realized_report = pm_summary.get('total_realized_pnl_long', 0.0) + pm_summary.get('total_realized_pnl_short', 0.0)
        final_equity_logical = initial_capital_report + pnl_realized_report
        roi_pct = _safe_division(pnl_realized_report, initial_capital_report) * 100 if initial_capital_report > 1e-9 else float('inf')

        report_lines.append(f"  Capital Inicial Total Operativo:    {initial_capital_report:,.2f} USDT")
        report_lines.append(f"  Capital Final Total (Equity Lóg.):  {final_equity_logical:,.4f} USDT")
        report_lines.append(f"  Retorno Sobre Capital Inicial (%):  {roi_pct:+.2f}%")
        report_lines.append(f"\n  Balance Operativo Final Long:         {op_long_final:,.4f} USDT")
        report_lines.append(f"  Balance Operativo Final Short:        {op_short_final:,.4f} USDT")
        report_lines.append(f"  Balance Cuenta Profit Final:          {profit_balance_final:,.4f} USDT")

        open_long_count = pm_summary.get('open_long_positions_count', 0)
        open_short_count = pm_summary.get('open_short_positions_count', 0)
        open_long_details = pm_summary.get('open_long_positions', [])
        open_short_details = pm_summary.get('open_short_positions', [])

        report_lines.append(f"\n  Posiciones Abiertas al Final: {open_long_count + open_short_count}")
        price_prec_report = getattr(config_module, 'PRICE_PRECISION', 4)
        qty_prec_report = getattr(config_module, 'DEFAULT_QTY_PRECISION', 6)

        # <<< INICIO DE CAMBIOS: Mostrar SL y estado de TS en posiciones abiertas >>>
        if open_long_count > 0:
             report_lines.append(f"    Longs Abiertas ({open_long_count}):")
             for pos in open_long_details:
                 entry_price_val = utils_module.safe_float_convert(pos.get('entry_price', 0.0))
                 size_contracts_val = utils_module.safe_float_convert(pos.get('size_contracts', 0.0))
                 sl_price_val = pos.get('stop_loss_price')
                 sl_str = f"{sl_price_val:.{price_prec_report}f}" if sl_price_val is not None else "N/A"
                 ts_active_str = "Activo" if pos.get('ts_is_active') else "Inactivo"
                 ts_stop_price = pos.get('ts_stop_price')
                 ts_str = f"Stop @ {ts_stop_price:.{price_prec_report}f}" if ts_active_str == "Activo" and ts_stop_price is not None else ts_active_str

                 report_lines.append(f"      - ID: ...{str(pos.get('id','N/A'))[-6:]}, Entry: {entry_price_val:.{price_prec_report}f}, Size: {size_contracts_val:.{qty_prec_report}f}, SL: {sl_str}, TS: {ts_str}")

        if open_short_count > 0:
             report_lines.append(f"    Shorts Abiertas ({open_short_count}):")
             for pos in open_short_details:
                 entry_price_val = utils_module.safe_float_convert(pos.get('entry_price', 0.0))
                 size_contracts_val = utils_module.safe_float_convert(pos.get('size_contracts', 0.0))
                 sl_price_val = pos.get('stop_loss_price')
                 sl_str = f"{sl_price_val:.{price_prec_report}f}" if sl_price_val is not None else "N/A"
                 ts_active_str = "Activo" if pos.get('ts_is_active') else "Inactivo"
                 ts_stop_price = pos.get('ts_stop_price')
                 ts_str = f"Stop @ {ts_stop_price:.{price_prec_report}f}" if ts_active_str == "Activo" and ts_stop_price is not None else ts_active_str

                 report_lines.append(f"      - ID: ...{str(pos.get('id','N/A'))[-6:]}, Entry: {entry_price_val:.{price_prec_report}f}, Size: {size_contracts_val:.{qty_prec_report}f}, SL: {sl_str}, TS: {ts_str}")
        # <<< FIN DE CAMBIOS >>>

    else:
        report_lines.append("  Gestión de Posiciones Desactivada o resumen no disponible.")
    report_lines.append("")

    try:
        results_filepath = getattr(config_module, 'RESULTS_FILEPATH', 'result/results.txt')
        results_dir = os.path.dirname(results_filepath)
        if results_dir: os.makedirs(results_dir, exist_ok=True)
        with open(results_filepath, 'w', encoding='utf-8') as f:
            f.write("\n".join(report_lines))
        print(f"[Results Reporter] Reporte guardado en: {results_filepath}")
    except Exception as e:
        print(f"ERROR [Results Reporter] guardando reporte: {e}"); traceback.print_exc()
    print("--- Fin Generación Reporte ---")

def generate_report(final_summary: dict, operation_mode: str):
    """
    Función de entrada principal para generar reportes. Llama a la función
    de generación detallada.
    """
    current_config = global_config_for_load_closed
    current_utils = global_utils_for_load_closed

    generate_backtest_report_from_summary(
        pm_summary=final_summary,
        operation_mode=operation_mode,
        config_module=current_config,
        utils_module=current_utils
    )

# =============== FIN ARCHIVO: core/reporting/results_reporter.py (v14 - Reporte con SL Individual y TS) ===============
