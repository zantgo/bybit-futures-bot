# =============== INICIO ARCHIVO: core/strategy/_position_helpers.py (v1.0.1 - Añadido est_liq_price a summary) ===============
"""
Funciones auxiliares para Position Manager y sus ejecutores.
Incluye formateo, redondeo de cantidades y extracción de datos API.
v1.0.1: Añadido 'est_liq_price' al diccionario devuelto por format_pos_for_summary.
"""
from decimal import Decimal, ROUND_DOWN, InvalidOperation
import datetime
import numpy as np # Importar numpy para np.isfinite y otros usos
from typing import Optional, Dict, Any, List, TYPE_CHECKING

# Dependencias (se establecerán mediante funciones set_... desde la fachada)
_config: Optional[Any] = None
_utils: Optional[Any] = None
_live_operations: Optional[Any] = None

if TYPE_CHECKING:
    import config as cfg_mod # pyright: ignore [reportUnusedImport]
    from core import _utils as ut_mod # pyright: ignore [reportUnusedImport]
    from core import live_operations as lo_mod # pyright: ignore [reportUnusedImport]

def set_config_dependency(config_module: Any):
    """Establece la dependencia del módulo config."""
    global _config
    _config = config_module
    print(f"DEBUG [Helper]: Dependencia Config establecida: {'Sí' if _config else 'No'}")

def set_utils_dependency(utils_module: Any):
    """Establece la dependencia del módulo utils."""
    global _utils
    _utils = utils_module
    print(f"DEBUG [Helper]: Dependencia Utils establecida: {'Sí' if _utils else 'No'}")

def set_live_operations_dependency(live_ops_module: Optional[Any]):
    """Establece la dependencia del módulo live_operations (puede ser None)."""
    global _live_operations
    _live_operations = live_ops_module
    print(f"DEBUG [Helper]: Dependencia Live Ops establecida: {'Sí' if _live_operations else 'No'}")


# --- Funciones Auxiliares ---

def format_pos_for_summary(pos: Dict[str, Any], utils_module: Any) -> Dict[str, Any]: # Renombrado utils a utils_module para evitar conflicto
    """Formatea un diccionario de posición lógica para el resumen JSON."""
    if not utils_module: 
         print("WARN [Helper Format Summary]: Módulo utils no disponible.")
         return pos 

    try:
        entry_ts_str = utils_module.format_datetime(pos.get('entry_timestamp')) if pos.get('entry_timestamp') else "N/A"
        size_contracts = utils_module.safe_float_convert(pos.get('size_contracts'), default=0.0)
        
        # Usar _config si está disponible, sino un default razonable para price_prec_summary
        price_prec_summary = getattr(_config, 'PRICE_PRECISION', 4) if _config else 4
        
        est_liq_price_val = utils_module.safe_float_convert(pos.get('est_liq_price')) # Puede ser None
        est_liq_price_formatted = round(est_liq_price_val, price_prec_summary) if est_liq_price_val is not None and np.isfinite(est_liq_price_val) else None
        
        # Asegurar que el ID siempre sea un string antes de hacer slicing
        pos_id_raw = pos.get('id', 'N/A')
        pos_id_str = str(pos_id_raw)

        return {
            'id': pos_id_str[-6:], 
            'entry_timestamp': entry_ts_str,
            'entry_price': round(utils_module.safe_float_convert(pos.get('entry_price'), 0.0), price_prec_summary),
            'margin_usdt': round(utils_module.safe_float_convert(pos.get('margin_usdt'), 0.0), 4),
            'size_contracts': round(size_contracts, getattr(_config, 'DEFAULT_QTY_PRECISION', 8) if _config else 8), # Usar config para qty_prec
            'take_profit_price': round(utils_module.safe_float_convert(pos.get('take_profit_price'), 0.0), price_prec_summary),
            'est_liq_price': est_liq_price_formatted, 
            'leverage': pos.get('leverage'), 
            'api_order_id': pos.get('api_order_id') 
        }
    except Exception as e:
        pos_id_raw_err = pos.get('id', 'N/A')
        pos_id_str_err = str(pos_id_raw_err)
        print(f"ERROR [Helper Format Summary]: Formateando posición {pos_id_str_err}: {e}")
        return {'id': pos_id_str_err[-6:], 'error': f'Formato fallido: {e}'}


