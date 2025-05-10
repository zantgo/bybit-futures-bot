

# =============== INICIO ARCHIVO: core/strategy/_position_helpers.py (Corregido) ===============
"""
Funciones auxiliares para Position Manager y sus ejecutores.
Incluye formateo, redondeo de cantidades y extracción de datos API.
"""
from decimal import Decimal, ROUND_DOWN, InvalidOperation
import datetime
# <<< Añadido 'Any' a las importaciones de typing >>>
from typing import Optional, Dict, Any, List, TYPE_CHECKING

# Dependencias (se establecerán mediante funciones set_... desde la fachada)
# <<< CORRECCIÓN: Usar Any o tipos específicos >>>
_config: Optional[Any] = None # Antes: Optional['cfg_mod']
_utils: Optional[Any] = None # Antes: Optional['ut_mod']
_live_operations: Optional[Any] = None # Antes: Optional['lo_mod']

if TYPE_CHECKING:
    # <<< Mantenemos imports originales por referencia >>>
    import config as cfg_mod
    from core import utils as ut_mod
    from core import live_operations as lo_mod

# <<< CORRECCIÓN: Usar Any o tipos específicos en las firmas >>>
def set_config_dependency(config_module: Any): # Antes: 'cfg_mod'
    """Establece la dependencia del módulo config."""
    global _config
    _config = config_module
    print(f"DEBUG [Helper]: Dependencia Config establecida: {'Sí' if _config else 'No'}")

def set_utils_dependency(utils_module: Any): # Antes: 'ut_mod'
    """Establece la dependencia del módulo utils."""
    global _utils
    _utils = utils_module
    print(f"DEBUG [Helper]: Dependencia Utils establecida: {'Sí' if _utils else 'No'}")

def set_live_operations_dependency(live_ops_module: Optional[Any]): # Antes: Optional['lo_mod']
    """Establece la dependencia del módulo live_operations (puede ser None)."""
    global _live_operations
    _live_operations = live_ops_module
    print(f"DEBUG [Helper]: Dependencia Live Ops establecida: {'Sí' if _live_operations else 'No'}")


# --- Funciones Auxiliares ---

