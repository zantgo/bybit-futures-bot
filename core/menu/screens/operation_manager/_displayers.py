"""
Módulo de Visualizadores del Panel de Control de Operación.

Contiene todas las funciones auxiliares cuya única responsabilidad es
mostrar (imprimir en la consola) secciones de información específicas, como
los detalles de la operación, las estadísticas de capital o las tablas de posiciones.
Estas funciones son "vistas puras": solo renderizan los datos que reciben.

v2.0 (Fallback Robusto):
- La clase de fallback para 'Operacion' ahora incluye todos los atributos
  necesarios con valores por defecto. Esto previene un `AttributeError` si
  la importación principal falla y asegura que la TUI pueda renderizar un
  estado vacío en lugar de crashear.
"""
from typing import Any, Dict
import datetime

try:
    from core.strategy.om._entities import Operacion
except ImportError:
    class Operacion:
        def __init__(self):
            self.estado = 'DESCONOCIDO'
            self.tendencia = 'N/A'
            self.tamaño_posicion_base_usdt = 0.0
            self.apalancamiento = 0.0
            self.max_posiciones_logicas = 0
            self.tiempo_inicio_ejecucion = None
            self.tsl_activacion_pct = 0.0
            self.tsl_distancia_pct = 0.0
            self.sl_posicion_individual_pct = 0.0
            self.accion_al_finalizar = 'N/A'
            self.pnl_realizado_usdt = 0.0
            self.capital_inicial_usdt = 0.0
            self.comercios_cerrados_contador = 0
            self.comisiones_totales_usdt = 0.0
            self.tipo_cond_entrada = 'N/A'
            self.valor_cond_entrada = 0.0
            self.tipo_cond_salida = None
            self.valor_cond_salida = None
            self.tsl_roi_activacion_pct = None
            self.tsl_roi_distancia_pct = None
            self.tsl_roi_activo = False
            self.tsl_roi_peak_pct = 0.0
            self.sl_roi_pct = None
            self.tiempo_maximo_min = None
            self.max_comercios = None

# --- Inyección de Dependencias ---
_deps: Dict[str, Any] = {}

def init(dependencies: Dict[str, Any]):
    """Recibe las dependencias inyectadas desde el __init__.py del módulo."""
    global _deps
    _deps = dependencies

# --- Funciones de Visualización ---

