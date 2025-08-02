"""
Implementación del Adaptador de Exchange para Bybit.

v2.3 (Refactor de Configuración):
- Adaptado para leer la configuración desde los nuevos diccionarios
  anidados en `config.py`.

v2.2 (Validación de Símbolo):
- El método `initialize` ahora valida activamente que el símbolo proporcionado
  exista en el exchange llamando a `get_instrument_info`.

v2.1 (Refactor Connection Layer):
- El constructor __init__ ahora recibe una instancia de ConnectionManager.
- Todos los métodos que necesitaban una sesión API ahora la obtienen a través de
  de la instancia self._connection_manager, eliminando la dependencia del módulo global.

v2.0: Implementa el manejo de cuentas con propósito y transferencias.
"""
import time
import uuid
import datetime
from typing import List, Optional, Tuple, TYPE_CHECKING

# --- Dependencias del Proyecto ---
from core import api as bybit_api, utils
from core.logging import memory_logger
import config
from ._interface import AbstractExchange
from ._models import StandardOrder, StandardPosition, StandardBalance, StandardInstrumentInfo, StandardTicker

if TYPE_CHECKING:
    from connection import ConnectionManager

try:
    from pybit.exceptions import InvalidRequestError, FailedRequestError
except ImportError:
    class InvalidRequestError(Exception): pass
    class FailedRequestError(Exception): pass

