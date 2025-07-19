# =============== INICIO ARCHIVO: core/live_operations.py (CORREGIDO FINAL) ===============
"""
Módulo para interactuar con la API de Bybit para ejecutar operaciones en vivo,
como colocar órdenes de mercado, establecer apalancamiento, y obtener información.
v8.5.3 - Integrado con memory_logger para reducir el ruido en la consola principal.
"""
import sys
import os
import traceback
from typing import Optional, Union, Dict, Any, List
import time
import datetime
from decimal import Decimal, ROUND_DOWN, InvalidOperation

# --- INICIO MODIFICACIÓN: Importar memory_logger ---
try:
    from core.logging import memory_logger
except ImportError:
    # Fallback si el módulo no se puede importar, para que el programa no se rompa.
    # Los logs simplemente se imprimirán en la consola.
    class MemoryLoggerFallback:
        def log(self, msg, level="INFO"): print(f"[{level}] {msg}")
    memory_logger = MemoryLoggerFallback()
# --- FIN MODIFICACIÓN ---

# Importar módulos necesarios de forma segura
try:
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if project_root not in sys.path: sys.path.insert(0, project_root)
    import config
    from core import utils
    from live.connection import manager as connection_manager
    try: from pybit.exceptions import InvalidRequestError, FailedRequestError
    except ImportError:
        print("WARN [Live Operations Import]: pybit exceptions not found. Using fallback.")
        class InvalidRequestError(Exception): pass
        class FailedRequestError(Exception):
             def __init__(self, message, status_code=None): super().__init__(message); self.status_code = status_code
except ImportError as e:
    print(f"ERROR [Live Operations Import]: No se pudo importar módulo necesario: {e}")
    config = type('obj', (object,), {'DEFAULT_QTY_PRECISION': 3, 'DEFAULT_MIN_ORDER_QTY': 0.001})()
    utils = None; connection_manager = None
    class InvalidRequestError(Exception): pass
    class FailedRequestError(Exception):
        def __init__(self, message, status_code=None): super().__init__(message); self.status_code = status_code
except Exception as e_imp:
     print(f"ERROR inesperado importando en live_operations: {e_imp}")
     config = type('obj', (object,), {'DEFAULT_QTY_PRECISION': 3, 'DEFAULT_MIN_ORDER_QTY': 0.001})()
     utils = None; connection_manager = None
     class InvalidRequestError(Exception): pass
     class FailedRequestError(Exception):
        def __init__(self, message, status_code=None): super().__init__(message); self.status_code = status_code

# --- Caché Simple para Instrument Info ---
_instrument_info_cache: Dict[str, Dict[str, Any]] = {}
_INSTRUMENT_INFO_CACHE_EXPIRY_SECONDS = 3600

# --- Funciones Auxiliares ---

def _get_qty_precision_from_step(step_str: str) -> int:
    """
    Calcula el número de decimales a partir del qtyStep usando el tipo Decimal
    para mayor robustez y precisión.
    """
    if not isinstance(step_str, str) or not step_str.strip():
        print(f"WARN [_get_qty_precision]: qtyStep inválido o vacío ('{step_str}'). Asumiendo 0 decimales.")
        return 0
    try:
        # Usar Decimal para manejar correctamente todos los formatos numéricos
        step_decimal = Decimal(step_str)

        # Si el valor no es finito (inf, nan) o es cero, no se puede determinar la precisión.
        if not step_decimal.is_finite():
            print(f"WARN [_get_qty_precision]: qtyStep no es un número finito ('{step_str}'). Asumiendo 0.")
            return 0

        # El exponente del Decimal nos da directamente el número de decimales.
        # ej. Decimal('0.001').as_tuple().exponent -> -3
        # ej. Decimal('10').as_tuple().exponent -> 1 (necesitamos 0 decimales)
        # ej. Decimal('1').as_tuple().exponent -> 0
        exponent = step_decimal.as_tuple().exponent
        if exponent < 0:
            return abs(exponent)
        else:
            return 0

    except InvalidOperation:
        print(f"WARN [_get_qty_precision]: No se pudo convertir qtyStep ('{step_str}') a Decimal. Asumiendo 0.")
        return 0