def calculate_and_round_quantity(
    margin_usdt: float,
    entry_price: float,
    leverage: float,
    symbol: str,
    is_live: bool
) -> Dict[str, Any]:
    """
    Calcula la cantidad de contratos basada en margen, precio y apalancamiento,
    y la redondea según la precisión del instrumento (API o config).
    Devuelve {'success': bool, 'qty_float': float, 'qty_str': str, 'precision': int, 'error': Optional[str]}
    """
    global _config, _utils, _live_operations 

    result = {'success': False, 'qty_float': 0.0, 'qty_str': "0.0", 'precision': 3, 'error': None}
    if not _config or not _utils:
        result['error'] = "Dependencias (config, utils) no disponibles en helper."
        return result
    if not isinstance(entry_price, (int, float)) or entry_price <= 0:
        result['error'] = f"Precio de entrada inválido: {entry_price} (tipo: {type(entry_price)})."
        return result
    if not isinstance(leverage, (int, float)) or leverage <= 0:
        result['error'] = f"Apalancamiento inválido: {leverage} (tipo: {type(leverage)})."
        return result
    if not isinstance(margin_usdt, (int, float)) or margin_usdt < 0:
        result['error'] = f"Margen inválido: {margin_usdt} (tipo: {type(margin_usdt)})."
        return result


    size_contracts_raw = _utils.safe_division(margin_usdt * leverage, entry_price, default=0.0)
    if size_contracts_raw <= 1e-12: 
        result['error'] = f"Cantidad calculada raw es 0 o negativa ({size_contracts_raw:.15f}). Margin: {margin_usdt}, Lev: {leverage}, Price: {entry_price}"
        return result

    qty_precision = int(getattr(_config, 'DEFAULT_QTY_PRECISION', 3)) 
    min_order_qty = float(getattr(_config, 'DEFAULT_MIN_ORDER_QTY', 0.001)) 

    if is_live and _live_operations and symbol:
         try:
             instrument_info = _live_operations.get_instrument_info(symbol)
             if instrument_info:
                 qty_step_str = instrument_info.get('qtyStep')
                 min_qty_str = instrument_info.get('minOrderQty')
                 if qty_step_str and hasattr(_live_operations, '_get_qty_precision_from_step'):
                     try:
                         qty_precision = _live_operations._get_qty_precision_from_step(qty_step_str)
                     except Exception as prec_err: print(f"WARN [Helper Qty]: Error calculando precisión desde qtyStep '{qty_step_str}': {prec_err}")
                 elif qty_step_str:
                      try:
                          step_val = float(qty_step_str)
                          if step_val > 0 and step_val < 1:
                              if 'e-' in qty_step_str.lower():
                                   precision_e = int(qty_step_str.lower().split('e-')[-1])
                                   qty_precision = precision_e
                              elif '.' in qty_step_str:
                                   qty_precision = len(qty_step_str.split('.')[-1].rstrip('0'))
                              else: qty_precision = 0 
                          else: qty_precision = 0 
                      except Exception as manual_prec_err:
                           print(f"WARN [Helper Qty]: Error calculando precisión manual desde qtyStep '{qty_step_str}': {manual_prec_err}")
                 if min_qty_str:
                     min_order_qty = _utils.safe_float_convert(min_qty_str, min_order_qty)
         except Exception as api_info_err:
              print(f"WARN [Helper Qty]: Error obteniendo info instrumento API: {api_info_err}")

    result['precision'] = qty_precision 

    try:
        size_contracts_decimal = Decimal(str(size_contracts_raw))
        rounding_factor = Decimal('1e-' + str(qty_precision))
        size_contracts_rounded = size_contracts_decimal.quantize(rounding_factor, rounding=ROUND_DOWN)
        size_contracts_final_float = float(size_contracts_rounded)
        size_contracts_str_api = str(size_contracts_rounded) 

        if size_contracts_final_float < (float(min_order_qty) - 1e-9): 
            result['error'] = f"Cantidad redondeada ({size_contracts_str_api}) < mínimo ({min_order_qty})."
            return result

        result['success'] = True
        result['qty_float'] = size_contracts_final_float
        result['qty_str'] = size_contracts_str_api
        return result

    except InvalidOperation as inv_op_err:
         result['error'] = f"Error de operación Decimal al redondear cantidad raw '{size_contracts_raw}' a {qty_precision} decimales: {inv_op_err}."
         return result
    except Exception as round_err:
        result['error'] = f"Excepción redondeando cantidad (raw={size_contracts_raw}, prec={qty_precision}): {round_err}"
        return result