class BybitAdapter(AbstractExchange):
    """Implementación del protocolo de Exchange para Bybit."""

    def __init__(self, connection_manager: 'ConnectionManager'):
        """
        Inicializa el adaptador con una instancia del gestor de conexiones.
        """
        self._connection_manager = connection_manager
        self._symbol: Optional[str] = None
        self._latest_price: Optional[float] = None
        # --- INICIO DE LA MODIFICACIÓN (Adaptación a Nueva Estructura) ---
        # Mapeo de propósito a nombre de cuenta de config.py
        # --- (COMENTADO) ---
        # self._purpose_to_account_name_map = {
        #     'main': config.ACCOUNT_MAIN,
        #     'longs': config.ACCOUNT_LONGS,
        #     'shorts': config.ACCOUNT_SHORTS,
        #     'profit': config.ACCOUNT_PROFIT,
        #     'ticker': config.TICKER_SOURCE_ACCOUNT
        # }
        # --- (CORREGIDO) ---
        self._purpose_to_account_name_map = {
            'main': config.BOT_CONFIG["ACCOUNTS"]["MAIN"],
            'longs': config.BOT_CONFIG["ACCOUNTS"]["LONGS"],
            'shorts': config.BOT_CONFIG["ACCOUNTS"]["SHORTS"],
            'profit': config.BOT_CONFIG["ACCOUNTS"]["PROFIT"],
            'ticker': config.BOT_CONFIG["TICKER"]["SOURCE_ACCOUNT"]
        }
        # --- FIN DE LA MODIFICACIÓN ---


    def initialize(self, symbol: str) -> bool:
        """
        Inicializa el adaptador, verifica la conexión a las cuentas necesarias y
        valida que el símbolo de trading exista en el exchange.
        """
        initialized_accounts = self._connection_manager.get_initialized_accounts()
        required_accounts = set(self._purpose_to_account_name_map.values())
        
        if not required_accounts.issubset(set(initialized_accounts)):
            missing = required_accounts - set(initialized_accounts)
            memory_logger.log(f"[BybitAdapter] ERROR: Faltan cuentas requeridas en la conexión: {missing}", "ERROR")
            return False

        # Validación activa del símbolo.
        memory_logger.log(f"[BybitAdapter] Validando existencia del símbolo '{symbol}'...", "INFO")
        instrument_info = self.get_instrument_info(symbol)
        if instrument_info is None:
            memory_logger.log(f"[BybitAdapter] ERROR: El símbolo '{symbol}' no es válido o no se pudo obtener su información.", "ERROR")
            return False

        self._symbol = symbol
        memory_logger.log(f"[BybitAdapter] Inicializado con éxito para el símbolo '{symbol}'.", "INFO")
        return True

    def get_instrument_info(self, symbol: str) -> Optional[StandardInstrumentInfo]:
        bybit_info = bybit_api.get_instrument_info(symbol)
        if not bybit_info: return None
        try:
            qty_step = utils.safe_float_convert(bybit_info.get('qtyStep'), 0.001)
            qty_precision = 0
            if '.' in str(qty_step):
                # Usar Decimal para un cálculo de precisión más robusto
                from decimal import Decimal
                qty_precision = abs(Decimal(str(qty_step)).as_tuple().exponent)

            return StandardInstrumentInfo(
                symbol=bybit_info.get('symbol'),
                price_precision=int(utils.safe_float_convert(bybit_info.get('priceScale'), 4)),
                quantity_precision=qty_precision,
                min_order_size=utils.safe_float_convert(bybit_info.get('minOrderQty'), 0.001),
                max_order_size=utils.safe_float_convert(bybit_info.get('maxOrderQty'), 100000.0),
                qty_step=qty_step
            )
        except Exception as e:
            memory_logger.log(f"[BybitAdapter] Error traduciendo instrument info: {e}", "ERROR")
            return None

    def get_balance(self, account_purpose: str) -> Optional[StandardBalance]:
        account_name = self._purpose_to_account_name_map.get(account_purpose)
        if not account_name: return None
        
        balance_info = bybit_api.get_unified_account_balance_info(account_name)
        if not balance_info: return None
        
        return StandardBalance(
            total_equity_usd=utils.safe_float_convert(balance_info.get('totalEquity')),
            available_balance_usd=utils.safe_float_convert(balance_info.get('totalAvailableBalance'))
        )

    def get_positions(self, symbol: str, account_purpose: str) -> List[StandardPosition]:
        account_name = self._purpose_to_account_name_map.get(account_purpose)
        if not account_name: return []
        
        api_positions = bybit_api.get_active_position_details_api(symbol, account_name)
        if api_positions is None: return []

        standard_positions = []
        for pos in api_positions:
            side = 'long' if pos.get('side') == 'Buy' else 'short'
            standard_pos = StandardPosition(
                symbol=pos.get('symbol'), side=side,
                size_contracts=utils.safe_float_convert(pos.get('size')),
                avg_entry_price=utils.safe_float_convert(pos.get('avgPrice')),
                liquidation_price=utils.safe_float_convert(pos.get('liqPrice')),
                unrealized_pnl=utils.safe_float_convert(pos.get('unrealisedPnl')),
                margin_usd=utils.safe_float_convert(pos.get('positionIM'))
            )
            standard_positions.append(standard_pos)
        return standard_positions
        
    def get_ticker(self, symbol: str) -> Optional[StandardTicker]:
        account_name = self._purpose_to_account_name_map.get('ticker')
        session, _ = self._connection_manager.get_session_for_operation('general', specific_account=account_name)
        if not session: return None
        
        # --- INICIO DE LA MODIFICACIÓN (Adaptación a Nueva Estructura) ---
        # --- (COMENTADO) ---
        # category = getattr(config, 'CATEGORY_LINEAR', 'linear')
        # --- (CORREGIDO) ---
        category = config.EXCHANGE_CONSTANTS["BYBIT"]["CATEGORY_LINEAR"]
        # --- FIN DE LA MODIFICACIÓN ---
        
        try:
            response = session.get_tickers(category=category, symbol=symbol)
            
            if not response or response.get('retCode') != 0: 
                if response:
                    msg = response.get('retMsg', 'Error desconocido')
                    code = response.get('retCode', -1)
                    memory_logger.log(f"[BybitAdapter get_ticker] Error API para '{symbol}': {msg} (Code: {code})", "WARN")
                return None
            
            ticker_data_list = response.get('result', {}).get('list', [])
            if not ticker_data_list:
                return None
                
            ticker_data = ticker_data_list[0]
            price = utils.safe_float_convert(ticker_data.get('lastPrice'))
            
            if price and price > 0:
                self._latest_price = price
                return StandardTicker(timestamp=datetime.datetime.now(datetime.timezone.utc), symbol=symbol, price=price)
            
            return None

        except (InvalidRequestError, FailedRequestError) as api_err:
            memory_logger.log(f"[BybitAdapter get_ticker] Excepción API para '{symbol}': {api_err}", "ERROR")
            return None
        except (IndexError, TypeError, KeyError) as e:
            memory_logger.log(f"[BybitAdapter get_ticker] Error parseando respuesta para '{symbol}': {e}", "WARN")
            return None

    def place_order(self, order: StandardOrder, account_purpose: str) -> Tuple[bool, str]:
        account_name = self._purpose_to_account_name_map.get(account_purpose)
        if not account_name: return False, f"Propósito de cuenta desconocido: '{account_purpose}'"

        # --- INICIO DE LA MODIFICACIÓN (Adaptación a Nueva Estructura) ---
        # --- (COMENTADO) ---
        # is_hedge_mode = getattr(config, 'BYBIT_HEDGE_MODE_ENABLED', True)
        # --- (CORREGIDO) ---
        is_hedge_mode = config.EXCHANGE_CONSTANTS["BYBIT"]["HEDGE_MODE_ENABLED"]
        # --- FIN DE LA MODIFICACIÓN ---
        pos_idx = 0
        if is_hedge_mode:
            side_map = {'buy': 'long', 'sell': 'short'}
            pos_idx = 1 if side_map.get(order.side.lower()) == 'long' else 2

        response = bybit_api.place_market_order(
            symbol=order.symbol, side=order.side.capitalize(),
            quantity=order.quantity_contracts, reduce_only=order.reduce_only,
            position_idx=pos_idx, account_name=account_name
        )

        if response and response.get('retCode') == 0:
            return True, response.get('result', {}).get('orderId', 'N/A')
        else:
            return False, response.get('retMsg', 'Error desconocido') if response else 'Sin respuesta'

    def cancel_order(self, order_id: str, symbol: str, account_purpose: str) -> bool:
        account_name = self._purpose_to_account_name_map.get(account_purpose)
        if not account_name: return False
        response = bybit_api.cancel_order(symbol=symbol, order_id=order_id, account_name=account_name)
        return response and response.get('retCode') == 0

    def set_leverage(self, symbol: str, leverage: float, account_purpose: str) -> bool:
        account_name = self._purpose_to_account_name_map.get(account_purpose)
        if not account_name: return False
        leverage_str = str(leverage)
        return bybit_api.set_leverage(
            symbol=symbol, buy_leverage=leverage_str,
            sell_leverage=leverage_str, account_name=account_name
        )

    def transfer_funds(self, amount: float, from_purpose: str, to_purpose: str, coin: str = "USDT") -> bool:
        from_acc_name = self._purpose_to_account_name_map.get(from_purpose)
        to_acc_name = self._purpose_to_account_name_map.get(to_purpose)
        if not from_acc_name or not to_acc_name: 
            memory_logger.log(f"Error de transferencia: propósito desconocido '{from_purpose}' o '{to_purpose}'", "ERROR")
            return False

        # --- INICIO DE LA MODIFICACIÓN (Adaptación a Nueva Estructura) ---
        # --- (COMENTADO) ---
        # loaded_uids = getattr(config, 'LOADED_UIDS', {})
        # --- (CORREGIDO) ---
        loaded_uids = config.LOADED_UIDS
        # --- FIN DE LA MODIFICACIÓN ---
        from_uid = loaded_uids.get(from_acc_name)
        to_uid = loaded_uids.get(to_acc_name)
        if not from_uid or not to_uid: 
            memory_logger.log(f"Error de transferencia: UID no encontrado para '{from_acc_name}' o '{to_acc_name}'", "ERROR")
            return False

        # --- INICIO DE LA MODIFICACIÓN (Adaptación a Nueva Estructura) ---
        # --- (COMENTADO) ---
        # session, _ = self._connection_manager.get_session_for_operation('general', specific_account=config.ACCOUNT_MAIN)
        # --- (CORREGIDO) ---
        session, _ = self._connection_manager.get_session_for_operation('general', specific_account=config.BOT_CONFIG["ACCOUNTS"]["MAIN"])
        # --- FIN DE LA MODIFICACIÓN ---
        if not session: 
            memory_logger.log("Error de transferencia: No se pudo obtener sesión para la cuenta principal.", "ERROR")
            return False
        
        amount_str = f"{amount:.4f}"
        
        try:
            transfer_id = str(uuid.uuid4())
            # --- INICIO DE LA MODIFICACIÓN (Adaptación a Nueva Estructura) ---
            # --- (COMENTADO) ---
            # response = session.create_universal_transfer(
            #     transferId=transfer_id, coin=coin.upper(), amount=amount_str,
            #     fromMemberId=int(from_uid), toMemberId=int(to_uid),
            #     fromAccountType=getattr(config, 'UNIVERSAL_TRANSFER_FROM_TYPE', 'UNIFIED'),
            #     toAccountType=getattr(config, 'UNIVERSAL_TRANSFER_TO_TYPE', 'UNIFIED')
            # )
            # --- (CORREGIDO) ---
            response = session.create_universal_transfer(
                transferId=transfer_id, coin=coin.upper(), amount=amount_str,
                fromMemberId=int(from_uid), toMemberId=int(to_uid),
                fromAccountType=config.EXCHANGE_CONSTANTS["BYBIT"]["UNIVERSAL_TRANSFER_FROM_TYPE"],
                toAccountType=config.EXCHANGE_CONSTANTS["BYBIT"]["UNIVERSAL_TRANSFER_TO_TYPE"]
            )
            # --- FIN DE LA MODIFICACIÓN ---
            
            if response and response.get('retCode') == 0:
                return True
            else:
                error_msg = response.get('retMsg', 'Error desconocido') if response else "Sin respuesta de la API"
                memory_logger.log(f"[BybitAdapter] Fallo en la transferencia: {error_msg}", "ERROR")
                return False

        except Exception as e:
            memory_logger.log(f"[BybitAdapter] Excepción en la transferencia: {e}", "ERROR")
            return False

    def get_latest_price(self) -> Optional[float]:
        return self._latest_price