# <<< CORRECCIÓN: Usar Any o tipos específicos en las firmas >>>
def format_pos_for_summary(pos: Dict[str, Any], utils: Any) -> Dict[str, Any]: # Antes: utils: 'ut_mod'
    """Formatea un diccionario de posición lógica para el resumen JSON."""
    if not utils: # Fallback si utils no está disponible
         print("WARN [Helper Format Summary]: Módulo utils no disponible.")
         return pos # Devuelve la posición sin formatear

    try:
        entry_ts_str = utils.format_datetime(pos.get('entry_timestamp')) if pos.get('entry_timestamp') else "N/A"
        size_contracts = utils.safe_float_convert(pos.get('size_contracts'), default=0.0)

        # Definir precisión para el resumen
        price_prec_summary = 4 # Usar 4 decimales para precios en resumen
        qty_prec_summary = 8   # Usar 8 decimales para cantidad en resumen

        return {
            'id': str(pos.get('id', 'N/A'))[-6:], # Mostrar últimos 6 caracteres del ID (asegurar string)
            'entry_timestamp': entry_ts_str,
            'entry_price': round(utils.safe_float_convert(pos.get('entry_price'), 0.0), price_prec_summary),
            'margin_usdt': round(utils.safe_float_convert(pos.get('margin_usdt'), 0.0), 4),
            'size_contracts': round(size_contracts, qty_prec_summary),
            'take_profit_price': round(utils.safe_float_convert(pos.get('take_profit_price'), 0.0), price_prec_summary),
            'leverage': pos.get('leverage'), # Dejar leverage como está
            'api_order_id': pos.get('api_order_id') # Dejar order id como está
        }
    except Exception as e:
        print(f"ERROR [Helper Format Summary]: Formateando posición {pos.get('id', 'N/A')}: {e}")
        return {'id': pos.get('id', 'N/A')[-6:], 'error': f'Formato fallido: {e}'}


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
    global _config, _utils, _live_operations # Acceder a dependencias globales

    result = {'success': False, 'qty_float': 0.0, 'qty_str': "0.0", 'precision': 3, 'error': None}
    if not _config or not _utils:
        result['error'] = "Dependencias (config, utils) no disponibles en helper."
        # print(f"DEBUG: _config: {_config}, _utils: {_utils}") # Debug extra
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


    # --- Calcular Cantidad Raw ---
    size_contracts_raw = _utils.safe_division(margin_usdt * leverage, entry_price, default=0.0)
    if size_contracts_raw <= 1e-12: # Usar una tolerancia muy pequeña
        result['error'] = f"Cantidad calculada raw es 0 o negativa ({size_contracts_raw:.15f}). Margin: {margin_usdt}, Lev: {leverage}, Price: {entry_price}"
        return result

    # --- Obtener Precisión y Mínimo ---
    qty_precision = int(getattr(_config, 'DEFAULT_QTY_PRECISION', 3)) # Asegurar que sea int
    min_order_qty = float(getattr(_config, 'DEFAULT_MIN_ORDER_QTY', 0.001)) # Asegurar que sea float

    # Si es live, intentar obtener datos de la API
    if is_live and _live_operations and symbol:
         try:
             instrument_info = _live_operations.get_instrument_info(symbol)
             if instrument_info:
                 qty_step_str = instrument_info.get('qtyStep')
                 min_qty_str = instrument_info.get('minOrderQty')
                 # Intentar obtener precisión desde qtyStep si existe el helper en live_ops
                 if qty_step_str and hasattr(_live_operations, '_get_qty_precision_from_step'):
                     try:
                         qty_precision = _live_operations._get_qty_precision_from_step(qty_step_str)
                         # print(f"DEBUG [Helper Qty]: Precisión obtenida de helper: {qty_precision}") # Debug
                     except Exception as prec_err: print(f"WARN [Helper Qty]: Error calculando precisión desde qtyStep '{qty_step_str}': {prec_err}")
                 elif qty_step_str:
                      # Fallback si _get_qty_precision_from_step no existe pero qtyStep sí
                      try:
                          # Convertir a float y calcular decimales
                          step_val = float(qty_step_str)
                          if step_val > 0 and step_val < 1:
                              # Contar decimales (forma simple, puede fallar con notación científica)
                              if 'e-' in qty_step_str.lower():
                                   precision_e = int(qty_step_str.lower().split('e-')[-1])
                                   qty_precision = precision_e
                              elif '.' in qty_step_str:
                                   qty_precision = len(qty_step_str.split('.')[-1].rstrip('0'))
                              else: qty_precision = 0 # Si es '1', la precisión es 0
                          else: qty_precision = 0 # Si step >= 1, precisión es 0
                          # print(f"DEBUG [Helper Qty]: Precisión calculada manualmente: {qty_precision}") # Debug
                      except Exception as manual_prec_err:
                           print(f"WARN [Helper Qty]: Error calculando precisión manual desde qtyStep '{qty_step_str}': {manual_prec_err}")
                           # Mantener default si falla el parseo manual

                 if min_qty_str:
                     min_order_qty = _utils.safe_float_convert(min_qty_str, min_order_qty)
                     # print(f"DEBUG [Helper Qty]: Min Qty obtenido de API: {min_order_qty}") # Debug
         except Exception as api_info_err:
              print(f"WARN [Helper Qty]: Error obteniendo info instrumento API: {api_info_err}")
              # Continuar con los defaults de config

    result['precision'] = qty_precision # Guardar la precisión usada

    # --- Redondear ---
    try:
        size_contracts_decimal = Decimal(str(size_contracts_raw))
        rounding_factor = Decimal('1e-' + str(qty_precision))
        # Usar ROUND_DOWN para no exceder el margen disponible
        size_contracts_rounded = size_contracts_decimal.quantize(rounding_factor, rounding=ROUND_DOWN)
        size_contracts_final_float = float(size_contracts_rounded)
        size_contracts_str_api = str(size_contracts_rounded) # Convertir a string después de redondear

        # --- Verificar Mínimo ---
        # Asegurar que la comparación es entre floats
        if size_contracts_final_float < (float(min_order_qty) - 1e-9): # Comparación con tolerancia
            result['error'] = f"Cantidad redondeada ({size_contracts_str_api}) < mínimo ({min_order_qty})."
            return result

        result['success'] = True
        result['qty_float'] = size_contracts_final_float
        result['qty_str'] = size_contracts_str_api
        # print(f"DEBUG [Helper Qty]: Cálculo exitoso. Qty: {size_contracts_str_api}, Prec: {qty_precision}") # Debug
        return result

    except InvalidOperation as inv_op_err:
         result['error'] = f"Error de operación Decimal al redondear cantidad raw '{size_contracts_raw}' a {qty_precision} decimales: {inv_op_err}."
         return result
    except Exception as round_err:
        result['error'] = f"Excepción redondeando cantidad (raw={size_contracts_raw}, prec={qty_precision}): {round_err}"
        # Podríamos intentar devolver raw aquí, pero es más seguro fallar
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

    # --- Obtener Precisión ---
    qty_precision = int(getattr(_config, 'DEFAULT_QTY_PRECISION', 3)) # Asegurar int
    if is_live and _live_operations and symbol:
        try:
            instrument_info = _live_operations.get_instrument_info(symbol)
            if instrument_info:
                qty_step_str = instrument_info.get('qtyStep')
                if qty_step_str and hasattr(_live_operations, '_get_qty_precision_from_step'):
                    try: qty_precision = _live_operations._get_qty_precision_from_step(qty_step_str)
                    except Exception as prec_err: print(f"WARN [Helper Format Qty]: Error calculando precisión desde qtyStep '{qty_step_str}': {prec_err}")
                elif qty_step_str:
                     try: # Fallback manual
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

    # --- Formatear ---
    try:
        quantity_decimal = Decimal(str(quantity_float))
        rounding_factor = Decimal('1e-' + str(qty_precision))
        # Redondear (ROUND_DOWN es generalmente más seguro)
        # Asegurarse que quantize funciona correctamente
        quantity_rounded = quantity_decimal.quantize(rounding_factor, rounding=ROUND_DOWN)
        # Formatear a string con la precisión correcta, evitando notación científica si es posible
        # y asegurando que tenga los decimales correctos
        quantity_str_api = format(quantity_rounded, f'.{qty_precision}f')

        result['success'] = True
        result['qty_str'] = quantity_str_api
        # print(f"DEBUG [Helper Format Qty]: Formato exitoso. Qty: {quantity_str_api}, Prec: {qty_precision}") # Debug
        return result

    except InvalidOperation as inv_op_err:
         result['error'] = f"Error de operación Decimal al formatear cantidad '{quantity_float}' a {qty_precision} decimales: {inv_op_err}."
         return result
    except Exception as fmt_err:
        result['error'] = f"Excepción formateando cantidad (val={quantity_float}, prec={qty_precision}): {fmt_err}"
        return result