def _handle_api_error_generic(response: Optional[Dict], operation_tag: str) -> bool:
    """Maneja respuestas de error comunes de la API Bybit v5."""
    if response and response.get('retCode') == 0: return False
    ret_code = -1; ret_msg = "No Response"
    if response: ret_code = response.get('retCode', -1); ret_msg = response.get('retMsg', 'Unknown API Error')
    print(f"  ERROR API [{operation_tag}]: Código={ret_code}, Mensaje='{ret_msg}'")
    if ret_code == 110007 or ret_code == 180024: print("    -> Sugerencia: ¿Fondos/Margen insuficiente?")
    elif ret_code == 10001 or ret_code == 110017: print("    -> Sugerencia: ¿Error en parámetros?")
    elif ret_code == 110043: print("    -> Sugerencia: ¿Qty inválida / ReduceOnly / Apalancamiento ya seteado?")
    elif ret_code == 110041: print("    -> Sugerencia: ¿positionIdx vs modo?")
    elif ret_code == 180034: print("    -> Sugerencia: ¿Qty fuera límites?")
    elif ret_code == 110020: print("    -> Sugerencia: ¿Posición opuesta (One-Way)?")
    elif ret_code == 10006: print("    -> Sugerencia: ¿Error de Conexión / Timeout?")
    elif ret_code == 10002: print("    -> Sugerencia: ¿Parámetro Inválido?")
    elif ret_code == 110001: print("    -> Sugerencia: ¿Orden/Posición no encontrada?")
    return True # Hubo error

# --- Funciones de Obtención de Información ---

def get_instrument_info(symbol: str, category: str = 'linear', force_refresh: bool = False) -> Optional[Dict[str, Any]]:
    """Obtiene información del instrumento (precisión, mínimos) desde la API o caché."""
    global _instrument_info_cache
    if not connection_manager or not config: print("ERROR [Get Instrument Info]: Dependencias no disponibles."); return None
    cache_key = f"{category}_{symbol}"; now = time.time()
    if not force_refresh and cache_key in _instrument_info_cache:
        cached_data = _instrument_info_cache[cache_key]
        if (now - cached_data.get('timestamp', 0)) < _INSTRUMENT_INFO_CACHE_EXPIRY_SECONDS: return cached_data.get('data')
    session = None; account_used = None; main_account_fallback = getattr(config, 'ACCOUNT_MAIN', 'main')
    session = connection_manager.get_client(main_account_fallback)
    if session: account_used = main_account_fallback
    else:
        initialized_accounts = connection_manager.get_initialized_accounts()
        if not initialized_accounts: print("ERROR [Get Instrument Info]: No hay sesiones API inicializadas."); return None
        account_used = initialized_accounts[0]; session = connection_manager.get_client(account_used)
        if not session: print("ERROR [Get Instrument Info]: Falló al obtener sesión API alternativa."); return None
        print(f"WARN [Get Instrument Info]: Usando sesión de '{account_used}' (fallback).")
    memory_logger.log(f"Consultando API para {symbol} ({category}) usando '{account_used}'...")
    params = {"category": category, "symbol": symbol}
    try:
        if not hasattr(session, 'get_instruments_info'): print("ERROR Fatal [Get Instrument Info]: Sesión API no tiene método 'get_instruments_info'."); return None
        response = session.get_instruments_info(**params)
        if _handle_api_error_generic(response, f"Get Instrument Info for {symbol}"): return None
        else:
            result_list = response.get('result', {}).get('list', [])
            if result_list:
                instrument_data = result_list[0]; lot_size_filter = instrument_data.get('lotSizeFilter', {}); price_filter = instrument_data.get('priceFilter', {})
                extracted_info = { 'symbol': instrument_data.get('symbol'), 'qtyStep': lot_size_filter.get('qtyStep'), 'minOrderQty': lot_size_filter.get('minOrderQty'), 'maxOrderQty': lot_size_filter.get('maxOrderQty'), 'priceScale': instrument_data.get('priceScale'), 'tickSize': price_filter.get('tickSize') }
                if not extracted_info.get('qtyStep') or not extracted_info.get('minOrderQty'): print(f"WARN [Get Instrument Info]: Datos qtyStep/minOrderQty incompletos para {symbol}.")
                memory_logger.log(f"ÉXITO [Get Instrument Info]: Datos obtenidos para {symbol}.")
                _instrument_info_cache[cache_key] = {'timestamp': now, 'data': extracted_info}; return extracted_info
            else:
                memory_logger.log(f"INFO [Get Instrument Info]: Lista de instrumentos vacía para {symbol}.")
                return None
    except (InvalidRequestError, FailedRequestError) as api_err: status_code = getattr(api_err, 'status_code', 'N/A'); print(f"ERROR API [Get Instrument Info] para {symbol}: {api_err} (Status: {status_code})"); return None
    except Exception as e: print(f"ERROR Inesperado [Get Instrument Info] para {symbol}: {e}"); traceback.print_exc(); return None

# --- Funciones de Operaciones Live ---