def format_quantity_for_api(
    quantity_float: float,
    symbol: str,
    is_live: bool
) -> Dict[str, Any]:
    """
    Formatea una cantidad flotante a string con la precisión correcta para la API.
    Devuelve {'success': bool, 'qty_str': str, 'precision': int, 'error': Optional[str]}
    """
    global _config, _utils, _live_operations

    result = {'success': False, 'qty_str': "0.0", 'precision': 3, 'error': None}
    if not _config or not _utils:
        result['error'] = "Dependencias (config, utils) no disponibles en helper."
        return result
    if not isinstance(quantity_float, (int, float)) or quantity_float < 0:
         result['error'] = f"Cantidad inválida para formatear: {quantity_float} (tipo: {type(quantity_float)})."
         return result

    qty_precision = int(getattr(_config, 'DEFAULT_QTY_PRECISION', 3)) 
    if is_live and _live_operations and symbol:
        try:
            instrument_info = _live_operations.get_instrument_info(symbol)
            if instrument_info:
                qty_step_str = instrument_info.get('qtyStep')
                if qty_step_str and hasattr(_live_operations, '_get_qty_precision_from_step'):
                    try: qty_precision = _live_operations._get_qty_precision_from_step(qty_step_str)
                    except Exception as prec_err: print(f"WARN [Helper Format Qty]: Error calculando precisión desde qtyStep '{qty_step_str}': {prec_err}")
                elif qty_step_str:
                     try: 
                         step_val = float(qty_step_str)
                         if step_val > 0 and step_val < 1:
                              if 'e-' in qty_step_str.lower(): qty_precision = int(qty_step_str.lower().split('e-')[-1])
                              elif '.' in qty_step_str: qty_precision = len(qty_step_str.split('.')[-1].rstrip('0'))
                              else: qty_precision = 0
                         else: qty_precision = 0
                     except Exception as manual_prec_err: print(f"WARN [Helper Format Qty]: Error calculando precisión manual desde qtyStep '{qty_step_str}': {manual_prec_err}")
        except Exception as api_info_err:
            print(f"WARN [Helper Format Qty]: Error obteniendo info instrumento API: {api_info_err}")

    result['precision'] = qty_precision

    try:
        quantity_decimal = Decimal(str(quantity_float))
        rounding_factor = Decimal('1e-' + str(qty_precision))
        quantity_rounded = quantity_decimal.quantize(rounding_factor, rounding=ROUND_DOWN)
        quantity_str_api = format(quantity_rounded, f'.{qty_precision}f')

        result['success'] = True
        result['qty_str'] = quantity_str_api
        return result

    except InvalidOperation as inv_op_err:
         result['error'] = f"Error de operación Decimal al formatear cantidad '{quantity_float}' a {qty_precision} decimales: {inv_op_err}."
         return result
    except Exception as fmt_err:
        result['error'] = f"Excepción formateando cantidad (val={quantity_float}, prec={qty_precision}): {fmt_err}"
        return result

def extract_physical_state_from_api(
    positions_raw: List[Dict[str, Any]],
    symbol: str,
    side: str,
    utils_module: Any # Renombrado utils a utils_module
) -> Optional[Dict[str, Any]]:
    """
    Extrae y calcula el estado físico agregado (tamaño, precio prom, margen, liq)
    de una lista de posiciones de la API para un lado específico.
    Devuelve un diccionario con el estado o None si no hay posiciones.
    """
    if not utils_module:
        print("ERROR [Helper Extract API]: Módulo utils no disponible.")
        return None

    pos_idx_target_hedge = 1 if side == 'long' else 2

    physical_positions_side = [
        p for p in positions_raw
        if p.get('symbol') == symbol and
           p.get('positionIdx') == pos_idx_target_hedge and
           utils_module.safe_float_convert(p.get('size'), 0.0) > 1e-12
    ]

    if not physical_positions_side and positions_raw:
        side_target_oneway = 'Buy' if side == 'long' else 'Sell'
        physical_positions_side = [
            p for p in positions_raw
            if p.get('symbol') == symbol and
               p.get('positionIdx') == 0 and 
               p.get('side') == side_target_oneway and 
               utils_module.safe_float_convert(p.get('size'), 0.0) > 1e-12
        ]
        if physical_positions_side:
             print(f"DEBUG [Helper Extract API]: Posición {side.upper()} encontrada usando filtro One-Way (idx=0, side={side_target_oneway}).")


    if not physical_positions_side:
        return None 

    try:
        real_total_size = sum(utils_module.safe_float_convert(p.get('size'), 0.0) for p in physical_positions_side)
        real_total_value = sum(utils_module.safe_float_convert(p.get('size'), 0.0) * utils_module.safe_float_convert(p.get('avgPrice'), 0.0) for p in physical_positions_side)
        real_avg_price = utils_module.safe_division(real_total_value, real_total_size, 0.0)
        real_total_margin = sum(utils_module.safe_float_convert(p.get('positionIM', p.get('positionMM', 0.0)), 0.0) for p in physical_positions_side)
        real_liq_price_str = physical_positions_side[0].get('liqPrice')
        real_liq_price = utils_module.safe_float_convert(real_liq_price_str, None) if real_liq_price_str else None
        sync_timestamp = datetime.datetime.now()

        return {
            'avg_entry_price': real_avg_price,
            'total_size_contracts': real_total_size,
            'total_margin_usdt': real_total_margin,
            'liquidation_price': real_liq_price,
            'timestamp': sync_timestamp
        }
    except Exception as e:
         print(f"ERROR [Helper Extract API]: Excepción calculando agregados para {side}: {e}")
         import traceback
         traceback.print_exc()
         return None


# =============== FIN ARCHIVO: core/strategy/_position_helpers.py (v1.0.1 - Añadido est_liq_price a summary) ===============