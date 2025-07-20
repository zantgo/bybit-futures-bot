
# =============== INICIO ARCHIVO: core/strategy/position_executor.py (CORREGIDO Y COMPLETO) ===============
"""
Clase PositionExecutor: Encapsula y centraliza la lógica de ejecución.

v18.1 (HFT Ready):
- Eliminados todos los delays (time.sleep) de los ciclos de apertura y cierre.
- Eliminada la lógica de sincronización post-apertura y post-cierre para minimizar la latencia.
- Reducidos los delays y reintentos en la transferencia de fondos (operación no crítica).
- Integrado control de nivel de log para mensajes de depuración.
"""
import datetime
import uuid
import time
import traceback
import json
from typing import Optional, Dict, Any, Tuple

try:
    from core.logging import memory_logger
except ImportError:
    class MemoryLoggerFallback:
        def log(self, msg, level="INFO"): print(f"[{level}] {msg}")
    memory_logger = MemoryLoggerFallback()


MAX_TRANSFER_RETRIES = 1
TRANSFER_RETRY_DELAY = 0.2

class PositionExecutor:
    """
    Clase responsable de la ejecución mecánica de apertura y cierre de posiciones.
    """
    def __init__(self,
                 is_live_mode: bool,
                 config: Optional[Any] = None,
                 utils: Optional[Any] = None,
                 balance_manager: Optional[Any] = None,
                 position_state: Optional[Any] = None,
                 position_calculations: Optional[Any] = None,
                 live_operations: Optional[Any] = None,
                 closed_position_logger: Optional[Any] = None,
                 position_helpers: Optional[Any] = None,
                 live_manager: Optional[Any] = None
                 ):
        self._is_live_mode = is_live_mode
        self._config = config
        self._utils = utils
        self._balance_manager = balance_manager
        self._position_state = position_state
        self._position_calculations = position_calculations
        self._live_operations = live_operations
        self._closed_position_logger = closed_position_logger
        self._position_helpers = position_helpers
        self._live_manager = live_manager

        essential_deps = [self._config, self._utils, self._balance_manager, self._position_state, self._position_calculations, self._position_helpers]
        dep_names = ['Config', 'Utils', 'BalanceMgr', 'PositionState', 'Calculations', 'Helpers']
        if not all(essential_deps):
            missing = [name for name, mod in zip(dep_names, essential_deps) if not mod]
            raise ValueError(f"PositionExecutor: Faltan dependencias esenciales: {missing}")

        try:
            from . import pm_state
            self._pm_state = pm_state
        except ImportError:
            self._pm_state = None
            # --- INICIO MODIFICACIÓN: Usar memory_logger en lugar de print ---
            memory_logger.log("ERROR CRITICO [PositionExecutor]: No se pudo importar pm_state.", level="ERROR")
            # --- CÓDIGO ANTERIOR (COMENTADO) ---
            # print("ERROR CRITICO [PositionExecutor]: No se pudo importar pm_state.")
            # --- FIN MODIFICACIÓN ---
            raise

        if self._is_live_mode and not self._live_operations: raise ValueError("PositionExecutor: Modo Live requiere 'live_operations'.")
        # --- INICIO MODIFICACIÓN: Usar memory_logger en lugar de print ---
        if self._is_live_mode and not self._live_manager: 
            memory_logger.log("WARN [PositionExecutor Init]: Modo Live pero 'live_manager' no proporcionado. Transferencias API fallarán.", level="WARN")
        # --- CÓDIGO ANTERIOR (COMENTADO) ---
        # if self._is_live_mode and not self._live_manager: print("WARN [PositionExecutor Init]: Modo Live pero 'live_manager' no proporcionado. Transferencias API fallarán.")
        # --- FIN MODIFICACIÓN ---

        self._leverage = 1.0; self._symbol = "N/A"; self._print_updates = False; self._price_prec = 4; self._qty_prec = 3; self._pnl_prec = 2
        try:
            self._leverage = float(getattr(self._config, 'POSITION_LEVERAGE', 1.0)); self._symbol = getattr(self._config, 'TICKER_SYMBOL', 'N/A')
            self._print_updates = getattr(self._config, 'POSITION_PRINT_POSITION_UPDATES', False); self._price_prec = int(getattr(self._config, 'PRICE_PRECISION', 4)); self._qty_prec = int(getattr(self._config, 'DEFAULT_QTY_PRECISION', 3)); self._pnl_prec = int(getattr(self._config, 'PNL_PRECISION', 2))
        except Exception as e: 
            # --- INICIO MODIFICACIÓN: Usar memory_logger en lugar de print ---
            memory_logger.log(f"WARN [PositionExecutor Init]: Error cacheando config: {e}. Usando defaults.", level="WARN")
            # --- CÓDIGO ANTERIOR (COMENTADO) ---
            # print(f"WARN [PositionExecutor Init]: Error cacheando config: {e}. Usando defaults.")
            # --- FIN MODIFICACIÓN ---
        memory_logger.log(f"[PositionExecutor] Inicializado. Modo Live: {self._is_live_mode}", level="INFO")

    def execute_open(self, side: str, entry_price: float, timestamp: datetime.datetime, margin_to_use: Optional[float] = None, size_contracts_str_api: Optional[str] = None ) -> Dict[str, Any]:
        """Orquesta la apertura de una posición (Live o Backtest) sin delays."""
        result = {'success': False, 'api_order_id': None, 'logical_position_id': None, 'message': 'Error no especificado'}
        
        # --- INICIO MODIFICACIÓN: Log de apertura con formato ---
        memory_logger.log(f"OPEN [{side.upper()}] -> Solicitud para abrir @ {entry_price:.{self._price_prec}f}", level="INFO")
        # --- CÓDIGO ANTERIOR (COMENTADO) ---
        # memory_logger.log(f"--- INICIO APERTURA [{side.upper()}] Px: {entry_price:.{self._price_prec}f} ---")
        # --- FIN MODIFICACIÓN ---
        
        if side not in ['long', 'short']: result['message'] = f"Lado inválido '{side}'."; memory_logger.log(f"ERROR [Exec Open]: {result['message']}", level="ERROR"); return result
        if not isinstance(entry_price, (int, float)) or entry_price <= 0: result['message'] = f"Precio entrada inválido {entry_price}."; memory_logger.log(f"ERROR [Exec Open]: {result['message']}", level="ERROR"); return result
        if margin_to_use is None and size_contracts_str_api is None: result['message'] = "Debe proveer 'margin_to_use' o 'size_contracts_str_api'."; memory_logger.log(f"ERROR [Exec Open]: {result['message']}", level="ERROR"); return result
        if not all([self._position_state, self._balance_manager, self._position_calculations, self._position_helpers, self._utils, self._pm_state]): result['message'] = "Faltan dependencias internas."; memory_logger.log(f"ERROR [Exec Open]: {result['message']}", level="ERROR"); return result

        size_contracts_final_float = 0.0; margin_used_final = 0.0; qty_precision_used = self._qty_prec
        try:
            if size_contracts_str_api is None:
                if not isinstance(margin_to_use, (int, float)) or margin_to_use <= 1e-6: result['message'] = f"Margen a usar inválido ({margin_to_use})."; memory_logger.log(f"ERROR [Exec Open]: {result['message']}", level="ERROR"); return result
                margin_used_final = margin_to_use
                memory_logger.log(f"  Calculando tamaño desde Margen: {margin_used_final:.4f} USDT", level="DEBUG")
                calc_qty_result = self._position_helpers.calculate_and_round_quantity(margin_usdt=margin_used_final, entry_price=entry_price, leverage=self._leverage, symbol=self._symbol, is_live=self._is_live_mode)
                if not calc_qty_result['success']: result['message'] = calc_qty_result['error']; memory_logger.log(f"ERROR [Exec Open]: {result['message']}", level="ERROR"); return result
                size_contracts_final_float = calc_qty_result['qty_float']; size_contracts_str_api = calc_qty_result['qty_str']; qty_precision_used = calc_qty_result['precision']
            else:
                memory_logger.log(f"  Usando tamaño pre-calculado: {size_contracts_str_api}", level="DEBUG")
                size_contracts_final_float = self._utils.safe_float_convert(size_contracts_str_api, 0.0)
                if size_contracts_final_float <= 1e-12: result['message'] = f"Tamaño provisto inválido ({size_contracts_str_api})."; memory_logger.log(f"ERROR [Exec Open]: {result['message']}", level="ERROR"); return result
                margin_used_final = self._utils.safe_division(size_contracts_final_float * entry_price, self._leverage, default=0.0)
                if margin_used_final <= 0: memory_logger.log(f"WARN [Exec Open]: Margen recalculado para tamaño provisto es {margin_used_final}.", level="WARN")
            memory_logger.log(f"  Tamaño Final: {size_contracts_final_float:.{qty_precision_used}f} ({size_contracts_str_api} API), Margen: {margin_used_final:.4f} USDT", level="DEBUG")
        except Exception as e: result['message'] = f"Excepción calculando tamaño/margen: {e}"; memory_logger.log(f"ERROR [Exec Open]: {result['message']}", level="ERROR"); traceback.print_exc(); return result

        logical_position_id = str(uuid.uuid4())
        
        individual_sl_pct = self._pm_state.get_individual_stop_loss_pct()
        stop_loss_price = self._position_calculations.calculate_stop_loss(side, entry_price, individual_sl_pct)
        
        est_liq_price_individual = self._position_calculations.calculate_liquidation_price(
            side=side, avg_entry_price=entry_price, leverage=self._leverage
        )
        new_position_data = {
            'id': logical_position_id, 'entry_timestamp': timestamp, 'entry_price': entry_price,
            'margin_usdt': margin_used_final, 'size_contracts': size_contracts_final_float,
            'leverage': self._leverage, 'stop_loss_price': stop_loss_price,
            'est_liq_price': est_liq_price_individual, 'ts_is_active': False,
            'ts_peak_price': None, 'ts_stop_price': None, 'api_order_id': None,
            'api_avg_fill_price': None, 'api_filled_qty': None
        }
        result['logical_position_id'] = logical_position_id

        execution_success = False; api_order_id = None
        try:
            if self._is_live_mode:
                memory_logger.log(f"  Ejecutando Apertura LIVE API...", level="DEBUG")
                if not self._live_operations: raise RuntimeError("Live Operations no disponible")
                target_account = getattr(self._config, 'ACCOUNT_LONGS' if side == 'long' else 'ACCOUNT_SHORTS', None); main_account = getattr(self._config, 'ACCOUNT_MAIN', 'main'); account_to_use = target_account if target_account and target_account in self._live_manager.get_initialized_accounts() else main_account
                if account_to_use not in self._live_manager.get_initialized_accounts(): raise RuntimeError(f"Cuenta operativa '{account_to_use}' no inicializada.")
                order_side_api = "Buy" if side == 'long' else "Sell"; pos_idx = 1 if side == 'long' else 2
                api_response = self._live_operations.place_market_order(symbol=self._symbol, side=order_side_api, quantity=size_contracts_str_api, reduce_only=False, position_idx=pos_idx, account_name=account_to_use)
                if api_response and api_response.get('retCode') == 0:
                    execution_success = True; api_order_id = api_response.get('result', {}).get('orderId', 'N/A'); memory_logger.log(f"  -> ÉXITO API: Orden Market {order_side_api} aceptada. OrderID: {api_order_id}")
                else:
                    ret_code = api_response.get('retCode', -1) if api_response else -1; ret_msg = api_response.get('retMsg', 'N/A') if api_response else 'N/A'; result['message'] = f"Fallo API orden Market {order_side_api}. Code={ret_code}, Msg='{ret_msg}'"; memory_logger.log(f"  -> ERROR API: {result['message']}", level="ERROR")
            else:
                memory_logger.log(f"  Ejecutando Apertura BACKTEST (Simulada)...", level="DEBUG")
                execution_success = True; api_order_id = None
                memory_logger.log(f"  -> ÉXITO Simulado.", level="DEBUG")
            if execution_success:
                self._balance_manager.decrease_operational_margin(side, margin_used_final)
        except Exception as exec_err: result['message'] = f"Excepción durante ejecución: {exec_err}"; memory_logger.log(f"ERROR [Exec Open]: {result['message']}", level="ERROR"); traceback.print_exc(); execution_success = False

        add_ok = False
        if execution_success:
            try:
                new_position_data['api_order_id'] = api_order_id
                add_ok = self._position_state.add_logical_position(side, new_position_data)
                if not add_ok:
                    result['message'] = f"Ejecución OK pero falló añadir a PS pos ID {logical_position_id}."
                    memory_logger.log(f"ERROR SEVERE [Exec Open]: {result['message']}", level="ERROR")
                    result['success'] = False
                    return result

                memory_logger.log(f"  Position State: Posición lógica ...{logical_position_id[-6:]} añadida (datos estimados).", level="DEBUG")
                
                memory_logger.log(f"  Actualizando estado físico agregado...", level="DEBUG")
                open_positions_now = self._position_state.get_open_logical_positions(side)
                aggregates = self._position_calculations.calculate_physical_aggregates(open_positions_now)
                liq_price_aggregate = self._position_calculations.calculate_liquidation_price(side, aggregates['avg_entry_price'], self._leverage)
                self._position_state.update_physical_position_state(side, aggregates.get('avg_entry_price', 0.0), aggregates.get('total_size_contracts', 0.0), aggregates.get('total_margin_usdt', 0.0), liq_price_aggregate, timestamp)
                memory_logger.log(f"  -> Estado físico agregado {side.upper()} recalculado.", level="DEBUG")

            except Exception as state_err: result['message'] = f"Ejecución OK pero falló post-proceso: {state_err}"; memory_logger.log(f"ERROR SEVERE [Exec Open]: {result['message']}", level="ERROR"); traceback.print_exc(); result['success'] = False; return result

        result['success'] = execution_success and add_ok
        result['api_order_id'] = api_order_id
        if result['success']:
            result['message'] = f"Apertura {side.upper()} exitosa."

        # --- INICIO MODIFICACIÓN: Log final de apertura ---
        if result['success']:
            memory_logger.log(f"OPEN [{side.upper()}] -> ÉXITO. Tamaño: {size_contracts_final_float:.{qty_precision_used}f}, Margen: {margin_used_final:.2f} USDT", level="INFO")
        else:
            memory_logger.log(f"OPEN [{side.upper()}] -> FALLO. Razón: {result['message']}", level="ERROR")
        # --- CÓDIGO ANTERIOR (COMENTADO) ---
        # memory_logger.log(f"--- FIN APERTURA [{side.upper()}] -> Success: {result['success']} ---")
        # --- FIN MODIFICACIÓN ---
        return result

    def execute_close(self, side: str, position_index: int, exit_price: float,
                      timestamp: datetime.datetime, exit_reason: str = "UNKNOWN") -> Dict[str, Any]:
        result = {
            'success': False, 'pnl_net_usdt': 0.0, 'amount_reinvested_in_operational_margin': 0.0,
            'amount_transferable_to_profit': 0.0, 'log_data': {}, 'message': 'Error no especificado',
            'closed_position_id': None
        }
        
        # --- INICIO MODIFICACIÓN: Log de cierre con formato ---
        memory_logger.log(f"CLOSE [{side.upper()} Idx:{position_index}] -> Solicitud para cerrar @ {exit_price:.{self._price_prec}f} (Razón: {exit_reason})", level="INFO")
        # --- CÓDIGO ANTERIOR (COMENTADO) ---
        # memory_logger.log(f"--- INICIO CIERRE [{side.upper()} Idx: {position_index}, Razón: {exit_reason}] ---")
        # --- FIN MODIFICACIÓN ---

        if side not in ['long', 'short']: result['message'] = "Lado inválido."; memory_logger.log(f"ERROR [Exec Close]: {result['message']}", level="ERROR"); return result
        if not isinstance(exit_price, (int, float)) or exit_price <= 0: result['message'] = "Precio salida inválido."; memory_logger.log(f"ERROR [Exec Close]: {result['message']}", level="ERROR"); return result
        if not all([self._position_state, self._balance_manager, self._position_calculations, self._position_helpers, self._utils]): result['message'] = "Faltan dependencias internas."; memory_logger.log(f"ERROR [Exec Close]: {result['message']}", level="ERROR"); return result

        pos_to_close_data = None; log_data_partial = {}; size_contracts_str_api = "0.0";
        pos_id_for_log = 'N/A_PreValid'; entry_price_for_calc = 0.0; initial_margin_for_calc = 0.0; size_contracts_for_calc = 0.0; entry_ts_for_calc = None; leverage_for_calc = self._leverage
        try:
            open_positions = self._position_state.get_open_logical_positions(side)
            if not (0 <= position_index < len(open_positions)): result['message'] = f"Índice {position_index} fuera de rango."; memory_logger.log(f"ERROR [Exec Close]: {result['message']}", level="ERROR"); return result
            pos_to_close_data = open_positions[position_index]
            pos_id_for_log = pos_to_close_data.get('id', 'N/A_DataErr'); log_data_partial = {'id': pos_id_for_log, 'side': side, 'index_closed': position_index}
            result['log_data'] = log_data_partial; result['closed_position_id'] = pos_id_for_log

            size_contracts_for_calc = self._utils.safe_float_convert(pos_to_close_data.get('size_contracts'), 0.0)
            entry_price_for_calc = self._utils.safe_float_convert(pos_to_close_data.get('entry_price'), 0.0)
            initial_margin_for_calc = self._utils.safe_float_convert(pos_to_close_data.get('margin_usdt'), 0.0)
            entry_ts_for_calc = pos_to_close_data.get('entry_timestamp')
            leverage_for_calc = self._utils.safe_float_convert(pos_to_close_data.get('leverage'), self._leverage)

            if size_contracts_for_calc <= 1e-12: result['message'] = f"Tamaño lógico <= 0 para pos ID ...{pos_id_for_log[-6:]}. Considerado ya cerrado."; memory_logger.log(f"WARN [Exec Close]: {result['message']}", level="WARN"); result['success'] = True; return result

            format_qty_result = self._position_helpers.format_quantity_for_api(quantity_float=size_contracts_for_calc, symbol=self._symbol, is_live=self._is_live_mode)
            if not format_qty_result['success']: result['message'] = f"Error formateando Qty para API ({format_qty_result['error']}) Pos ID ...{pos_id_for_log[-6:]}."; memory_logger.log(f"ERROR [Exec Close]: {result['message']}", level="ERROR"); return result
            size_contracts_str_api = format_qty_result['qty_str']
        except Exception as data_err: result['message'] = f"Excepción obteniendo datos/formateando: {data_err}"; memory_logger.log(f"ERROR [Exec Close]: {result['message']}", level="ERROR"); traceback.print_exc(); return result

        execution_success = False; api_order_id_close = None; ret_code: Optional[int] = None; ret_msg: Optional[str] = None
        try:
            if self._is_live_mode:
                memory_logger.log(f"  Ejecutando Cierre LIVE API (ReduceOnly)...", level="DEBUG")
                if not self._live_operations: raise RuntimeError("Live Operations no disponible")
                target_account = getattr(self._config, 'ACCOUNT_LONGS' if side == 'long' else 'ACCOUNT_SHORTS', None); main_account = getattr(self._config, 'ACCOUNT_MAIN', 'main'); account_to_use = target_account if target_account and target_account in self._live_manager.get_initialized_accounts() else main_account
                if account_to_use not in self._live_manager.get_initialized_accounts(): raise RuntimeError(f"Cuenta operativa '{account_to_use}' no inicializada.")
                close_order_side_api = "Sell" if side == 'long' else "Buy"; pos_idx = 1 if side == 'long' else 2
                api_response = self._live_operations.place_market_order(symbol=self._symbol, side=close_order_side_api, quantity=size_contracts_str_api, reduce_only=True, position_idx=pos_idx, account_name=account_to_use)
                if api_response and api_response.get('retCode') == 0:
                    execution_success = True; api_order_id_close = api_response.get('result', {}).get('orderId', 'N/A'); memory_logger.log(f"  -> ÉXITO API: Orden Cierre Market {close_order_side_api} aceptada. OrderID: {api_order_id_close}")
                else:
                    if api_response: ret_code = api_response.get('retCode', -1); ret_msg = api_response.get('retMsg', 'N/A')
                    else: ret_code = -1; ret_msg = 'No API Response'
                    result['message'] = f"Fallo API orden Cierre Market {close_order_side_api}. Code={ret_code}, Msg='{ret_msg}'"; memory_logger.log(f"  -> ERROR API: {result['message']}", level="ERROR")
                    if ret_code == 110001: execution_success = True; memory_logger.log("  WARN [Exec Close]: Orden/Posición no encontrada (110001). Permitiendo limpieza lógica.", level="WARN")
            else:
                memory_logger.log(f"  Ejecutando Cierre BACKTEST (Simulado)...", level="DEBUG")
                execution_success = True; api_order_id_close = None
                memory_logger.log(f"  -> ÉXITO Simulado.", level="DEBUG")
        except Exception as exec_err: result['message'] = f"Excepción durante ejecución: {exec_err}"; memory_logger.log(f"ERROR [Exec Close]: {result['message']}", level="ERROR"); traceback.print_exc(); execution_success = False

        remove_ok = False; log_data_final = {}
        if execution_success:
            try:
                removed_pos_data = self._position_state.remove_logical_position(side, position_index)
                if removed_pos_data:
                    remove_ok = True
                    pos_id_for_log = removed_pos_data.get('id', pos_id_for_log)
                    entry_price_for_calc = self._utils.safe_float_convert(removed_pos_data.get('entry_price'), 0.0)
                    initial_margin_for_calc = self._utils.safe_float_convert(removed_pos_data.get('margin_usdt'), 0.0)
                    size_contracts_for_calc = self._utils.safe_float_convert(removed_pos_data.get('size_contracts'), 0.0)
                    entry_ts_for_calc = removed_pos_data.get('entry_timestamp')
                    leverage_for_calc = self._utils.safe_float_convert(removed_pos_data.get('leverage'), self._leverage)
                    memory_logger.log(f"  Position State: Posición lógica ...{pos_id_for_log[-6:]} removida.", level="DEBUG")
                elif ret_code == 110001:
                    remove_ok = True; memory_logger.log(f"  INFO [Exec Close]: Pos lógica idx {position_index} (ID: ...{pos_id_for_log[-6:]}) no encontrada, consistente con API 110001.")
                else:
                    result['message'] = f"Ejecución OK pero falló remover pos lógica idx {position_index} (ID: ...{pos_id_for_log[-6:]})."; memory_logger.log(f"ERROR SEVERE [Exec Close]: {result['message']}", level="ERROR"); result['success'] = False; return result

                calc_results = self._position_calculations.calculate_pnl_commission_reinvestment(side, entry_price_for_calc, exit_price, size_contracts_for_calc)
                pnl_gross_usdt, commission_usdt, pnl_net_usdt = calc_results['pnl_gross_usdt'], calc_results['commission_usdt'], calc_results['pnl_net_usdt']
                amount_reinvested_op_margin, amount_transferable_profit = calc_results['amount_reinvested_in_operational_margin'], calc_results['amount_transferable_to_profit']

                result.update({
                    'pnl_net_usdt': pnl_net_usdt, 'amount_reinvested_in_operational_margin': amount_reinvested_op_margin,
                    'amount_transferable_to_profit': amount_transferable_profit
                })
                memory_logger.log(f"  Cálculos PNL: Neto={pnl_net_usdt:+.{self._pnl_prec}f}, Reinv={amount_reinvested_op_margin:.{self._pnl_prec}f}, Transf={amount_transferable_profit:.{self._pnl_prec}f}", level="DEBUG")

                if remove_ok and removed_pos_data:
                    margin_to_return_to_op = initial_margin_for_calc + amount_reinvested_op_margin
                    self._balance_manager.increase_operational_margin(side, margin_to_return_to_op)
                elif remove_ok and ret_code == 110001:
                    memory_logger.log("  Balance Manager: No se modifica margen operativo (posición no encontrada).", level="DEBUG")

                memory_logger.log(f"  Actualizando estado físico agregado post-remoción...", level="DEBUG")
                open_positions_now = self._position_state.get_open_logical_positions(side);
                if open_positions_now:
                    aggregates = self._position_calculations.calculate_physical_aggregates(open_positions_now)
                    liq_price = self._position_calculations.calculate_liquidation_price(side, aggregates['avg_entry_price'], self._leverage)
                    self._position_state.update_physical_position_state(side, aggregates.get('avg_entry_price', 0.0), aggregates.get('total_size_contracts', 0.0), aggregates.get('total_margin_usdt', 0.0), liq_price, timestamp)
                    memory_logger.log(f"  -> Estado físico {side.upper()} recalculado (pos restantes: {len(open_positions_now)}).", level="DEBUG")
                else:
                    self._position_state.reset_physical_position_state(side)
                    memory_logger.log(f"  -> Estado físico {side.upper()} reseteado (no quedan pos lógicas).", level="DEBUG")

                log_entry_ts_str = self._utils.format_datetime(entry_ts_for_calc) if entry_ts_for_calc else "N/A"; log_exit_ts_str = self._utils.format_datetime(timestamp); duration = (timestamp - entry_ts_for_calc).total_seconds() if isinstance(entry_ts_for_calc, datetime.datetime) else None
                
                log_data_final = {
                    "id": pos_id_for_log, "side": side, "entry_timestamp": log_entry_ts_str,
                    "exit_timestamp": log_exit_ts_str, "duration_seconds": duration, "entry_price": entry_price_for_calc,
                    "exit_price": exit_price, "size_contracts": size_contracts_for_calc, "margin_usdt": initial_margin_for_calc,
                    "leverage": leverage_for_calc, "pnl_gross_usdt": pnl_gross_usdt, "commission_usdt": commission_usdt,
                    "pnl_net_usdt": pnl_net_usdt, "reinvest_usdt": amount_reinvested_op_margin, "transfer_usdt": amount_transferable_profit,
                    "api_close_order_id": api_order_id_close, "api_ret_code_close": ret_code, "api_ret_msg_close": ret_msg,
                    "exit_reason": exit_reason
                }
                
                result['log_data'] = log_data_final

                if self._closed_position_logger and hasattr(self._closed_position_logger, 'log_closed_position'):
                    try: self._closed_position_logger.log_closed_position(log_data_final)
                    except Exception as log_e: 
                        # --- INICIO MODIFICACIÓN: Usar memory_logger en lugar de print ---
                        memory_logger.log(f"ERROR [Exec Close]: Fallo log pos cerrada ID {pos_id_for_log}: {log_e}", level="ERROR")
                        # --- CÓDIGO ANTERIOR (COMENTADO) ---
                        # print(f"ERROR [Exec Close]: Fallo log pos cerrada ID {pos_id_for_log}: {log_e}")
                        # --- FIN MODIFICACIÓN ---

            except Exception as state_err: result['message'] = f"Ejecución OK pero falló post-proceso: {state_err}"; memory_logger.log(f"ERROR SEVERE [Exec Close]: {result['message']}", level="ERROR"); traceback.print_exc(); result['success'] = False; return result

        result['success'] = execution_success and remove_ok
        if not result['success'] and not result['message']: result['message'] = "Fallo en cierre por razón desconocida."
        elif result['success']: result['message'] = f"Cierre {side.upper()} idx {position_index} exitoso."
        
        # --- INICIO MODIFICACIÓN: Log final de cierre ---
        if result['success']:
            pnl_net = result.get('pnl_net_usdt', 0.0)
            log_level = "INFO" if pnl_net >= 0 else "WARN"
            memory_logger.log(f"CLOSE [{side.upper()} Idx:{position_index}] -> ÉXITO. PNL Neto: {pnl_net:+.{self._pnl_prec}f} USDT", level=log_level)
        else:
            memory_logger.log(f"CLOSE [{side.upper()} Idx:{position_index}] -> FALLO. Razón: {result['message']}", level="ERROR")
        # --- CÓDIGO ANTERIOR (COMENTADO) ---
        # memory_logger.log(f"--- FIN CIERRE [{side.upper()} Idx: {position_index}] -> Success: {result['success']} ---")
        # --- FIN MODIFICACIÓN ---
        return result

    def execute_transfer(self, amount: float, from_account_side: str) -> float:
        memory_logger.log(f"Solicitando transferencia de {amount:.4f} desde {from_account_side.upper()}", level="DEBUG")
        transferred_amount_api_or_sim = 0.0
        if amount <= 1e-9:
            memory_logger.log("  Monto <= 0, omitida.", level="DEBUG")
            return 0.0

        try:
            if self._is_live_mode:
                if not self._live_manager or not self._live_operations or not self._config:
                    memory_logger.log("ERROR [Exec Transfer Live]: live_manager/live_ops/config no disponibles.", level="ERROR"); return 0.0
                from_acc_name = getattr(self._config, 'ACCOUNT_LONGS' if from_account_side == 'long' else 'ACCOUNT_SHORTS', None)
                to_acc_name = getattr(self._config, 'ACCOUNT_PROFIT', None)
                if not from_acc_name or not to_acc_name: memory_logger.log(f"ERROR [Exec Transfer Live]: Cuenta origen/destino no definida.", level="ERROR"); return 0.0
                loaded_uids = getattr(self._config, 'LOADED_UIDS', {}); from_uid = loaded_uids.get(from_acc_name); to_uid = loaded_uids.get(to_acc_name)
                if not from_uid or not to_uid: memory_logger.log(f"ERROR [Exec Transfer Live]: UIDs no encontrados.", level="ERROR"); return 0.0
                try: from_uid_int = int(from_uid); to_uid_int = int(to_uid)
                except ValueError: memory_logger.log(f"ERROR [Exec Transfer Live]: UIDs inválidos (no int).", level="ERROR"); return 0.0

                TRANSFER_API_PRECISION = 4; amount_str = f"{amount:.{TRANSFER_API_PRECISION}f}"
                main_acc_for_call = getattr(self._config, 'ACCOUNT_MAIN', 'main');
                session_for_call = self._live_manager.get_client(main_acc_for_call)
                if not session_for_call: session_for_call = self._live_manager.get_client(from_acc_name)
                if not session_for_call: memory_logger.log(f"ERROR [Exec Transfer Live]: Sesión API no disponible.", level="ERROR"); return 0.0

                for attempt in range(MAX_TRANSFER_RETRIES + 1):
                    memory_logger.log(f"  API Call Attempt #{attempt + 1}/{MAX_TRANSFER_RETRIES + 1}: create_universal_transfer(...)", level="DEBUG")
                    resp = None
                    try:
                        resp = self._live_manager.create_universal_transfer(
                            session=session_for_call, coin="USDT", amount=amount_str, from_member_id=from_uid_int,
                            to_member_id=to_uid_int, from_account_type=getattr(self._config, 'UNIVERSAL_TRANSFER_FROM_TYPE', 'UNIFIED'),
                            to_account_type=getattr(self._config, 'UNIVERSAL_TRANSFER_TO_TYPE', 'UNIFIED')
                        )
                    except Exception as api_call_err:
                         memory_logger.log(f"    ERROR [Exec Transfer]: Excepción en llamada API (Intento {attempt + 1}): {api_call_err}", level="ERROR")
                         if attempt < MAX_TRANSFER_RETRIES: time.sleep(TRANSFER_RETRY_DELAY); continue
                         else: memory_logger.log("    Fallo API después de máximos reintentos por excepción.", level="ERROR"); break
                    if resp and resp.get('retCode') == 0:
                        transfer_id = resp.get('result', {}).get('transferId', 'N/A')
                        memory_logger.log(f"    -> ÉXITO API Transfer: ID={transfer_id}, Status={resp.get('result',{}).get('status','?')}")
                        transferred_amount_api_or_sim = amount
                        break
                    elif resp:
                        ret_code_t = resp.get('retCode', -1); ret_msg_t = resp.get('retMsg', 'N/A')
                        memory_logger.log(f"    -> FALLO API Transfer (Intento {attempt + 1}): Code={ret_code_t}, Msg='{ret_msg_t}'", level="WARN")
                        non_retryable_codes = [131200, 131001, 131228, 10003, 10005, 10019, 131214, 131204, 131206, 131210]
                        if ret_code_t in non_retryable_codes: memory_logger.log("      Error no recuperable.", level="WARN"); transferred_amount_api_or_sim = 0.0; break
                        if attempt < MAX_TRANSFER_RETRIES: time.sleep(TRANSFER_RETRY_DELAY)
                        else: memory_logger.log("    Fallo API después de máximos reintentos.", level="ERROR"); transferred_amount_api_or_sim = 0.0
                    else:
                        memory_logger.log(f"    -> FALLO API Transfer (Intento {attempt + 1}): No se recibió respuesta.", level="WARN")
                        if attempt < MAX_TRANSFER_RETRIES: time.sleep(TRANSFER_RETRY_DELAY)
                        else: memory_logger.log("    Fallo API sin respuesta después de máximos reintentos.", level="ERROR"); transferred_amount_api_or_sim = 0.0
            else:
                memory_logger.log("  Ejecutando Transferencia BACKTEST (Simulada)...", level="DEBUG")
                if not self._balance_manager: memory_logger.log("ERROR [Exec Transfer BT]: balance_manager no disponible.", level="ERROR"); return 0.0
                sim_success = self._balance_manager.simulate_profit_transfer(from_account_side, amount)
                if sim_success:
                    memory_logger.log(f"  -> ÉXITO Simulación Transfer: {amount:.4f} USDT reflejado en BalanceManager.", level="DEBUG")
                    transferred_amount_api_or_sim = amount
                else: memory_logger.log(f"  -> FALLO Simulación Transfer.", level="ERROR"); transferred_amount_api_or_sim = 0.0
        except Exception as e:
            memory_logger.log(f"ERROR [Exec Transfer]: Excepción general: {e}", level="ERROR"); traceback.print_exc(); transferred_amount_api_or_sim = 0.0

        memory_logger.log(f"  Monto Efectivamente Transferido (API o Sim): {transferred_amount_api_or_sim:.4f} USDT", level="DEBUG")
        return transferred_amount_api_or_sim


    def sync_physical_state(self, side: str):
        # --- INICIO MODIFICACIÓN: Usar memory_logger en lugar de print ---
        if not self._is_live_mode: 
            memory_logger.log("WARN [Sync State]: Solo aplicable en modo Live.", level="WARN")
            return
        if not all([self._position_state, self._live_operations, self._config, self._utils, self._position_helpers, self._live_manager]):
            memory_logger.log("WARN [Sync State]: Faltan dependencias.", level="WARN")
            return
        if getattr(self._config, 'LOG_LEVEL', 'INFO') == "DEBUG": 
            memory_logger.log(f"  ... Sincronizando estado físico {side.upper()} con API ...", level="DEBUG")
        # --- CÓDIGO ANTERIOR (COMENTADO) ---
        # if not self._is_live_mode: print("WARN [Sync State]: Solo aplicable en modo Live."); return
        # if not all([self._position_state, self._live_operations, self._config, self._utils, self._position_helpers, self._live_manager]): print("WARN [Sync State]: Faltan dependencias."); return
        # if getattr(self._config, 'LOG_LEVEL', 'INFO') == "DEBUG": print(f"  ... Sincronizando estado físico {side.upper()} con API ...")
        # --- FIN MODIFICACIÓN ---
        
        physical_state_data = None
        try:
            target_account = getattr(self._config, 'ACCOUNT_LONGS' if side == 'long' else 'ACCOUNT_SHORTS', None); main_acc = getattr(self._config, 'ACCOUNT_MAIN', 'main'); account_to_use = target_account if target_account and target_account in self._live_manager.get_initialized_accounts() else main_acc
            
            # --- INICIO MODIFICACIÓN: Usar memory_logger en lugar de print ---
            if account_to_use not in self._live_manager.get_initialized_accounts(): 
                memory_logger.log(f"    ERROR SYNC: Cuenta '{account_to_use}' no inicializada.", level="ERROR")
                return
            physical_pos_raw = self._live_operations.get_active_position_details_api(self._symbol, account_to_use)
            if physical_pos_raw is None:
                memory_logger.log(f"    WARN [Sync State]: No se recibieron datos de posición desde API para {side.upper()}. No se puede sincronizar.", level="WARN")
                return
            # --- CÓDIGO ANTERIOR (COMENTADO) ---
            # if account_to_use not in self._live_manager.get_initialized_accounts(): print(f"    ERROR SYNC: Cuenta '{account_to_use}' no inicializada."); return
            # physical_pos_raw = self._live_operations.get_active_position_details_api(self._symbol, account_to_use)
            # if physical_pos_raw is None:
            #     print(f"    WARN [Sync State]: No se recibieron datos de posición desde API para {side.upper()}. No se puede sincronizar."); return
            # --- FIN MODIFICACIÓN ---

            physical_state_data = self._position_helpers.extract_physical_state_from_api(physical_pos_raw, self._symbol, side, self._utils)
            if physical_state_data:
                self._position_state.update_physical_position_state(side, physical_state_data['avg_entry_price'], physical_state_data['total_size_contracts'], physical_state_data['total_margin_usdt'], physical_state_data.get('liquidation_price'), physical_state_data.get('timestamp', datetime.datetime.now()))
                if getattr(self._config, 'LOG_LEVEL', 'INFO') == "DEBUG": 
                    # --- INICIO MODIFICACIÓN: Usar memory_logger ---
                    memory_logger.log(f"    SYNC OK: Estado físico {side.upper()} actualizado desde API.", level="DEBUG")
                    # --- CÓDIGO ANTERIOR (COMENTADO) ---
                    # print(f"    SYNC OK: Estado físico {side.upper()} actualizado desde API.")
                    # --- FIN MODIFICACIÓN ---
            else:
                self._position_state.reset_physical_position_state(side)
                if getattr(self._config, 'LOG_LEVEL', 'INFO') == "DEBUG": 
                    # --- INICIO MODIFICACIÓN: Usar memory_logger ---
                    memory_logger.log(f"    SYNC OK: No hay posición física {side.upper()} en API. Estado reseteado.", level="DEBUG")
                    # --- CÓDIGO ANTERIOR (COMENTADO) ---
                    # print(f"    SYNC OK: No hay posición física {side.upper()} en API. Estado reseteado.")
                    # --- FIN MODIFICACIÓN ---
            current_physical_state = self._position_state.get_physical_position_state(side)
            if self._print_updates and getattr(self._config, 'LOG_LEVEL', 'INFO') == "DEBUG":
                # --- INICIO MODIFICACIÓN: Usar memory_logger ---
                memory_logger.log(f"    --- Estado Físico {side.upper()} Actualizado (JSON): ---", level="DEBUG")
                try:
                    state_to_print = current_physical_state.copy(); ts_val = state_to_print.get('last_update_ts')
                    if isinstance(ts_val, datetime.datetime): state_to_print['last_update_ts'] = self._utils.format_datetime(ts_val)
                    elif ts_val is not None: state_to_print['last_update_ts'] = str(ts_val)
                    memory_logger.log(json.dumps(state_to_print, indent=2), level="DEBUG")
                except Exception as json_e:
                    memory_logger.log(f"    ERROR [Sync State]: Format JSON: {json_e}\n    Estado crudo: {current_physical_state}", level="ERROR")
                memory_logger.log(f"    -------------------------------------------------", level="DEBUG")
                # --- CÓDIGO ANTERIOR (COMENTADO) ---
                # print(f"    --- Estado Físico {side.upper()} Actualizado (JSON): ---")
                # try:
                #     state_to_print = current_physical_state.copy(); ts_val = state_to_print.get('last_update_ts')
                #     if isinstance(ts_val, datetime.datetime): state_to_print['last_update_ts'] = self._utils.format_datetime(ts_val)
                #     elif ts_val is not None: state_to_print['last_update_ts'] = str(ts_val)
                #     print(json.dumps(state_to_print, indent=2))
                # except Exception as json_e: print(f"    ERROR [Sync State]: Format JSON: {json_e}\n    Estado crudo: {current_physical_state}")
                # print(f"    -------------------------------------------------")
                # --- FIN MODIFICACIÓN ---

        except Exception as sync_err: 
            # --- INICIO MODIFICACIÓN: Usar memory_logger ---
            memory_logger.log(f"    ERROR SYNC: Excepción durante sincronización {side.upper()}: {sync_err}", level="ERROR")
            # --- CÓDIGO ANTERIOR (COMENTADO) ---
            # print(f"    ERROR SYNC: Excepción durante sincronización {side.upper()}: {sync_err}"); traceback.print_exc()
            # --- FIN MODIFICACIÓN ---

# =============== FIN ARCHIVO: core/strategy/position_executor.py (CORREGIDO Y COMPLETO) ===============