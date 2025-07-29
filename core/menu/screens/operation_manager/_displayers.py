"""
Módulo de Visualizadores del Panel de Control de Operación.

Contiene todas las funciones auxiliares cuya única responsabilidad es
mostrar (imprimir en la consola) secciones de información específicas, como
los detalles de la operación, las estadísticas de capital o las tablas de posiciones.
"""
from typing import Any, Dict

# Importar helpers y entidades necesarios
try:
    from core.strategy.pm._entities import Operacion
except ImportError:
    class Operacion: pass

# --- Inyección de Dependencias ---
_deps: Dict[str, Any] = {}

def init(dependencies: Dict[str, Any]):
    """Recibe las dependencias inyectadas desde el __init__.py del módulo."""
    global _deps
    _deps = dependencies

# --- Funciones de Visualización ---

def _display_operation_details(summary: Dict[str, Any]):
    """Muestra la sección de parámetros de la operación."""
    print("\n--- Parámetros de la Operación " + "-"*54)
    op_state = summary.get('operation_status', {})
    tendencia = op_state.get('tendencia', 'NEUTRAL')
    color_map = {'LONG_ONLY': "\033[92m", 'SHORT_ONLY': "\033[91m", 'LONG_SHORT': "\033[96m", 'NEUTRAL': "\033[90m"}
    color, reset = color_map.get(tendencia, ""), "\033[0m"
    pos_abiertas = len(summary.get('open_long_positions', [])) + len(summary.get('open_short_positions', []))
    pos_total = op_state.get('max_posiciones_logicas', 0)
    col1 = {
        "Tendencia": f"{color}{tendencia}{reset}",
        "Tamaño Base": f"{op_state.get('tamaño_posicion_base_usdt', 0):.2f}$",
        "Apalancamiento": f"{op_state.get('apalancamiento', 0.0):.1f}x",
        "Posiciones": f"{pos_abiertas} / {pos_total}"
    }
    col2 = {
        "TSL Activación": f"{op_state.get('tsl_activacion_pct', 0.0)}%",
        "TSL Distancia": f"{op_state.get('tsl_distancia_pct', 0.0)}%",
        "SL Individual": f"{op_state.get('sl_posicion_individual_pct', 0.0)}%",
        " ": " "
    }
    max_key_len1 = max(len(k) for k in col1.keys())
    max_key_len2 = max(len(k) for k in col2.keys())
    keys1, keys2 = list(col1.keys()), list(col2.keys())
    for i in range(len(keys1)):
        k1, v1, k2, v2 = keys1[i], col1[keys1[i]], keys2[i], col2[keys2[i]]
        print(f"  {k1:<{max_key_len1}}: {v1:<22} |  {k2:<{max_key_len2}}: {v2}")

def _display_capital_stats(summary: Dict[str, Any]):
    """Muestra la sección de estadísticas de capital y rendimiento."""
    print("\n--- Capital y Rendimiento " + "-"*58)
    op_state = summary.get('operation_status', {})
    op_pnl, op_roi = summary.get('operation_pnl', 0.0), summary.get('operation_roi', 0.0)
    pnl_color, reset = ("\033[92m" if op_pnl >= 0 else "\033[91m"), "\033[0m"
    capital_inicial = op_state.get('capital_inicial_usdt', 0.0)
    pnl_realizado = op_state.get('pnl_realizado_usdt', 0.0)
    capital_actual = capital_inicial + pnl_realizado
    col1 = {"Capital Inicial": f"{capital_inicial:.2f}$", "Capital Actual": f"{capital_actual:.2f}$", "Tiempo Ejecución": op_state.get('tiempo_ejecucion_str', 'N/A')}
    col2 = {"PNL": f"{pnl_color}{op_pnl:+.4f}${reset}", "ROI": f"{pnl_color}{op_roi:+.2f}%{reset}", "Comercios Cerrados": op_state.get('comercios_cerrados_contador', 0)}
    max_key_len = max(len(k) for k in col1.keys())
    for (k1, v1), (k2, v2) in zip(col1.items(), col2.items()):
        print(f"  {k1:<{max_key_len}}: {v1:<20} |  {k2:<18}: {v2}")

def _display_positions_tables(summary: Dict[str, Any], current_price: float):
    """Muestra las tablas de posiciones abiertas para LONG y SHORT."""
    print("\n--- Posiciones " + "-"*69)
    def print_table(side: str):
        positions = summary.get(f'open_{side}_positions', [])
        print(f"  Tabla {side.upper()} ({len(positions)})")
        if not positions: 
            print("    (No hay posiciones abiertas)")
            return
        header = f"    {'Entrada':>10} {'SL':>10} {'TSL':>15} {'PNL (U)':>15} {'ROI (%)':>10}"
        print(header); print("    " + "-" * (len(header)-4))
        for pos in positions:
            entry, sl, margin, size = pos.get('entry_price', 0.0), pos.get('stop_loss_price'), pos.get('margin_usdt', 0.0), pos.get('size_contracts', 0.0)
            pnl = (current_price - entry) * size if side == 'long' else (entry - current_price) * size
            roi = (pnl / margin) * 100 if margin > 0 else 0.0
            pnl_color = "\033[92m" if pnl >= 0 else "\033[91m"
            print(f"    {entry:10.4f} {sl:10.4f if sl else 'N/A':>10} {'Inactivo':>15} {pnl_color}{pnl:14.4f}$\033[0m {pnl_color}{roi:9.2f}%\033[0m")
        print()
    print_table('long')
    print_table('short')

def _display_operation_conditions(operacion: Operacion):
    """Muestra la sección de condiciones de entrada y salida de la operación."""
    print("\n--- Condiciones de la Operación " + "-"*54)
    estado = 'ACTIVA' if operacion.tendencia != 'NEUTRAL' else 'EN_ESPERA'
    cond_in_str = "No definida"
    if operacion.tipo_cond_entrada == 'MARKET': 
        cond_in_str = "Inmediata (Precio de Mercado)"
    elif operacion.tipo_cond_entrada and operacion.valor_cond_entrada is not None:
        op = ">" if operacion.tipo_cond_entrada == 'PRICE_ABOVE' else "<"
        cond_in_str = f"Precio {op} {operacion.valor_cond_entrada:.4f}"
    
    status_color_map = {'EN_ESPERA': "\033[93m", 'ACTIVA': "\033[92m"}
    color, reset = status_color_map.get(estado, ""), "\033[0m"
    
    print(f"  Estado: {color}{estado}{reset}")
    print(f"  Condición de Entrada: {cond_in_str}")
    
    print(f"  Condiciones de Salida:")
    exit_conditions = []
    if operacion.tipo_cond_salida and operacion.valor_cond_salida is not None:
        op = ">" if operacion.tipo_cond_salida == 'PRICE_ABOVE' else "<"
        exit_conditions.append(f"Precio {op} {operacion.valor_cond_salida:.4f}")
    if operacion.tp_roi_pct is not None: 
        exit_conditions.append(f"TP-ROI >= {operacion.tp_roi_pct}%")
    if operacion.sl_roi_pct is not None: 
        exit_conditions.append(f"SL-ROI <= {operacion.sl_roi_pct}%")
    if operacion.tiempo_maximo_min is not None: 
        exit_conditions.append(f"Tiempo >= {operacion.tiempo_maximo_min} min")
    if operacion.max_comercios is not None: 
        exit_conditions.append(f"Trades >= {operacion.max_comercios}")

    if not exit_conditions: 
        print("    - Ninguna (finalización manual)")
    else: 
        print(f"    - {', '.join(exit_conditions)}")