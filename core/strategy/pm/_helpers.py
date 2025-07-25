"""
Funciones auxiliares para Position Manager y sus ejecutores.
Incluye formateo, redondeo de cantidades y extracción de datos.

v2.0: Refactorizado para ser agnóstico al exchange.
- Las funciones ahora dependen de `AbstractExchange` para obtener datos del instrumento.
- Se ha añadido una función para extraer estado desde `StandardPosition`.
"""
from decimal import Decimal, ROUND_DOWN, InvalidOperation
import datetime
import numpy as np
import traceback # Importamos al inicio del módulo
from typing import Optional, Dict, Any, List, TYPE_CHECKING

# --- Dependencias del Proyecto ---
# Estas dependencias son inyectadas/configuradas por el runner al inicio.
try:
    from core.exchange import AbstractExchange, StandardPosition
    from core.logging import memory_logger
except ImportError:
    class AbstractExchange: pass
    class StandardPosition: pass
    class MemoryLoggerFallback:
        def log(self, msg, level="INFO"): print(f"[{level}] {msg}")
    memory_logger = MemoryLoggerFallback()

if TYPE_CHECKING:
    import config as cfg_mod
    from core import utils as ut_mod
    
# --- Dependencias del Módulo (inyectadas al inicio) ---
# Mantenemos este patrón simple del código original.
_config: Optional['cfg_mod'] = None
_utils: Optional['ut_mod'] = None

def set_dependencies(config_module: Any, utils_module: Any):
    """Establece las dependencias esenciales para este módulo de helpers."""
    global _config, _utils
    _config = config_module
    _utils = utils_module

# --- Funciones Auxiliares ---

def format_pos_for_summary(pos: Dict[str, Any]) -> Dict[str, Any]:
    """Formatea un diccionario de posición lógica para el resumen de la TUI."""
    if not _utils or not _config: 
         memory_logger.log("WARN [Helper Format Summary]: Módulo utils o config no disponible.", level="WARN")
         return pos 

    try:
        entry_ts_str = _utils.format_datetime(pos.get('entry_timestamp')) if pos.get('entry_timestamp') else "N/A"
        size_contracts = _utils.safe_float_convert(pos.get('size_contracts'), default=0.0)
        
        price_prec_summary = getattr(_config, 'PRICE_PRECISION', 4)
        
        est_liq_price_val = _utils.safe_float_convert(pos.get('est_liq_price'))
        est_liq_price_formatted = round(est_liq_price_val, price_prec_summary) if est_liq_price_val is not None and np.isfinite(est_liq_price_val) else None
        
        pos_id_raw = pos.get('id', 'N/A')
        pos_id_str = str(pos_id_raw)

        return {
            'id': pos_id_str[-6:], 
            'entry_timestamp': entry_ts_str,
            'entry_price': round(_utils.safe_float_convert(pos.get('entry_price'), 0.0), price_prec_summary),
            'margin_usdt': round(_utils.safe_float_convert(pos.get('margin_usdt'), 0.0), 4),
            'size_contracts': round(size_contracts, getattr(_config, 'DEFAULT_QTY_PRECISION', 8)),
            'stop_loss_price': round(_utils.safe_float_convert(pos.get('stop_loss_price'), 0.0), price_prec_summary) if pos.get('stop_loss_price') else None,
            'est_liq_price': est_liq_price_formatted, 
            'leverage': pos.get('leverage'), 
            'api_order_id': str(pos.get('api_order_id', 'N/A'))[-8:]
        }
    except Exception as e:
        pos_id_raw_err = pos.get('id', 'N/A')
        pos_id_str_err = str(pos_id_raw_err)
        memory_logger.log(f"ERROR [Helper Format Summary]: Formateando posición {pos_id_str_err}: {e}", level="ERROR")
        return {'id': pos_id_str_err[-6:], 'error': f'Formato fallido: {e}'}