# <<< CORRECCIÓN: Usar Any o tipos específicos en las firmas >>>
def extract_physical_state_from_api(
    positions_raw: List[Dict[str, Any]],
    symbol: str,
    side: str,
    utils: Any # Antes: 'ut_mod'
) -> Optional[Dict[str, Any]]:
    """
    Extrae y calcula el estado físico agregado (tamaño, precio prom, margen, liq)
    de una lista de posiciones de la API para un lado específico.
    Devuelve un diccionario con el estado o None si no hay posiciones.
    """
    if not utils:
        print("ERROR [Helper Extract API]: Módulo utils no disponible.")
        return None

    # Bybit API v5 usa positionIdx=0 para modo One-Way, 1=Long/2=Short para Hedge
    # Asumimos que el modo correcto (Hedge o One-Way) está configurado en la cuenta Bybit.
    # Aquí usaremos el índice esperado para cada lado en MODO HEDGE como referencia principal.
    # Si se usa One-Way, positionIdx será 0 y necesitaremos filtrar por 'side'.
    # TODO: Considerar añadir una config global 'BYBIT_POSITION_MODE' ('HEDGE'/'ONEWAY')
    # Por ahora, intentaremos detectar One-Way si no encontramos por índice 1/2.

    pos_idx_target_hedge = 1 if side == 'long' else 2

    # Intentar filtrar por índice de Hedge Mode primero
    physical_positions_side = [
        p for p in positions_raw
        if p.get('symbol') == symbol and
           p.get('positionIdx') == pos_idx_target_hedge and
           utils.safe_float_convert(p.get('size'), 0.0) > 1e-12
    ]

    # Si no se encontraron por índice Hedge Y la lista original no estaba vacía,
    # intentar filtrar por índice 0 y 'side' (modo One-Way)
    if not physical_positions_side and positions_raw:
        side_target_oneway = 'Buy' if side == 'long' else 'Sell'
        physical_positions_side = [
            p for p in positions_raw
            if p.get('symbol') == symbol and
               p.get('positionIdx') == 0 and # Índice 0 para One-Way
               p.get('side') == side_target_oneway and # Filtrar por lado
               utils.safe_float_convert(p.get('size'), 0.0) > 1e-12
        ]
        if physical_positions_side:
             print(f"DEBUG [Helper Extract API]: Posición {side.upper()} encontrada usando filtro One-Way (idx=0, side={side_target_oneway}).")


    if not physical_positions_side:
        # print(f"DEBUG [Helper Extract API]: No se encontraron posiciones físicas para {symbol} lado {side.upper()}.")
        return None # No hay posiciones físicas para este lado

    try:
        # Calcular agregados
        real_total_size = sum(utils.safe_float_convert(p.get('size'), 0.0) for p in physical_positions_side)
        real_total_value = sum(utils.safe_float_convert(p.get('size'), 0.0) * utils.safe_float_convert(p.get('avgPrice'), 0.0) for p in physical_positions_side)
        real_avg_price = utils.safe_division(real_total_value, real_total_size, 0.0)

        # Calcular margen total (intentar IM, si no MM, si no 0)
        real_total_margin = sum(utils.safe_float_convert(p.get('positionIM', p.get('positionMM', 0.0)), 0.0) for p in physical_positions_side)

        # Obtener precio de liquidación (usar el de la primera entrada como representativo)
        # Puede ser None si la API no lo devuelve o si el valor es inválido/vacío
        real_liq_price_str = physical_positions_side[0].get('liqPrice')
        real_liq_price = utils.safe_float_convert(real_liq_price_str, None) if real_liq_price_str else None


        # Usar timestamp actual para la actualización
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


# =============== FIN ARCHIVO: core/strategy/_position_helpers.py (Corregido) ===============