def set_leverage(
    symbol: str,
    buy_leverage: Union[float, str],
    sell_leverage: Union[float, str],
    account_name: Optional[str] = None
) -> bool:
    """Establece el apalancamiento para un símbolo específico (v5 API)."""
    if not connection_manager or not config: print("ERROR [Set Leverage]: Dependencias no disponibles."); return False
    target_account = account_name
    if not target_account:
         acc_longs = getattr(config, 'ACCOUNT_LONGS', None); acc_shorts = getattr(config, 'ACCOUNT_SHORTS', None); main_acc = getattr(config, 'ACCOUNT_MAIN', 'main')
         if acc_longs and connection_manager.get_client(acc_longs): target_account = acc_longs
         elif acc_shorts and connection_manager.get_client(acc_shorts): target_account = acc_shorts
         else: target_account = main_acc
    session = connection_manager.get_client(target_account)
    if not session: print(f"ERROR [Set Leverage]: Sesión API no válida para '{target_account}'."); return False
    try: buy_lev_str = str(float(buy_leverage)); sell_lev_str = str(float(sell_leverage))
    except (ValueError, TypeError): print(f"ERROR [Set Leverage]: Apalancamiento inválido ({buy_leverage}, {sell_leverage})."); return False
    params = { "category": getattr(config, 'CATEGORY_LINEAR', 'linear'), "symbol": symbol, "buyLeverage": buy_lev_str, "sellLeverage": sell_lev_str, }
    memory_logger.log(f"Intentando establecer leverage para {symbol} en '{target_account}': Buy={buy_lev_str}x, Sell={sell_lev_str}x")
    try:
        if not hasattr(session, 'set_leverage'): print("ERROR Fatal [Set Leverage]: Sesión API no tiene método 'set_leverage'."); return False
        response = session.set_leverage(**params)
        if not _handle_api_error_generic(response, "Set Leverage"):
            memory_logger.log(f"ÉXITO [Set Leverage]: Apalancamiento establecido para {symbol}.")
            return True
        elif response and response.get('retCode') == 110043:
            memory_logger.log(f"INFO [Set Leverage]: Apalancamiento no modificado (ya estaba) - Código 110043.")
            return True
        else: return False
    except InvalidRequestError as invalid_req_err:
        error_message = str(invalid_req_err)
        if "110043" in error_message or "leverage not modified" in error_message.lower():
            memory_logger.log(f"INFO [Set Leverage]: Apalancamiento no modificado (ya estaba) - InvalidRequestError(110043).")
            return True
        else: print(f"ERROR API [Set Leverage] - Invalid Request: {invalid_req_err}"); return False
    except FailedRequestError as api_err:
        status_code = getattr(api_err, 'status_code', None)
        if status_code == 503: print(f"WARN [Set Leverage]: Received HTTP 503. Leverage MAY already be set. Continuing."); return True
        else: print(f"ERROR API [Set Leverage]: {api_err} (Status: {status_code})"); return False
    except Exception as e: print(f"ERROR Inesperado [Set Leverage]: {e}"); traceback.print_exc(); return False


def place_market_order(
    symbol: str,
    side: str,
    quantity: Union[float, str],
    reduce_only: bool = False,
    position_idx: Optional[int] = None,
    account_name: Optional[str] = None
) -> Optional[dict]:
    """
    Coloca una orden de mercado en Bybit (v5 API).
    Obtiene precisión y mínimo de la API y redondea/valida la cantidad.
    """
    if not connection_manager or not config: print("ERROR [Place Order]: Dependencias no disponibles."); return None
    if side not in ["Buy", "Sell"]: print(f"ERROR [Place Order]: Lado inválido '{side}'."); return None

    instrument_info = get_instrument_info(symbol)
    qty_precision = getattr(config, 'DEFAULT_QTY_PRECISION', 3); min_qty = getattr(config, 'DEFAULT_MIN_ORDER_QTY', 0.001)
    if instrument_info:
        qty_step_str = instrument_info.get('qtyStep'); min_qty_str = instrument_info.get('minOrderQty')
        if qty_step_str and min_qty_str:
            try: qty_precision = _get_qty_precision_from_step(qty_step_str); min_qty = float(min_qty_str)
            except (ValueError, TypeError) as e: print(f"WARN [Place Order]: Error procesando instrument info ({e}). Usando defaults.")
        else: print(f"WARN [Place Order]: Faltan datos en instrument info. Usando defaults.")
    else: print(f"WARN [Place Order]: No se pudo obtener instrument info. Usando defaults.")

    try:
        qty_float = float(quantity)
        if qty_float <= 1e-9: print(f"ERROR [Place Order]: Cantidad debe ser positiva '{quantity}'."); return None
        qty_decimal = Decimal(str(qty_float)); rounding_factor = Decimal('1e-' + str(qty_precision)); qty_rounded = qty_decimal.quantize(rounding_factor, rounding=ROUND_DOWN); qty_str_api = str(qty_rounded)
        if qty_rounded < Decimal(str(min_qty)):
            if not reduce_only: print(f"ERROR [Place Order]: Cantidad redondeada ({qty_str_api}) < mínimo ({min_qty})."); return None
            else: print(f"WARN [Place Order]: Cantidad de cierre ({qty_str_api}) < mínimo ({min_qty}), pero permitido por reduce_only=True.")
    except (ValueError, TypeError, InvalidOperation) as e: print(f"ERROR [Place Order]: Cantidad inválida o error de redondeo '{quantity}': {e}."); return None

    target_account = account_name if account_name else getattr(config, 'ACCOUNT_MAIN', 'main')
    session = connection_manager.get_client(target_account)
    if not session: print(f"ERROR [Place Order]: No se pudo obtener sesión API válida para '{target_account}'."); return None

    params = { "category": getattr(config, 'CATEGORY_LINEAR', 'linear'), "symbol": symbol, "side": side, "orderType": "Market", "qty": qty_str_api, "reduceOnly": bool(reduce_only) }
    is_hedge_mode = getattr(config, 'BYBIT_HEDGE_MODE_ENABLED', True)
    if is_hedge_mode:
        if position_idx is None: position_idx = 1 if side == "Buy" else 2
        elif position_idx not in [1, 2]: print(f"ERROR [Place Order]: position_idx ({position_idx}) inválido para modo Hedge (debe ser 1 o 2)."); return None
        params["positionIdx"] = position_idx
    else: params["positionIdx"] = 0

    memory_logger.log(f"Enviando orden MARKET a cuenta '{target_account}': {params}")
    try:
        if not hasattr(session, 'place_order'): print("ERROR Fatal [Place Order]: Sesión API no tiene método 'place_order'."); return None
        response = session.place_order(**params)
        if not _handle_api_error_generic(response, "Place Order"):
            order_id = response.get('result', {}).get('orderId', 'N/A')
            memory_logger.log(f"ÉXITO [Place Order]: Orden aceptada API. OrderID: {order_id}")
            return response
        else: return response
    except (InvalidRequestError, FailedRequestError) as api_err: status_code = getattr(api_err, 'status_code', 'N/A'); print(f"ERROR API [Place Order]: {api_err} (Status: {status_code})"); return None
    except Exception as e: print(f"ERROR Inesperado [Place Order]: {e}"); traceback.print_exc(); return None


