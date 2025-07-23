"""
Implementación del Adaptador de Exchange para Bybit.
v2.0: Implementa el manejo de cuentas con propósito y transferencias.
"""
import time
from typing import List, Optional, Tuple
import datetime
from core import api as bybit_api, utils
from core.logging import memory_logger
from connection import manager as connection_manager
import config

from ._interface import AbstractExchange
from ._models import StandardOrder, StandardPosition, StandardBalance, StandardInstrumentInfo, StandardTicker

class BybitAdapter(AbstractExchange):
    """Implementación del protocolo de Exchange para Bybit."""

    def __init__(self):
        self._symbol: Optional[str] = None
        self._latest_price: Optional[float] = None
        # Mapeo de propósito a nombre de cuenta de config.py
        self._purpose_to_account_name_map = {
            'main': config.ACCOUNT_MAIN,
            'longs': config.ACCOUNT_LONGS,
            'shorts': config.ACCOUNT_SHORTS,
            'profit': config.ACCOUNT_PROFIT,
            'ticker': config.TICKER_SOURCE_ACCOUNT
        }

    def initialize(self, symbol: str) -> bool:
        """Verifica que las cuentas necesarias están disponibles."""
        self._symbol = symbol
        initialized_accounts = connection_manager.get_initialized_accounts()
        required_accounts = set(self._purpose_to_account_name_map.values())
        
        if not required_accounts.issubset(set(initialized_accounts)):
            missing = required_accounts - set(initialized_accounts)
            memory_logger.log(f"[BybitAdapter] ERROR: Faltan cuentas requeridas en la conexión: {missing}", "ERROR")
            return False
        
        memory_logger.log(f"[BybitAdapter] Inicializado con éxito para el símbolo '{symbol}'.", "INFO")
        return True

    def get_instrument_info(self, symbol: str) -> Optional[StandardInstrumentInfo]:
        # Esta llamada no depende de la cuenta, así que es simple
        bybit_info = bybit_api.get_instrument_info(symbol)
        if not bybit_info: return None
        # (El resto de la lógica de traducción permanece igual)
        try:
            qty_step = utils.safe_float_convert(bybit_info.get('qtyStep'), 0.001)
            qty_precision = 0
            if '.' in str(qty_step):
                qty_precision = len(str(qty_step).split('.')[1])

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
        session, _ = connection_manager.get_session_for_operation('general', specific_account=account_name)
        if not session: return None
        
        category = getattr(config, 'CATEGORY_LINEAR', 'linear')
        response = session.get_tickers(category=category, symbol=symbol)
        
        if not response or response.get('retCode') != 0: return None
            
        try:
            ticker_data = response.get('result', {}).get('list', [])[0]
            price = utils.safe_float_convert(ticker_data.get('lastPrice'))
            if price and price > 0:
                self._latest_price = price
                return StandardTicker(timestamp=datetime.datetime.now(datetime.timezone.utc), symbol=symbol, price=price)
            return None
        except (IndexError, TypeError, KeyError): return None

    def place_order(self, order: StandardOrder, account_purpose: str) -> Tuple[bool, str]:
        account_name = self._purpose_to_account_name_map.get(account_purpose)
        if not account_name: return False, f"Propósito de cuenta desconocido: '{account_purpose}'"

        is_hedge_mode = getattr(config, 'BYBIT_HEDGE_MODE_ENABLED', True)
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
        if not from_acc_name or not to_acc_name: return False

        loaded_uids = getattr(config, 'LOADED_UIDS', {})
        from_uid = loaded_uids.get(from_acc_name)
        to_uid = loaded_uids.get(to_acc_name)
        if not from_uid or not to_uid: return False

        session, _ = connection_manager.get_session_for_operation('general', specific_account=config.ACCOUNT_MAIN)
        if not session: return False
        
        amount_str = f"{amount:.{4}f}" # Precisión de transferencia
        try:
            response = session.create_universal_transfer(
                transferId=f"bot_{int(time.time()*1000)}", coin=coin.upper(), amount=amount_str,
                fromMemberId=int(from_uid), toMemberId=int(to_uid),
                fromAccountType=getattr(config, 'UNIVERSAL_TRANSFER_FROM_TYPE', 'UNIFIED'),
                toAccountType=getattr(config, 'UNIVERSAL_TRANSFER_TO_TYPE', 'UNIFIED')
            )
            return response and response.get('retCode') == 0
        except Exception as e:
            memory_logger.log(f"[BybitAdapter] Fallo en la transferencia: {e}", "ERROR")
            return False
        
    def get_latest_price(self) -> Optional[float]:
        return self._latest_price