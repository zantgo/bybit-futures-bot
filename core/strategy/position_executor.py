# =============== INICIO ARCHIVO: core/strategy/position_executor.py (CORREGIDO Y ABSOLUTAMENTE COMPLETO) ===============
"""
Clase PositionExecutor: Encapsula y centraliza la lógica de ejecución.

v18.0:
- Corregida la inyección de dependencias. `pm_state` ya no se inyecta en el
  constructor, sino que se importa directamente dentro de la clase para
  romper dependencias circulares y simplificar el llamado.
- Se mantiene la lógica de SL dinámico y logging de `exit_reason`.
"""
import datetime
import uuid
import time
import traceback
import json
from typing import Optional, Dict, Any, Tuple

# --- Dependencias (inyectadas a través de __init__) ---
MAX_TRANSFER_RETRIES = 2
TRANSFER_RETRY_DELAY = 2

class PositionExecutor:
    """
    Clase responsable de la ejecución mecánica de apertura y cierre de posiciones.
    """
    def __init__(self,
                 is_live_mode: bool,
                 config: Optional[Any] = None,
                 utils: Optional[Any] = None,
                 # pm_state: Optional[Any] = None,  # <<< LÍNEA ELIMINADA SEGÚN INSTRUCCIONES >>>
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
        # self._pm_state = pm_state  # <<< LÍNEA ELIMINADA SEGÚN INSTRUCCIONES >>>
        self._balance_manager = balance_manager
        self._position_state = position_state
        self._position_calculations = position_calculations
        self._live_operations = live_operations
        self._closed_position_logger = closed_position_logger
        self._position_helpers = position_helpers
        self._live_manager = live_manager
        
        # <<< MODIFICACIÓN DE LA LISTA DE DEPENDENCIAS ESENCIALES >>>
        essential_deps = [self._config, self._utils, self._balance_manager, self._position_state, self._position_calculations, self._position_helpers]
        dep_names = ['Config', 'Utils', 'BalanceMgr', 'PositionState', 'Calculations', 'Helpers']
        if not all(essential_deps):
            missing = [name for name, mod in zip(dep_names, essential_deps) if not mod]
            raise ValueError(f"PositionExecutor: Faltan dependencias esenciales: {missing}")

        # <<< IMPORTACIÓN INTERNA DE pm_state >>>
        try:
            from . import pm_state
            self._pm_state = pm_state
        except ImportError:
            self._pm_state = None
            print("ERROR CRITICO [PositionExecutor]: No se pudo importar pm_state.")
            raise
        
        if self._is_live_mode and not self._live_operations: raise ValueError("PositionExecutor: Modo Live requiere 'live_operations'.")
        if self._is_live_mode and not self._live_manager: print("WARN [PositionExecutor Init]: Modo Live pero 'live_manager' no proporcionado. Transferencias API fallarán.")
        
        self._leverage = 1.0; self._symbol = "N/A"; self._post_order_delay = 3; self._post_close_delay = 3; self._print_updates = False; self._price_prec = 4; self._qty_prec = 3; self._pnl_prec = 2
        try:
            self._leverage = float(getattr(self._config, 'POSITION_LEVERAGE', 1.0)); self._symbol = getattr(self._config, 'TICKER_SYMBOL', 'N/A')
            self._post_order_delay = int(getattr(self._config, 'POST_ORDER_CONFIRMATION_DELAY_SECONDS', 3)); self._post_close_delay = int(getattr(self._config, 'POST_CLOSE_SYNC_DELAY_SECONDS', 3))
            self._print_updates = getattr(self._config, 'POSITION_PRINT_POSITION_UPDATES', False); self._price_prec = int(getattr(self._config, 'PRICE_PRECISION', 4)); self._qty_prec = int(getattr(self._config, 'DEFAULT_QTY_PRECISION', 3)); self._pnl_prec = int(getattr(self._config, 'PNL_PRECISION', 2))
        except Exception as e: print(f"WARN [PositionExecutor Init]: Error cacheando config: {e}. Usando defaults.")
        print(f"[PositionExecutor] Inicializado. Modo Live: {self._is_live_mode}")

    def execute_open(self, side: str, entry_price: float, timestamp: datetime.datetime, margin_to_use: Optional[float] = None, size_contracts_str_api: Optional[str] = None ) -> Dict[str, Any]:
        """Orquesta la apertura de una posición (Live o Backtest)."""
        result = {'success': False, 'api_order_id': None, 'logical_position_id': None, 'message': 'Error no especificado'}
        print(f"\n--- EXECUTE OPEN [{side.upper()}] ---")
        if side not in ['long', 'short']: result['message'] = f"Lado inválido '{side}'."; print(f"ERROR [Exec Open]: {result['message']}"); return result
        if not isinstance(entry_price, (int, float)) or entry_price <= 0: result['message'] = f"Precio entrada inválido {entry_price}."; print(f"ERROR [Exec Open]: {result['message']}"); return result
        if margin_to_use is None and size_contracts_str_api is None: result['message'] = "Debe proveer 'margin_to_use' o 'size_contracts_str_api'."; print(f"ERROR [Exec Open]: {result['message']}"); return result
        if not all([self._position_state, self._balance_manager, self._position_calculations, self._position_helpers, self._utils, self._pm_state]): result['message'] = "Faltan dependencias internas."; print(f"ERROR [Exec Open]: {result['message']}"); return result

        size_contracts_final_float = 0.0; margin_used_final = 0.0; qty_precision_used = self._qty_prec
        try:
            if size_contracts_str_api is None:
                if not isinstance(margin_to_use, (int, float)) or margin_to_use <= 1e-6: result['message'] = f"Margen a usar inválido ({margin_to_use})."; print(f"ERROR [Exec Open]: {result['message']}"); return result
                margin_used_final = margin_to_use; print(f"  Calculando tamaño desde Margen: {margin_used_final:.4f} USDT")
                calc_qty_result = self._position_helpers.calculate_and_round_quantity(margin_usdt=margin_used_final, entry_price=entry_price, leverage=self._leverage, symbol=self._symbol, is_live=self._is_live_mode)
                if not calc_qty_result['success']: result['message'] = calc_qty_result['error']; print(f"ERROR [Exec Open]: {result['message']}"); return result
                size_contracts_final_float = calc_qty_result['qty_float']; size_contracts_str_api = calc_qty_result['qty_str']; qty_precision_used = calc_qty_result['precision']
            else:
                print(f"  Usando tamaño pre-calculado: {size_contracts_str_api}")
                size_contracts_final_float = self._utils.safe_float_convert(size_contracts_str_api, 0.0)
                if size_contracts_final_float <= 1e-12: result['message'] = f"Tamaño provisto inválido ({size_contracts_str_api})."; print(f"ERROR [Exec Open]: {result['message']}"); return result
                margin_used_final = self._utils.safe_division(size_contracts_final_float * entry_price, self._leverage, default=0.0)
                if margin_used_final <= 0: print(f"WARN [Exec Open]: Margen recalculado para tamaño provisto es {margin_used_final}.")
            print(f"  Tamaño Final: {size_contracts_final_float:.{qty_precision_used}f} ({size_contracts_str_api} para API), Margen Usado Estimado: {margin_used_final:.4f} USDT")
        except Exception as e: result['message'] = f"Excepción calculando tamaño/margen: {e}"; print(f"ERROR [Exec Open]: {result['message']}"); traceback.print_exc(); return result

        logical_position_id = str(uuid.uuid4())
        
        individual_sl_pct = self._pm_state.get_individual_stop_loss_pct()
        stop_loss_price = self._position_calculations.calculate_stop_loss(side, entry_price, individual_sl_pct)
        
        est_liq_price_individual = self._position_calculations.calculate_liquidation_price(
            side=side, avg_entry_price=entry_price, leverage=self._leverage
        )
        new_position_data = {
            'id': logical_position_id,
            'entry_timestamp': timestamp,
            'entry_price': entry_price,
            'margin_usdt': margin_used_final,
            'size_contracts': size_contracts_final_float,
            'leverage': self._leverage,
            'stop_loss_price': stop_loss_price,
            'est_liq_price': est_liq_price_individual,
            'ts_is_active': False,
            'ts_peak_price': None,
            'ts_stop_price': None,
            'api_order_id': None,
            'api_avg_fill_price': None,
            'api_filled_qty': None
        }
        result['logical_position_id'] = logical_position_id

        execution_success = False; api_order_id = None
        try:
            if self._is_live_mode:
                print(f"  Ejecutando Apertura LIVE API...");
                if not self._live_operations: raise RuntimeError("Live Operations no disponible")
                target_account = getattr(self._config, 'ACCOUNT_LONGS' if side == 'long' else 'ACCOUNT_SHORTS', None); main_account = getattr(self._config, 'ACCOUNT_MAIN', 'main'); account_to_use = target_account if target_account and target_account in self._live_manager.get_initialized_accounts() else main_account
                if account_to_use not in self._live_manager.get_initialized_accounts(): raise RuntimeError(f"Cuenta operativa '{account_to_use}' no inicializada.")
                order_side_api = "Buy" if side == 'long' else "Sell"; pos_idx = 1 if side == 'long' else 2
                api_response = self._live_operations.place_market_order(symbol=self._symbol, side=order_side_api, quantity=size_contracts_str_api, reduce_only=False, position_idx=pos_idx, account_name=account_to_use)
                if api_response and api_response.get('retCode') == 0:
                    execution_success = True; api_order_id = api_response.get('result', {}).get('orderId', 'N/A'); print(f"  -> ÉXITO API: Orden Market {order_side_api} aceptada. OrderID: {api_order_id}")
                else:
                    ret_code = api_response.get('retCode', -1) if api_response else -1; ret_msg = api_response.get('retMsg', 'N/A') if api_response else 'N/A'; result['message'] = f"Fallo API orden Market {order_side_api}. Code={ret_code}, Msg='{ret_msg}'"; print(f"  -> ERROR API: {result['message']}")
            else:
                print(f"  Ejecutando Apertura BACKTEST (Simulada)..."); execution_success = True; api_order_id = None; print(f"  -> ÉXITO Simulado.")
            if execution_success:
                self._balance_manager.decrease_operational_margin(side, margin_used_final)
        except Exception as exec_err: result['message'] = f"Excepción durante ejecución: {exec_err}"; print(f"ERROR [Exec Open]: {result['message']}"); traceback.print_exc(); execution_success = False

        add_ok = False; sync_ok = not self._is_live_mode; updated_pos_details = None
        if execution_success:
            try:
                new_position_data['api_order_id'] = api_order_id
                add_ok = self._position_state.add_logical_position(side, new_position_data)
                if not add_ok: result['message'] = f"Ejecución OK pero falló añadir a PS pos ID {logical_position_id}."; print(f"ERROR SEVERE [Exec Open]: {result['message']}"); result['success'] = False; return result
                print(f"  Position State: Posición lógica ...{logical_position_id[-6:]} añadida (datos estimados).")
                if self._print_updates: print("\n  --- ESTADO POST-APERTURA (Lógica Añadida) ---"); self._position_state.display_logical_table(side); print("  " + "-"*60)
                if self._is_live_mode and api_order_id and api_order_id != 'N/A':
                    print(f"\n  --- SYNC PRECIO/QTY POST-APERTURA ---"); print(f"    Esperando {self._post_order_delay}s..."); time.sleep(self._post_order_delay)
                    sync_ok = self._position_state.sync_new_logical_entry_price(side, logical_position_id, api_order_id)
                    if sync_ok:
                        print(f"    Sincronización de precio/tamaño OK para pos ...{logical_position_id[-6:]}.")
                        updated_pos_after_sync = self._position_state.get_position_by_id(side, logical_position_id)
                        if updated_pos_after_sync:
                            new_entry_price_synced = updated_pos_after_sync.get('entry_price', entry_price)
                            update_details = {}
                            est_liq_price_synced = self._position_calculations.calculate_liquidation_price(
                                side=side, avg_entry_price=new_entry_price_synced, leverage=updated_pos_after_sync.get('leverage', self._leverage)
                            )
                            if est_liq_price_synced is not None:
                                update_details['est_liq_price'] = est_liq_price_synced
                                print(f"    Precio Liq. Estimado Individual Actualizado: {est_liq_price_synced:.{self._price_prec}f}")
                            if abs(new_entry_price_synced - entry_price) > 1e-9:
                                new_sl_price_synced = self._position_calculations.calculate_stop_loss(side, new_entry_price_synced, individual_sl_pct)
                                if new_sl_price_synced is not None:
                                    update_details['stop_loss_price'] = new_sl_price_synced
                                    print(f"    Stop Loss Price Individual Actualizado: {new_sl_price_synced:.{self._price_prec}f}")
                            if update_details:
                                self._position_state.update_logical_position_details(side, logical_position_id, update_details)
                            updated_pos_details = updated_pos_after_sync
                    else:
                        print(f"WARN [Exec Open]: Falló sync post-apertura para pos ...{logical_position_id[-6:]}. Usando datos estimados!")
                    if self._print_updates:
                        if updated_pos_details: print(f"      > Px Entrada Real: {updated_pos_details.get('entry_price', 0.0):.{self._price_prec}f}, Tamaño Real: {updated_pos_details.get('size_contracts', 0.0):.{qty_precision_used}f}")
                        else: print("      (WARN: No se pudieron leer detalles actualizados)")
                        print("\n  --- ESTADO POST-SYNC PRECIO/QTY ---"); self._position_state.display_logical_table(side); print("  " + "-"*60)

                print(f"  Actualizando estado físico agregado...")
                open_positions_now = self._position_state.get_open_logical_positions(side)
                aggregates = self._position_calculations.calculate_physical_aggregates(open_positions_now)
                liq_price_aggregate = self._position_calculations.calculate_liquidation_price(side, aggregates['avg_entry_price'], self._leverage)
                ts_for_phys_update = timestamp
                if self._is_live_mode and sync_ok and updated_pos_details:
                    updated_ts = updated_pos_details.get('entry_timestamp')
                    if isinstance(updated_ts, datetime.datetime): ts_for_phys_update = updated_ts
                self._position_state.update_physical_position_state(side, aggregates.get('avg_entry_price', 0.0), aggregates.get('total_size_contracts', 0.0), aggregates.get('total_margin_usdt', 0.0), liq_price_aggregate, ts_for_phys_update)
                print(f"  -> Estado físico agregado {side.upper()} recalculado.")
            except Exception as state_err: result['message'] = f"Ejecución OK pero falló post-proceso: {state_err}"; print(f"ERROR SEVERE [Exec Open]: {result['message']}"); traceback.print_exc(); result['success'] = False; return result

        result['success'] = execution_success and add_ok
        result['api_order_id'] = api_order_id
        if result['success'] and self._is_live_mode and not sync_ok and api_order_id and api_order_id != 'N/A':
             result['message'] = f"Apertura ÉXITO (API+Lógica), pero sync inicial Px/Qty falló (pos ID: ...{result.get('logical_position_id', '??')[-6:]}). Usando datos estimados."
             print(f"  INFO [Exec Open]: {result['message']}")
        elif result['success']:
            result['message'] = f"Apertura {side.upper()} exitosa."

        print(f"--- FIN EXECUTE OPEN [{side.upper()}] -> Success: {result['success']} ---")
        return result

    def execute_close(self, side: str, position_index: int, exit_price: float,
                      timestamp: datetime.datetime, exit_reason: str = "UNKNOWN") -> Dict[str, Any]:
        result = {
            'success': False, 'pnl_net_usdt': 0.0, 'amount_reinvested_in_operational_margin': 0.0,
            'amount_transferable_to_profit': 0.0, 'log_data': {}, 'message': 'Error no especificado',
            'closed_position_id': None
        }
        print(f"\n--- EXECUTE CLOSE [{side.upper()} Idx: {position_index}, Razón: {exit_reason}] ---")

        if side not in ['long', 'short']: result['message'] = "Lado inválido."; print(f"ERROR [Exec Close]: {result['message']}"); return result
        if not isinstance(exit_price, (int, float)) or exit_price <= 0: result['message'] = "Precio salida inválido."; print(f"ERROR [Exec Close]: {result['message']}"); return result
        if not all([self._position_state, self._balance_manager, self._position_calculations, self._position_helpers, self._utils]): result['message'] = "Faltan dependencias internas."; print(f"ERROR [Exec Close]: {result['message']}"); return result

        pos_to_close_data = None; log_data_partial = {}; size_contracts_str_api = "0.0";
        pos_id_for_log = 'N/A_PreValid'; entry_price_for_calc = 0.0; initial_margin_for_calc = 0.0; size_contracts_for_calc = 0.0; entry_ts_for_calc = None; leverage_for_calc = self._leverage
        try:
            open_positions = self._position_state.get_open_logical_positions(side)
            if not (0 <= position_index < len(open_positions)): result['message'] = f"Índice {position_index} fuera de rango."; print(f"ERROR [Exec Close]: {result['message']}"); return result
            pos_to_close_data = open_positions[position_index]
            pos_id_for_log = pos_to_close_data.get('id', 'N/A_DataErr'); log_data_partial = {'id': pos_id_for_log, 'side': side, 'index_closed': position_index}
            result['log_data'] = log_data_partial; result['closed_position_id'] = pos_id_for_log

            size_contracts_for_calc = self._utils.safe_float_convert(pos_to_close_data.get('size_contracts'), 0.0)
            entry_price_for_calc = self._utils.safe_float_convert(pos_to_close_data.get('entry_price'), 0.0)
            initial_margin_for_calc = self._utils.safe_float_convert(pos_to_close_data.get('margin_usdt'), 0.0)
            entry_ts_for_calc = pos_to_close_data.get('entry_timestamp')
            leverage_for_calc = self._utils.safe_float_convert(pos_to_close_data.get('leverage'), self._leverage)

            if size_contracts_for_calc <= 1e-12: result['message'] = f"Tamaño lógico <= 0 para pos ID ...{pos_id_for_log[-6:]}. Considerado ya cerrado."; print(f"WARN [Exec Close]: {result['message']}"); result['success'] = True; return result

            format_qty_result = self._position_helpers.format_quantity_for_api(quantity_float=size_contracts_for_calc, symbol=self._symbol, is_live=self._is_live_mode)
            if not format_qty_result['success']: result['message'] = f"Error formateando Qty para API ({format_qty_result['error']}) Pos ID ...{pos_id_for_log[-6:]}."; print(f"ERROR [Exec Close]: {result['message']}"); return result
            size_contracts_str_api = format_qty_result['qty_str']
        except Exception as data_err: result['message'] = f"Excepción obteniendo datos/formateando: {data_err}"; print(f"ERROR [Exec Close]: {result['message']}"); traceback.print_exc(); return result

        execution_success = False; api_order_id_close = None; ret_code: Optional[int] = None; ret_msg: Optional[str] = None
        try:
            if self._is_live_mode:
                print(f"  Ejecutando Cierre LIVE API (ReduceOnly)...")
                if not self._live_operations: raise RuntimeError("Live Operations no disponible")
                target_account = getattr(self._config, 'ACCOUNT_LONGS' if side == 'long' else 'ACCOUNT_SHORTS', None); main_account = getattr(self._config, 'ACCOUNT_MAIN', 'main'); account_to_use = target_account if target_account and target_account in self._live_manager.get_initialized_accounts() else main_account
                if account_to_use not in self._live_manager.get_initialized_accounts(): raise RuntimeError(f"Cuenta operativa '{account_to_use}' no inicializada.")
                close_order_side_api = "Sell" if side == 'long' else "Buy"; pos_idx = 1 if side == 'long' else 2
                api_response = self._live_operations.place_market_order(symbol=self._symbol, side=close_order_side_api, quantity=size_contracts_str_api, reduce_only=True, position_idx=pos_idx, account_name=account_to_use)
                if api_response and api_response.get('retCode') == 0:
                    execution_success = True; api_order_id_close = api_response.get('result', {}).get('orderId', 'N/A'); print(f"  -> ÉXITO API: Orden Cierre Market {close_order_side_api} aceptada. OrderID: {api_order_id_close}")
                else:
                    if api_response: ret_code = api_response.get('retCode', -1); ret_msg = api_response.get('retMsg', 'N/A')
                    else: ret_code = -1; ret_msg = 'No API Response'
                    result['message'] = f"Fallo API orden Cierre Market {close_order_side_api}. Code={ret_code}, Msg='{ret_msg}'"; print(f"  -> ERROR API: {result['message']}")
                    if ret_code == 110001: execution_success = True; print("  WARN [Exec Close]: Orden/Posición no encontrada (110001). Permitiendo limpieza lógica.")
            else:
                print(f"  Ejecutando Cierre BACKTEST (Simulado)..."); execution_success = True; api_order_id_close = None; print(f"  -> ÉXITO Simulado.")
        except Exception as exec_err: result['message'] = f"Excepción durante ejecución: {exec_err}"; print(f"ERROR [Exec Close]: {result['message']}"); traceback.print_exc(); execution_success = False

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
                    print(f"  Position State: Posición lógica ...{pos_id_for_log[-6:]} removida.")
                elif ret_code == 110001:
                    remove_ok = True; print(f"  INFO [Exec Close]: Pos lógica idx {position_index} (ID: ...{pos_id_for_log[-6:]}) no encontrada, consistente con API 110001.")
                else:
                    result['message'] = f"Ejecución OK pero falló remover pos lógica idx {position_index} (ID: ...{pos_id_for_log[-6:]})."; print(f"ERROR SEVERE [Exec Close]: {result['message']}"); result['success'] = False; return result

                calc_results = self._position_calculations.calculate_pnl_commission_reinvestment(side, entry_price_for_calc, exit_price, size_contracts_for_calc)
                pnl_gross_usdt, commission_usdt, pnl_net_usdt = calc_results['pnl_gross_usdt'], calc_results['commission_usdt'], calc_results['pnl_net_usdt']
                amount_reinvested_op_margin, amount_transferable_profit = calc_results['amount_reinvested_in_operational_margin'], calc_results['amount_transferable_to_profit']

                result.update({
                    'pnl_net_usdt': pnl_net_usdt,
                    'amount_reinvested_in_operational_margin': amount_reinvested_op_margin,
                    'amount_transferable_to_profit': amount_transferable_profit
                })
                print(f"  Cálculos PNL: Neto={pnl_net_usdt:+.{self._pnl_prec}f}, Reinv Op.Margin={amount_reinvested_op_margin:.{self._pnl_prec}f}, Transf. Profit={amount_transferable_profit:.{self._pnl_prec}f}")

                if remove_ok and removed_pos_data:
                    margin_to_return_to_op = initial_margin_for_calc + amount_reinvested_op_margin
                    self._balance_manager.increase_operational_margin(side, margin_to_return_to_op)
                elif remove_ok and ret_code == 110001:
                     print("  Balance Manager: No se modifica margen operativo (posición no encontrada).")

                print(f"  Actualizando estado físico agregado post-remoción...")
                open_positions_now = self._position_state.get_open_logical_positions(side);
                if open_positions_now:
                    aggregates = self._position_calculations.calculate_physical_aggregates(open_positions_now)
                    liq_price = self._position_calculations.calculate_liquidation_price(side, aggregates['avg_entry_price'], self._leverage)
                    self._position_state.update_physical_position_state(side, aggregates.get('avg_entry_price', 0.0), aggregates.get('total_size_contracts', 0.0), aggregates.get('total_margin_usdt', 0.0), liq_price, timestamp)
                    print(f"  -> Estado físico {side.upper()} recalculado (pos restantes: {len(open_positions_now)}).")
                else:
                    self._position_state.reset_physical_position_state(side)
                    print(f"  -> Estado físico {side.upper()} reseteado (no quedan pos lógicas).")

                log_entry_ts_str = self._utils.format_datetime(entry_ts_for_calc) if entry_ts_for_calc else "N/A"; log_exit_ts_str = self._utils.format_datetime(timestamp); duration = (timestamp - entry_ts_for_calc).total_seconds() if isinstance(entry_ts_for_calc, datetime.datetime) else None
                
                log_data_final = {
                    "id": pos_id_for_log, "side": side, "entry_timestamp": log_entry_ts_str,
                    "exit_timestamp": log_exit_ts_str, "duration_seconds": duration,
                    "entry_price": entry_price_for_calc, "exit_price": exit_price,
                    "size_contracts": size_contracts_for_calc, "margin_usdt": initial_margin_for_calc,
                    "leverage": leverage_for_calc, "pnl_gross_usdt": pnl_gross_usdt,
                    "commission_usdt": commission_usdt, "pnl_net_usdt": pnl_net_usdt,
                    "reinvest_usdt": amount_reinvested_op_margin,
                    "transfer_usdt": amount_transferable_profit,
                    "api_close_order_id": api_order_id_close,
                    "api_ret_code_close": ret_code, "api_ret_msg_close": ret_msg,
                    "exit_reason": exit_reason # Añadir la razón del cierre al log
                }
                
                result['log_data'] = log_data_final

                if self._closed_position_logger and hasattr(self._closed_position_logger, 'log_closed_position'):
                    try: self._closed_position_logger.log_closed_position(log_data_final)
                    except Exception as log_e: print(f"ERROR [Exec Close]: Fallo log pos cerrada ID {pos_id_for_log}: {log_e}")

                if self._print_updates: print("\n  --- ESTADO POST-CIERRE (Lógica Eliminada) ---"); self._position_state.display_logical_table(side); print("  " + "-"*60)
            except Exception as state_err: result['message'] = f"Ejecución OK pero falló post-proceso: {state_err}"; print(f"ERROR SEVERE [Exec Close]: {result['message']}"); traceback.print_exc(); result['success'] = False; return result

        if self._is_live_mode and execution_success and remove_ok:
            print(f"\n  --- SYNC FISICO POST-CIERRE ---"); print(f"    Esperando {self._post_close_delay}s..."); time.sleep(self._post_close_delay)
            try:
                self.sync_physical_state(side);
                if self._print_updates: print("\n  --- ESTADO POST-SYNC FISICO ---"); self._position_state.display_logical_table(side); print("  " + "-"*60)
            except Exception as sync_e: print(f"ERROR [Exec Close]: Excepción sync post-cierre: {sync_e}"); traceback.print_exc()

        result['success'] = execution_success and remove_ok
        if not result['success'] and not result['message']: result['message'] = "Fallo en cierre por razón desconocida."
        elif result['success']: result['message'] = f"Cierre {side.upper()} idx {position_index} exitoso."

        print(f"--- FIN EXECUTE CLOSE [{side.upper()} Idx: {position_index}] -> Success: {result['success']} ---")
        return result

    def execute_transfer(self, amount: float, from_account_side: str) -> float:
        print(f"DEBUG [Exec Transfer]: Solicitando transferencia API/Sim de {amount:.4f} desde {from_account_side.upper()}")
        transferred_amount_api_or_sim = 0.0
        if amount <= 1e-9: print("  INFO [Exec Transfer]: Monto <= 0, omitida."); return 0.0

        try:
            if self._is_live_mode:
                if not self._live_manager or not self._live_operations or not self._config:
                    print("ERROR [Exec Transfer Live]: live_manager/live_ops/config no disponibles."); return 0.0
                from_acc_name = getattr(self._config, 'ACCOUNT_LONGS' if from_account_side == 'long' else 'ACCOUNT_SHORTS', None)
                to_acc_name = getattr(self._config, 'ACCOUNT_PROFIT', None)
                if not from_acc_name or not to_acc_name: print(f"ERROR [Exec Transfer Live]: Cuenta origen/destino no definida."); return 0.0
                loaded_uids = getattr(self._config, 'LOADED_UIDS', {}); from_uid = loaded_uids.get(from_acc_name); to_uid = loaded_uids.get(to_acc_name)
                if not from_uid or not to_uid: print(f"ERROR [Exec Transfer Live]: UIDs no encontrados."); return 0.0
                try: from_uid_int = int(from_uid); to_uid_int = int(to_uid)
                except ValueError: print(f"ERROR [Exec Transfer Live]: UIDs inválidos (no int)."); return 0.0

                TRANSFER_API_PRECISION = 4; amount_str = f"{amount:.{TRANSFER_API_PRECISION}f}"
                main_acc_for_call = getattr(self._config, 'ACCOUNT_MAIN', 'main');
                session_for_call = self._live_manager.get_client(main_acc_for_call)
                if not session_for_call: session_for_call = self._live_manager.get_client(from_acc_name)
                if not session_for_call: print(f"ERROR [Exec Transfer Live]: Sesión API no disponible."); return 0.0

                for attempt in range(MAX_TRANSFER_RETRIES):
                    print(f"  API Call Attempt #{attempt + 1}/{MAX_TRANSFER_RETRIES}: create_universal_transfer(...)")
                    resp = None
                    try:
                        resp = self._live_manager.create_universal_transfer(
                            session=session_for_call, coin="USDT", amount=amount_str,
                            from_member_id=from_uid_int, to_member_id=to_uid_int,
                            from_account_type=getattr(self._config, 'UNIVERSAL_TRANSFER_FROM_TYPE', 'UNIFIED'),
                            to_account_type=getattr(self._config, 'UNIVERSAL_TRANSFER_TO_TYPE', 'UNIFIED')
                        )
                    except Exception as api_call_err:
                         print(f"    ERROR [Exec Transfer]: Excepción en llamada API (Intento {attempt + 1}): {api_call_err}")
                         if attempt < MAX_TRANSFER_RETRIES - 1: time.sleep(TRANSFER_RETRY_DELAY); continue
                         else: print("    Fallo API después de máximos reintentos por excepción."); break
                    if resp and resp.get('retCode') == 0:
                        transfer_id = resp.get('result', {}).get('transferId', 'N/A')
                        print(f"    -> ÉXITO API Transfer: ID={transfer_id}, Status={resp.get('result',{}).get('status','?')}")
                        transferred_amount_api_or_sim = amount
                        break
                    elif resp:
                        ret_code_t = resp.get('retCode', -1); ret_msg_t = resp.get('retMsg', 'N/A')
                        print(f"    -> FALLO API Transfer (Intento {attempt + 1}): Code={ret_code_t}, Msg='{ret_msg_t}'")
                        non_retryable_codes = [131200, 131001, 131228, 10003, 10005, 10019, 131214, 131204, 131206, 131210]
                        if ret_code_t in non_retryable_codes: print("      Error no recuperable."); transferred_amount_api_or_sim = 0.0; break
                        if attempt < MAX_TRANSFER_RETRIES - 1: time.sleep(TRANSFER_RETRY_DELAY)
                        else: print("    Fallo API después de máximos reintentos."); transferred_amount_api_or_sim = 0.0
                    else:
                        print(f"    -> FALLO API Transfer (Intento {attempt + 1}): No se recibió respuesta.")
                        if attempt < MAX_TRANSFER_RETRIES - 1: time.sleep(TRANSFER_RETRY_DELAY)
                        else: print("    Fallo API sin respuesta después de máximos reintentos."); transferred_amount_api_or_sim = 0.0
            else:
                print("  Ejecutando Transferencia BACKTEST (Simulada)...")
                if not self._balance_manager: print("ERROR [Exec Transfer BT]: balance_manager no disponible."); return 0.0
                sim_success = self._balance_manager.simulate_profit_transfer(from_account_side, amount)
                if sim_success: print(f"  -> ÉXITO Simulación Transfer: {amount:.4f} USDT reflejado en BalanceManager."); transferred_amount_api_or_sim = amount
                else: print(f"  -> FALLO Simulación Transfer."); transferred_amount_api_or_sim = 0.0
        except Exception as e:
            print(f"ERROR [Exec Transfer]: Excepción general: {e}"); traceback.print_exc(); transferred_amount_api_or_sim = 0.0

        print(f"  Monto Efectivamente Transferido (API o Sim): {transferred_amount_api_or_sim:.4f} USDT")
        return transferred_amount_api_or_sim


    def sync_physical_state(self, side: str):
        if not self._is_live_mode: print("WARN [Sync State]: Solo aplicable en modo Live."); return
        if not all([self._position_state, self._live_operations, self._config, self._utils, self._position_helpers, self._live_manager]): print("WARN [Sync State]: Faltan dependencias."); return
        print(f"  ... Sincronizando estado físico {side.upper()} con API ...")
        physical_state_data = None
        try:
            target_account = getattr(self._config, 'ACCOUNT_LONGS' if side == 'long' else 'ACCOUNT_SHORTS', None); main_acc = getattr(self._config, 'ACCOUNT_MAIN', 'main'); account_to_use = target_account if target_account and target_account in self._live_manager.get_initialized_accounts() else main_acc
            if account_to_use not in self._live_manager.get_initialized_accounts(): print(f"    ERROR SYNC: Cuenta '{account_to_use}' no inicializada."); return
            physical_pos_raw = self._live_operations.get_active_position_details_api(self._symbol, account_to_use)
            if physical_pos_raw is None:
                print(f"    WARN [Sync State]: No se recibieron datos de posición desde API para {side.upper()}. No se puede sincronizar."); return
            physical_state_data = self._position_helpers.extract_physical_state_from_api(physical_pos_raw, self._symbol, side, self._utils)
            if physical_state_data:
                self._position_state.update_physical_position_state(side, physical_state_data['avg_entry_price'], physical_state_data['total_size_contracts'], physical_state_data['total_margin_usdt'], physical_state_data.get('liquidation_price'), physical_state_data.get('timestamp', datetime.datetime.now()))
                print(f"    SYNC OK: Estado físico {side.upper()} actualizado desde API.")
            else:
                self._position_state.reset_physical_position_state(side)
                print(f"    SYNC OK: No hay posición física {side.upper()} en API. Estado reseteado.")
            current_physical_state = self._position_state.get_physical_position_state(side)
            print(f"    --- Estado Físico {side.upper()} Actualizado (JSON): ---")
            try:
                state_to_print = current_physical_state.copy(); ts_val = state_to_print.get('last_update_ts')
                if isinstance(ts_val, datetime.datetime): state_to_print['last_update_ts'] = self._utils.format_datetime(ts_val)
                elif ts_val is not None: state_to_print['last_update_ts'] = str(ts_val)
                print(json.dumps(state_to_print, indent=2))
            except Exception as json_e: print(f"    ERROR [Sync State]: Format JSON: {json_e}\n    Estado crudo: {current_physical_state}")
            print(f"    -------------------------------------------------")
        except Exception as sync_err: print(f"    ERROR SYNC: Excepción durante sincronización {side.upper()}: {sync_err}"); traceback.print_exc()

# =============== FIN ARCHIVO: core/strategy/position_executor.py (CORREGIDO Y ABSOLUTAMENTE COMPLETO) ===============