# --- Funciones para Obtener Balances ---

def get_unified_account_balance_info(account_name: str) -> Optional[dict]:
    """Obtiene detalles del balance de la Cuenta Unificada (UTA)."""
    if not connection_manager or not config or not utils: print("ERROR [Get Unified Balance]: Dependencias no disponibles."); return None
    session = connection_manager.get_client(account_name)
    if not session: print(f"ERROR [Get Unified Balance]: Sesión API no válida para '{account_name}'."); return None
    memory_logger.log(f"Obteniendo balance UNIFIED para '{account_name}'...")
    try:
        if not hasattr(session, 'get_wallet_balance'): print("ERROR Fatal [Get Unified Balance]: Sesión API no tiene método 'get_wallet_balance'."); return None
        response = session.get_wallet_balance(accountType="UNIFIED")
        if _handle_api_error_generic(response, f"Get Unified Balance for {account_name}"): return None
        else:
            result_list = response.get('result', {}).get('list', [])
            if not result_list:
                memory_logger.log(f"INFO [Get Unified Balance]: Sin datos para '{account_name}'.")
                return {'totalEquity': 0.0, 'totalAvailableBalance': 0.0, 'totalWalletBalance': 0.0, 'usdt_balance': 0.0, 'usdt_available': 0.0}
            account_data = result_list[0]
            balance_info = { 'totalEquity': utils.safe_float_convert(account_data.get('totalEquity'), 0.0), 'totalAvailableBalance': utils.safe_float_convert(account_data.get('totalAvailableBalance'), 0.0), 'totalWalletBalance': utils.safe_float_convert(account_data.get('totalWalletBalance'), 0.0), 'usdt_balance': 0.0, 'usdt_available': 0.0 }
            coins_data = account_data.get('coin', [])
            usdt_data = next((coin for coin in coins_data if coin.get('coin') == 'USDT'), None)
            if usdt_data: balance_info['usdt_balance'] = utils.safe_float_convert(usdt_data.get('walletBalance'), 0.0); balance_info['usdt_available'] = utils.safe_float_convert(usdt_data.get('availableToWithdraw', usdt_data.get('walletBalance')), 0.0) # Fallback
            memory_logger.log(f"ÉXITO [Get Unified Balance]: Balance obtenido para '{account_name}'.")
            return balance_info
    except (InvalidRequestError, FailedRequestError) as api_err: status_code = getattr(api_err, 'status_code', 'N/A'); print(f"ERROR API [Get Unified Balance] para '{account_name}': {api_err} (Status: {status_code})"); return None
    except Exception as e: print(f"ERROR Inesperado [Get Unified Balance] para '{account_name}': {e}"); traceback.print_exc(); return None