def calculate_and_round_quantity(
    margin_usdt: float,
    entry_price: float,
    leverage: float,
    symbol: str,
    is_live: bool, # Mantenido por compatibilidad, aunque ahora se asume siempre live
    exchange_adapter: AbstractExchange
) -> Dict[str, Any]:
    """
    Calcula y redondea la cantidad de contratos usando la información del exchange_adapter.
    """
    result = {'success': False, 'qty_float': 0.0, 'qty_str': "0.0", 'precision': 3, 'error': None}
    
    if not all([_config, _utils, exchange_adapter]):
        result['error'] = "Dependencias (config, utils, exchange_adapter) no disponibles en helper."
        return result
    if not isinstance(entry_price, (int, float)) or entry_price <= 0:
        result['error'] = f"Precio de entrada inválido: {entry_price}."
        return result
    if not isinstance(leverage, (int, float)) or leverage <= 0:
        result['error'] = f"Apalancamiento inválido: {leverage}."
        return result
    if not isinstance(margin_usdt, (int, float)) or margin_usdt < 0:
        result['error'] = f"Margen inválido: {margin_usdt}."
        return result

    size_contracts_raw = _utils.safe_division(margin_usdt * leverage, entry_price, default=0.0)
    if size_contracts_raw <= 1e-12: 
        result['error'] = f"Cantidad calculada raw es 0 o negativa ({size_contracts_raw:.15f})."
        return result

    # Obtener reglas del instrumento desde el adaptador
    instrument_info = exchange_adapter.get_instrument_info(symbol)
    if instrument_info:
        qty_precision = instrument_info.quantity_precision
        min_order_qty = instrument_info.min_order_size
    else:
        # Fallback a la configuración si la llamada a la API falla
        memory_logger.log(f"WARN [Helper Qty]: No se pudo obtener instrument info. Usando defaults de config.py.", level="WARN")
        qty_precision = int(getattr(_config, 'DEFAULT_QTY_PRECISION', 3))
        min_order_qty = float(getattr(_config, 'DEFAULT_MIN_ORDER_QTY', 0.001))

    result['precision'] = qty_precision

    try:
        size_contracts_decimal = Decimal(str(size_contracts_raw))
        rounding_factor = Decimal('1e-' + str(qty_precision))
        size_contracts_rounded = size_contracts_decimal.quantize(rounding_factor, rounding=ROUND_DOWN)
        size_contracts_final_float = float(size_contracts_rounded)
        
        # Formatear a string con la cantidad exacta de decimales requeridos por la API
        size_contracts_str_api = format(size_contracts_rounded, f'.{qty_precision}f')

        if size_contracts_final_float < (float(min_order_qty) - 1e-9): 
            result['error'] = f"Cantidad redondeada ({size_contracts_str_api}) < mínimo ({min_order_qty})."
            return result

        result['success'] = True
        result['qty_float'] = size_contracts_final_float
        result['qty_str'] = size_contracts_str_api
        return result

    except Exception as e:
        result['error'] = f"Excepción redondeando cantidad (raw={size_contracts_raw}, prec={qty_precision}): {e}"
        return result

def format_quantity_for_api(
    quantity_float: float,
    symbol: str,
    is_live: bool, # Mantenido por compatibilidad
    exchange_adapter: AbstractExchange
) -> Dict[str, Any]:
    """
    Formatea una cantidad flotante a string con la precisión correcta del exchange.
    """
    result = {'success': False, 'qty_str': "0.0", 'precision': 3, 'error': None}
    if not all([_config, _utils, exchange_adapter]):
        result['error'] = "Dependencias (config, utils, exchange_adapter) no disponibles."
        return result
    if not isinstance(quantity_float, (int, float)) or quantity_float < 0:
         result['error'] = f"Cantidad inválida para formatear: {quantity_float}."
         return result

    instrument_info = exchange_adapter.get_instrument_info(symbol)
    if instrument_info:
        qty_precision = instrument_info.quantity_precision
    else:
        memory_logger.log(f"WARN [Helper Format Qty]: No se pudo obtener instrument info. Usando default de config.py.", level="WARN")
        qty_precision = int(getattr(_config, 'DEFAULT_QTY_PRECISION', 3))

    result['precision'] = qty_precision

    try:
        quantity_decimal = Decimal(str(quantity_float))
        rounding_factor = Decimal('1e-' + str(qty_precision))
        quantity_rounded = quantity_decimal.quantize(rounding_factor, rounding=ROUND_DOWN)
        quantity_str_api = format(quantity_rounded, f'.{qty_precision}f')

        result['success'] = True
        result['qty_str'] = quantity_str_api
        return result
    
    except Exception as e:
        result['error'] = f"Excepción formateando cantidad (val={quantity_float}, prec={qty_precision}): {e}"
        return result

def extract_physical_state_from_standard_positions(
    positions: List[StandardPosition],
    utils_module: Any
) -> Optional[Dict[str, Any]]:
    """
    Extrae y calcula el estado físico agregado desde una lista de objetos StandardPosition.
    """
    if not utils_module:
        memory_logger.log("ERROR [Helper Extract Standard]: Módulo utils no disponible.", level="ERROR")
        return None

    if not positions:
        return None 

    try:
        total_size = sum(p.size_contracts for p in positions)
        total_value = sum(p.size_contracts * p.avg_entry_price for p in positions)
        avg_price = utils_module.safe_division(total_value, total_size, 0.0)
        total_margin = sum(p.margin_usd for p in positions)
        # Asumimos que la liquidación es la misma para todas las partes de la posición
        liq_price = positions[0].liquidation_price if positions else None
        
        return {
            'avg_entry_price': avg_price,
            'total_size_contracts': total_size,
            'total_margin_usdt': total_margin,
            'liquidation_price': liq_price,
            'timestamp': datetime.datetime.now()
        }
    except Exception as e:
        memory_logger.log(f"ERROR [Helper Extract Standard]: Excepción calculando agregados: {e}", level="ERROR")
        memory_logger.log(traceback.format_exc(), level="ERROR")
        return None