def _display_operation_details(summary: Dict[str, Any], operacion: Operacion, side: str):
    """Muestra la sección de parámetros de la operación para un lado específico."""
    print(f"\n--- Parámetros de la Operación {side.upper()} " + "-"*48)
    
    if not operacion or operacion.estado == 'DETENIDA':
        print(f"  (La operación {side.upper()} está DETENIDA y no tiene parámetros activos)")
        return

    tendencia = operacion.tendencia
    color_map = {'LONG_ONLY': "\033[92m", 'SHORT_ONLY': "\033[91m"}
    color, reset = color_map.get(tendencia, ""), "\033[0m"
    
    pos_abiertas = summary.get(f'open_{side}_positions_count', 0)
    pos_total = operacion.max_posiciones_logicas

    fecha_activacion_str = "N/A"
    tiempo_ejecucion_str = "N/A"
    if operacion.tiempo_inicio_ejecucion:
        fecha_activacion_str = operacion.tiempo_inicio_ejecucion.strftime('%Y-%m-%d %H:%M:%S')
        duration = datetime.datetime.now(datetime.timezone.utc) - operacion.tiempo_inicio_ejecucion
        total_seconds = int(duration.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        tiempo_ejecucion_str = f"{hours:02}:{minutes:02}:{seconds:02}"
    
    col1 = {
        "Tendencia": f"{color}{tendencia}{reset}",
        "Tamaño Base": f"{operacion.tamaño_posicion_base_usdt:.2f}$",
        "Apalancamiento": f"{operacion.apalancamiento:.1f}x",
        "Posiciones": f"{pos_abiertas} / {pos_total}",
        "Fecha Activacion": fecha_activacion_str
    }
    col2 = {
        "TSL Activación": f"{operacion.tsl_activacion_pct}%",
        "TSL Distancia": f"{operacion.tsl_distancia_pct}%",
        "SL Individual": f"{operacion.sl_posicion_individual_pct}%",
        "Acción Final": operacion.accion_al_finalizar,
        "Tiempo Activa": tiempo_ejecucion_str
    }

    max_key_len1 = max(len(k) for k in col1.keys())
    max_key_len2 = max(len(k) for k in col2.keys())
    keys1, keys2 = list(col1.keys()), list(col2.keys())
    for i in range(len(keys1)):
        k1, v1 = keys1[i], col1[keys1[i]]
        k2, v2 = (keys2[i], col2[keys2[i]]) if i < len(keys2) else ("", "")
        print(f"  {k1:<{max_key_len1}}: {v1:<22} |  {k2:<{max_key_len2}}: {v2}")

def _display_capital_stats(summary: Dict[str, Any], operacion: Operacion, side: str, current_price: float):
    """Muestra la sección de estadísticas de capital para un lado específico."""
    print(f"\n--- Capital y Rendimiento ({side.upper()}) " + "-"*52)
    
    if not operacion or operacion.estado == 'DETENIDA':
        print(f"  (La operación {side.upper()} está DETENIDA y no tiene capital asignado)")
        return

    unrealized_pnl = 0.0
    for pos_data in summary.get(f'open_{side}_positions', []):
        entry = pos_data.get('entry_price', 0.0)
        size = pos_data.get('size_contracts', 0.0)
        if side == 'long': unrealized_pnl += (current_price - entry) * size
        else: unrealized_pnl += (entry - current_price) * size

    realized_pnl = operacion.pnl_realizado_usdt
    total_pnl = realized_pnl + unrealized_pnl
    initial_capital = operacion.capital_inicial_usdt
    roi = (total_pnl / initial_capital) * 100 if initial_capital > 0 else 0.0
    
    pnl_color, reset = ("\033[92m" if total_pnl >= 0 else "\033[91m"), "\033[0m"
    capital_actual = initial_capital + realized_pnl

    trades_abiertos = summary.get(f'open_{side}_positions_count', 0)
    trades_cerrados = operacion.comercios_cerrados_contador
    
    comisiones_totales = getattr(operacion, 'comisiones_totales_usdt', 0.0)

    ganancias_netas = total_pnl - comisiones_totales
    netas_color = "\033[92m" if ganancias_netas >= 0 else "\033[91m"
    
    avg_entry_price = summary.get(f'avg_entry_price_{side}', 'N/A')
    avg_liq_price = summary.get(f'avg_liq_price_{side}', 'N/A')

    avg_entry_str = f"{avg_entry_price:.4f}" if isinstance(avg_entry_price, (int, float)) else "N/A"
    avg_liq_str = f"{avg_liq_price:.4f}" if isinstance(avg_liq_price, (int, float)) else "N/A"
    
    print(f"  {'Capital Inicial':<20}: {initial_capital:<19.2f}$ |  {'Capital Actual':<20}: {capital_actual:<.2f}$")
    print(f"  {'PNL Total Op.':<20}: {pnl_color}{total_pnl:<+18.4f}${reset} |  {'ROI Op.':<20}: {pnl_color}{roi:<+.2f}%{reset}")
    print(f"  {'Trades Abiertos':<20}: {trades_abiertos:<22} |  {'Trades Cerrados':<20}: {trades_cerrados}")
    print(f"  {'Comisiones Totales':<20}: ${comisiones_totales:<20.4f} |  {'Ganancias Netas':<20}: {netas_color}${ganancias_netas:<.4f}{reset}")
    print(f"  {'Avg Ent Price':<20}: {avg_entry_str:<22} |  {'Avg Liq Price':<20}: {avg_liq_str}")

def _display_positions_tables(summary: Dict[str, Any], operacion: Operacion, current_price: float, side: str):
    """Muestra la tabla de posiciones abiertas para un lado específico."""
    positions = summary.get(f'open_{side}_positions', [])
    max_pos = operacion.max_posiciones_logicas if operacion else 'N/A'
    
    header_title = f"--- Posiciones ({len(positions)}/{max_pos}) "
    print("\n" + header_title + "-"*(80 - len(header_title)))
    
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
        ts_info = "TS Inactivo" # Esto puede mejorarse para mostrar el precio de stop del TSL
        print(f"    {entry:10.4f} {sl:10.4f if sl else 'N/A':>10} {ts_info:>15} {pnl_color}{pnl:14.4f}$\033[0m {pnl_color}{roi:9.2f}%\033[0m")

def _display_operation_conditions(operacion: Operacion):
    """Muestra la sección de condiciones de entrada y salida de la operación."""
    print("\n--- Condiciones de la Operación " + "-"*54)
    
    status_color_map = {
        'ACTIVA': "\033[92m", 'PAUSADA': "\033[93m", 'DETENIDA': "\033[90m", 'EN_ESPERA': "\033[96m"
    }
    color = status_color_map.get(operacion.estado, "")
    reset = "\033[0m"
    
    cond_in_str = "No definida (Operación Inactiva)"
    if operacion.estado != 'DETENIDA':
        if operacion.tipo_cond_entrada == 'MARKET': 
            cond_in_str = "Inmediata (Precio de Mercado)"
        elif operacion.tipo_cond_entrada and operacion.valor_cond_entrada is not None:
            op = ">" if operacion.tipo_cond_entrada == 'PRICE_ABOVE' else "<"
            cond_in_str = f"Precio {op} {operacion.valor_cond_entrada:.4f}"
    
    print(f"  Estado: {color}{operacion.estado}{reset}")
    print(f"  Condición de Entrada: {cond_in_str}")
    
    print(f"  Condiciones de Salida (se desactiva al cumplirse CUALQUIERA):")
    exit_conditions = []
    if operacion.tipo_cond_salida and operacion.valor_cond_salida is not None:
        op = ">" if operacion.tipo_cond_salida == 'PRICE_ABOVE' else "<"
        exit_conditions.append(f"Precio {op} {operacion.valor_cond_salida:.4f}")
    
    if operacion.tsl_roi_activacion_pct is not None and operacion.tsl_roi_distancia_pct is not None:
        tsl_config_str = (f"TSL-ROI: Activa a {operacion.tsl_roi_activacion_pct}%, "
                          f"Distancia {operacion.tsl_roi_distancia_pct}%")
        
        if operacion.tsl_roi_activo:
            tsl_config_str += f" (ACTIVO | Pico: {operacion.tsl_roi_peak_pct:.2f}%)"
        
        exit_conditions.append(tsl_config_str)

    if operacion.sl_roi_pct is not None: 
        exit_conditions.append(f"SL-ROI <= {operacion.sl_roi_pct}%")
    if operacion.tiempo_maximo_min is not None: 
        exit_conditions.append(f"Tiempo >= {operacion.tiempo_maximo_min} min")
    if operacion.max_comercios is not None: 
        exit_conditions.append(f"Trades >= {operacion.max_comercios}")

    if not exit_conditions: 
        print("    - Ninguna (finalización manual o por SL/TS individuales)")
    else: 
        for cond in exit_conditions:
            print(f"    - {cond}")

    # --- INICIO DE LA MODIFICACIÓN ---
    # Añadimos la línea que muestra la acción final de la operación.
    if operacion.estado != 'DETENIDA':
        print(f"  Acción de Salida Automática: {operacion.accion_al_finalizar.upper()}")
    # --- FIN DE LA MODIFICACIÓN ---