def get_funding_account_balance_info(account_name: str) -> Optional[Dict[str, Dict[str, float]]]:
    """Obtiene detalles del balance de la Cuenta de Fondos (FUND)."""
    if not connection_manager or not config or not utils: print("ERROR [Get Funding Balance]: Dependencias no disponibles."); return None
    session = connection_manager.get_client(account_name)
    if not session: print(f"ERROR [Get Funding Balance]: Sesión API no válida para '{account_name}'."); return None
    memory_logger.log(f"Obteniendo balance FUND para '{account_name}'...")
    try:
        if not hasattr(session, 'get_coins_balance'): print("ERROR Fatal [Get Funding Balance]: Sesión API no tiene método 'get_coins_balance'."); return None
        response = session.get_coins_balance(accountType="FUND")
        funding_balances = {}
        if _handle_api_error_generic(response, f"Get Funding Balance for {account_name}"): return None
        else:
            balance_list = response.get('result', {}).get('balance', [])
            if balance_list:
                for coin_data in balance_list: coin_symbol = coin_data.get('coin'); wallet_balance = utils.safe_float_convert(coin_data.get('walletBalance'), 0.0);
                if coin_symbol and wallet_balance > 1e-9: funding_balances[coin_symbol] = {'walletBalance': wallet_balance}
                memory_logger.log(f"ÉXITO [Get Funding Balance]: Balances obtenidos para '{account_name}'. {len(funding_balances)} activo(s).")
            else:
                memory_logger.log(f"INFO [Get Funding Balance]: Sin datos de balance para '{account_name}'.")
            return funding_balances
    except (InvalidRequestError, FailedRequestError) as api_err: status_code = getattr(api_err, 'status_code', 'N/A'); print(f"ERROR API [Get Funding Balance] para '{account_name}': {api_err} (Status: {status_code})"); return None
    except Exception as e: print(f"ERROR Inesperado [Get Funding Balance] para '{account_name}': {e}"); traceback.print_exc(); return None


# --- Funciones para Órdenes y Posiciones ---

def cancel_order( symbol: str, order_id: Optional[str] = None, order_link_id: Optional[str] = None, account_name: Optional[str] = None) -> Optional[dict]:
    """Cancela una orden específica en Bybit (v5 API)."""
    if not connection_manager or not config: print("ERROR [Cancel Order]: Dependencias no disponibles."); return None
    if not order_id and not order_link_id: print("ERROR [Cancel Order]: Debe proporcionar order_id o order_link_id."); return None
    target_account = account_name if account_name else getattr(config, 'ACCOUNT_MAIN', 'main'); session = connection_manager.get_client(target_account)
    if not session: target_account = getattr(config, 'ACCOUNT_MAIN', 'main'); session = connection_manager.get_client(target_account)
    if not session: print(f"ERROR [Cancel Order]: Sesión API no válida."); return None
    params = {"category": getattr(config, 'CATEGORY_LINEAR', 'linear'), "symbol": symbol,}; id_type = ""
    if order_id: params["orderId"] = order_id; id_type = f"ID={order_id}"
    elif order_link_id: params["orderLinkId"] = order_link_id; id_type = f"LinkID={order_link_id}"
    memory_logger.log(f"Intentando cancelar orden {id_type} para {symbol} en '{target_account}'...")
    try:
        if not hasattr(session, 'cancel_order'): print("ERROR Fatal [Cancel Order]: Sesión API no tiene método 'cancel_order'."); return None
        response = session.cancel_order(**params)
        if not _handle_api_error_generic(response, f"Cancel Order {id_type}"):
            canceled_id = response.get('result', {}).get('orderId') or response.get('result', {}).get('orderLinkId', 'N/A')
            memory_logger.log(f"ÉXITO [Cancel Order]: Cancelación aceptada para orden {canceled_id}.")
            return response
        elif response and response.get('retCode') == 110001:
            memory_logger.log(f"INFO [Cancel Order]: Orden {id_type} no encontrada o ya finalizada (110001).", level="WARN")
            return None
        else: return response
    except (InvalidRequestError, FailedRequestError) as api_err: status_code = getattr(api_err, 'status_code', 'N/A'); print(f"ERROR API [Cancel Order]: {api_err} (Status: {status_code})"); return None
    except Exception as e: print(f"ERROR Inesperado [Cancel Order]: {e}"); traceback.print_exc(); return None


def get_order_status( symbol: str, order_id: Optional[str] = None, order_link_id: Optional[str] = None, account_name: Optional[str] = None) -> Optional[dict]:
    """Obtiene el estado de una orden específica usando get_order_history (v5 API)."""
    if not connection_manager or not config: print("ERROR [Get Order Status]: Dependencias no disponibles."); return None
    if not order_id and not order_link_id: print("ERROR [Get Order Status]: Debe proporcionar order_id o order_link_id."); return None
    target_account = account_name if account_name else getattr(config, 'ACCOUNT_MAIN', 'main'); session = connection_manager.get_client(target_account)
    if not session: target_account = getattr(config, 'ACCOUNT_MAIN', 'main'); session = connection_manager.get_client(target_account)
    if not session: print(f"ERROR [Get Order Status]: Sesión API no válida."); return None
    params = {"category": getattr(config, 'CATEGORY_LINEAR', 'linear'), "limit": 1,}; id_type = ""
    if order_id: params["orderId"] = order_id; id_type = f"ID={order_id}"
    elif order_link_id: params["orderLinkId"] = order_link_id; id_type = f"LinkID={order_link_id}"
    memory_logger.log(f"Buscando estado orden {id_type} en '{target_account}'...")
    try:
        if not hasattr(session, 'get_order_history'): print("ERROR Fatal [Get Order Status]: Sesión API no tiene método 'get_order_history'."); return None
        response = session.get_order_history(**params)
        if _handle_api_error_generic(response, f"Get Order Status {id_type}"): return None
        else:
            order_list = response.get('result', {}).get('list', [])
            if order_list:
                order_details = order_list[0]; found_id = order_details.get('orderId'); found_link_id = order_details.get('orderLinkId')
                if (order_id and found_id == order_id) or (order_link_id and found_link_id == order_link_id):
                    memory_logger.log(f"ÉXITO [Get Order Status]: Orden {id_type} encontrada. Estado: {order_details.get('orderStatus', 'N/A')}")
                    return order_details
                else:
                    memory_logger.log(f"INFO [Get Order Status]: Orden encontrada ({found_id}/{found_link_id}) no coincide con buscada ({id_type}).")
                    return None
            else:
                memory_logger.log(f"INFO [Get Order Status]: Orden {id_type} no encontrada.")
                return None
    except (InvalidRequestError, FailedRequestError) as api_err: status_code = getattr(api_err, 'status_code', 'N/A'); print(f"ERROR API [Get Order Status]: {api_err} (Status: {status_code})"); return None
    except Exception as e: print(f"ERROR Inesperado [Get Order Status]: {e}"); traceback.print_exc(); return None


def get_active_position_details_api(symbol: str, account_name: Optional[str] = None) -> Optional[List[dict]]:
    """Obtiene detalles de la(s) posición(es) activas para un símbolo (v5 API)."""
    if not connection_manager or not config or not utils: print("ERROR [Get Position]: Dependencias no disponibles."); return None
    target_account = account_name if account_name else getattr(config, 'ACCOUNT_MAIN', 'main'); session = connection_manager.get_client(target_account)
    if not session: target_account = getattr(config, 'ACCOUNT_MAIN', 'main'); session = connection_manager.get_client(target_account)
    if not session: print(f"ERROR [Get Position]: Sesión API no válida."); return None
    params = {"category": getattr(config, 'CATEGORY_LINEAR', 'linear'), "symbol": symbol,}
    memory_logger.log(f"Obteniendo detalles de posición para {symbol} en '{target_account}'...")
    try:
        if not hasattr(session, 'get_positions'): print("ERROR Fatal [Get Position]: Sesión API no tiene método 'get_positions'."); return None
        response = session.get_positions(**params)
        if _handle_api_error_generic(response, f"Get Position for {symbol}"): return None
        else:
            position_list = response.get('result', {}).get('list', [])
            if position_list:
                active_positions = [pos for pos in position_list if utils.safe_float_convert(pos.get('size'), 0.0) > 1e-12]
                if active_positions:
                    memory_logger.log(f"ÉXITO [Get Position]: {len(active_positions)} posición(es) activa(s) encontrada(s) para {symbol}.")
                    return active_positions
                else:
                    memory_logger.log(f"INFO [Get Position]: No hay posiciones activas para {symbol}.")
                    return []
            else:
                memory_logger.log(f"INFO [Get Position]: Lista de posiciones vacía para {symbol}.")
                return []
    except (InvalidRequestError, FailedRequestError) as api_err: status_code = getattr(api_err, 'status_code', 'N/A'); print(f"ERROR API [Get Position]: {api_err} (Status: {status_code})"); return None
    except Exception as e: print(f"ERROR Inesperado [Get Position]: {e}"); traceback.print_exc(); return None

# --- NUEVA FUNCIÓN: Cerrar Todas las Posiciones ---

def close_all_symbol_positions(symbol: str, account_name: Optional[str] = None) -> bool:
    """
    Intenta cerrar todas las posiciones activas (Long y Short) para un símbolo específico
    en una cuenta determinada. Usa la información del instrumento para validar cantidad.
    """
    if not connection_manager or not config or not utils: print("ERROR [Close All Positions]: Dependencias no disponibles."); return False
    target_account = account_name if account_name else getattr(config, 'ACCOUNT_MAIN', 'main'); session = connection_manager.get_client(target_account)
    if not session:
        if account_name and account_name != getattr(config, 'ACCOUNT_MAIN', 'main'): target_account = getattr(config, 'ACCOUNT_MAIN', 'main'); session = connection_manager.get_client(target_account)
    if not session: print(f"ERROR [Close All Positions]: Sesión API no válida para '{target_account}'."); return False
    memory_logger.log(f"Intentando cerrar TODAS las posiciones para {symbol} en cuenta '{target_account}'...")

    instrument_info = get_instrument_info(symbol)
    qty_precision = getattr(config, 'DEFAULT_QTY_PRECISION', 3); min_qty = getattr(config, 'DEFAULT_MIN_ORDER_QTY', 0.001)
    if instrument_info:
        qty_step_str = instrument_info.get('qtyStep'); min_qty_str = instrument_info.get('minOrderQty')
        try: qty_precision = _get_qty_precision_from_step(qty_step_str) if qty_step_str else qty_precision; min_qty = float(min_qty_str) if min_qty_str else min_qty
        except (ValueError, TypeError): print(f"WARN [Close All Positions]: Error procesando instrument info. Usando defaults.")
    else: print(f"WARN [Close All Positions]: No se pudo obtener instrument info. Usando defaults.")
    memory_logger.log(f"DEBUG [Close All Positions]: Usando Precision={qty_precision}, Min Qty={min_qty}", level="DEBUG")

    active_positions = get_active_position_details_api(symbol=symbol, account_name=target_account)
    if active_positions is None: print(f"  ERROR [Close All Positions]: No se pudieron obtener posiciones."); return False
    if not active_positions:
        memory_logger.log(f"INFO [Close All Positions]: No hay posiciones activas para {symbol}.")
        return True

    all_close_attempts_made = True
    for pos in active_positions:
        pos_side = pos.get('side'); pos_size_str = pos.get('size', '0'); pos_idx = pos.get('positionIdx', 0)
        try:
            pos_size_float = float(pos_size_str)
            if not pos_side or pos_size_float < float(min_qty):
                memory_logger.log(f"Saltando pos inválida/pequeña (<{min_qty}): {pos}", level="WARN")
                continue
        except (ValueError, TypeError):
            print(f"WARN [Close All Positions]: Error convirtiendo tamaño {pos_size_str}. Saltando.")
            continue
        close_order_side = "Sell" if pos_side == "Buy" else "Buy"
        try:
             qty_decimal = Decimal(pos_size_str); rounding_factor = Decimal('1e-' + str(qty_precision)); qty_rounded = qty_decimal.quantize(rounding_factor, rounding=ROUND_DOWN); qty_to_close_str = str(qty_rounded)
             if qty_rounded <= Decimal(0):
                 print(f"WARN [Close All Positions]: Cantidad redondeada a cero para {pos_size_str}. Saltando.")
                 all_close_attempts_made = False
                 continue
        except Exception as e: print(f"  ERROR [Close All Positions]: Falló formateo qty {pos_size_str}: {e}. Saltando."); all_close_attempts_made = False; continue
        memory_logger.log(f"-> Intentando cerrar {pos_side} PosIdx={pos_idx} (Tamaño API: {qty_to_close_str})...")
        close_response = place_market_order( symbol=symbol, side=close_order_side, quantity=qty_to_close_str, reduce_only=True, position_idx=pos_idx, account_name=target_account )
        if not close_response or close_response.get('retCode') != 0:
            print(f"  -> FALLO al intentar cerrar {pos_side} PosIdx={pos_idx}.")
            all_close_attempts_made = False

    if all_close_attempts_made:
        memory_logger.log(f"INFO [Close All Positions]: Se intentó cerrar todas las posiciones para {symbol} en '{target_account}'.")
    else: print(f"WARN [Close All Positions]: Fallaron algunos intentos de cierre para {symbol}. Verifica logs.")
    return all_close_attempts_made


def close_position_by_side(symbol: str, side_to_close: str, account_name: Optional[str] = None) -> bool:
    """
    Intenta cerrar la posición activa para un lado específico (Buy para Long, Sell para Short)
    para un símbolo en una cuenta determinada.
    """
    if not connection_manager or not config or not utils: print("ERROR [Close Position By Side]: Dependencias no disponibles."); return False
    if side_to_close not in ["Buy", "Sell"]: print(f"ERROR [Close Position By Side]: Lado inválido '{side_to_close}'."); return False
    target_account = account_name if account_name else getattr(config, 'ACCOUNT_MAIN', 'main'); session = connection_manager.get_client(target_account)
    if not session:
        if account_name and account_name != getattr(config, 'ACCOUNT_MAIN', 'main'): target_account = getattr(config, 'ACCOUNT_MAIN', 'main'); session = connection_manager.get_client(target_account)
    if not session: print(f"ERROR [Close Position By Side]: Sesión API no válida para '{target_account}'."); return False
    memory_logger.log(f"Buscando posición {side_to_close} para {symbol} en cuenta '{target_account}'...")

    instrument_info = get_instrument_info(symbol)
    qty_precision = getattr(config, 'DEFAULT_QTY_PRECISION', 3); min_qty = getattr(config, 'DEFAULT_MIN_ORDER_QTY', 0.001)
    if instrument_info:
        qty_step_str = instrument_info.get('qtyStep'); min_qty_str = instrument_info.get('minOrderQty')
        try: qty_precision = _get_qty_precision_from_step(qty_step_str) if qty_step_str else qty_precision; min_qty = float(min_qty_str) if min_qty_str else min_qty
        except (ValueError, TypeError): print(f"WARN [Close Position By Side]: Error procesando info instrumento. Usando defaults.")
    else: print(f"WARN [Close Position By Side]: No se pudo obtener info instrumento. Usando defaults.")

    active_positions = get_active_position_details_api(symbol=symbol, account_name=target_account)
    if active_positions is None: print(f"  ERROR [Close Position By Side]: No se pudieron obtener posiciones."); return False

    position_to_close = None
    for pos in active_positions:
        if pos.get('side') == side_to_close: position_to_close = pos; break
    if not position_to_close:
        memory_logger.log(f"INFO [Close Position By Side]: No se encontró posición activa del lado '{side_to_close}'.")
        return True

    pos_size_str = position_to_close.get('size', '0'); pos_idx = position_to_close.get('positionIdx', 0);
    close_order_side = "Sell" if side_to_close == "Buy" else "Buy"
    try:
        pos_size_float = float(pos_size_str)
        qty_decimal = Decimal(pos_size_str); rounding_factor = Decimal('1e-' + str(qty_precision)); qty_rounded = qty_decimal.quantize(rounding_factor, rounding=ROUND_DOWN); qty_to_close_str = str(qty_rounded)
        if qty_rounded <= Decimal(0): print(f"  ERROR [Close Position By Side]: Cantidad redondeada a cero para {pos_size_str}."); return False
    except (ValueError, TypeError, InvalidOperation) as e: print(f"  ERROR [Close Position By Side]: Error procesando tamaño '{pos_size_str}': {e}"); return False

    memory_logger.log(f"-> Intentando cerrar {side_to_close} PosIdx={pos_idx} (Tamaño API: {qty_to_close_str})...")
    close_response = place_market_order( symbol=symbol, side=close_order_side, quantity=qty_to_close_str, reduce_only=True, position_idx=pos_idx, account_name=target_account )
    if close_response and close_response.get('retCode') == 0:
        memory_logger.log(f"ÉXITO [Close Position By Side]: Orden de cierre para {side_to_close} enviada.")
        return True
    else:
        print(f"  FALLO [Close Position By Side]: No se pudo enviar orden de cierre para {side_to_close}.")
        return False


def get_order_execution_history(category: str, symbol: str, order_id: str, limit: int = 50) -> Optional[List[Dict[str, Any]]]:
    """
    Obtiene el historial de ejecuciones (trades) para una orden específica (v5 API).
    """
    if not connection_manager: print("ERROR [Get Executions]: Connection manager no disponible."); return None
    session = None
    if config:
         session = connection_manager.get_client(getattr(config, 'ACCOUNT_MAIN', 'main'))
    if not session: print("ERROR [Get Executions]: No se pudo obtener sesión API."); return None
    if not hasattr(session, 'get_executions'): print("ERROR Fatal [Get Executions]: Sesión API no tiene método 'get_executions'."); return None

    params = {
        "category": category,
        "symbol": symbol,
        "orderId": order_id,
        "limit": min(limit, 100)
    }
    memory_logger.log(f"Consultando API para ejecuciones de Orden ID: {order_id}...", level="DEBUG")
    try:
        response = session.get_executions(**params)
        if _handle_api_error_generic(response, f"Get Executions for Order {order_id}"):
            if response and response.get('retCode') == 110001:
                 memory_logger.log(f"INFO [Get Executions]: Orden {order_id} no encontrada (110001).")
                 return []
            return []
        else:
            executions_list = response.get('result', {}).get('list', [])
            memory_logger.log(f"ÉXITO [Get Executions]: {len(executions_list)} ejecuciones encontradas para Orden ID {order_id}.")
            return executions_list

    except (InvalidRequestError, FailedRequestError) as api_err:
        status_code = getattr(api_err, 'status_code', 'N/A')
        print(f"ERROR API [Get Executions] para orden {order_id}: {api_err} (Status: {status_code})")
        return None
    except Exception as e:
        print(f"ERROR Inesperado [Get Executions] para orden {order_id}: {e}")
        traceback.print_exc()
        return None

# =============== FIN ARCHIVO: core/live_operations.py (CORREGIDO FINAL) ===============