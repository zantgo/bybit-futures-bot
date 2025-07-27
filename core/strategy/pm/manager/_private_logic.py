# core/strategy/pm/manager/_private_logic.py

"""
Módulo del Position Manager: Lógica Privada.

Contiene todos los métodos privados (que comienzan con '_') que encapsulan
la lógica de negocio interna y la gestión de estado del PositionManager.
"""
import datetime
import uuid
from typing import Any

# --- Dependencias de Tipado ---
try:
    # --- INICIO DE LA MODIFICACIÓN: Importar nuevas entidades ---
    from .._entities import Hito, Operacion, ConfiguracionOperacion, LogicalPosition
    # from .._entities import Milestone # Comentada la antigua
    # --- FIN DE LA MODIFICACIÓN ---
    from .. import _transfer_executor
except ImportError:
    # --- INICIO DE LA MODIFICACIÓN: Añadir fallbacks ---
    class Hito: pass
    class Operacion: pass
    class ConfiguracionOperacion: pass
    class LogicalPosition: pass
    # class Milestone: pass
    # --- FIN DE LA MODIFICACIÓN ---
    _transfer_executor = None

class _PrivateLogic:
    """Clase base que contiene la lógica interna y privada del PositionManager."""

    def _reset_all_states(self):
        """Resetea todos los atributos de estado del manager a sus valores iniciales."""
        self._initialized = False; self._operation_mode = "unknown"
        # -- (COMENTADO) Atributos que ahora son de la operación --
        # self._leverage = 1.0
        # self._max_logical_positions = 1; self._initial_base_position_size_usdt = 0.0
        self._total_realized_pnl_long = 0.0; self._total_realized_pnl_short = 0.0
        self._session_tp_hit = False; self._session_start_time = None
        self._global_stop_loss_roi_pct = None; self._global_take_profit_roi_pct = None
        self._milestones = []
        # self._active_trend = None # Comentado
        self.operacion_activa = None

    # --- (COMENTADO) _start_trend ---
    # def _start_trend(self, milestone: Milestone):
    #     """Activa una nueva tendencia basada en la configuración de un hito."""
    #     if self._active_trend:
    #         self._memory_logger.log(f"ADVERTENCIA: Se intentó iniciar una nueva tendencia mientras otra estaba activa.", "WARN")
    #         self._end_trend("Iniciando nueva tendencia")
        
    #     self._active_trend = {
    #         "milestone_id": milestone.id, "config": milestone.action.params,
    #         "start_time": datetime.datetime.now(datetime.timezone.utc),
    #         "trades_executed": 0,
    #         "initial_pnl": self.get_total_pnl_realized()
    #     }
    #     mode = self._active_trend['config'].mode
    #     self._memory_logger.log(f"TENDENCIA INICIADA: Modo '{mode}' activado por hito ...{milestone.id[-6:]}", "INFO")

    # --- (COMENTADO) _end_trend ---
    # def _end_trend(self, reason: str):
    #     """Finaliza la tendencia activa y vuelve al estado NEUTRAL."""
    #     if self._active_trend:
    #         mode = self._active_trend['config'].mode
    #         self._memory_logger.log(f"TENDENCIA FINALIZADA: Modo '{mode}' terminado. Razón: {reason}", "INFO")
    #         self._active_trend = None

    # --- INICIO DE LA MODIFICACIÓN: Nuevas funciones para gestionar el ciclo de vida de la Operación ---
    def _start_operation(self, config_operacion: ConfiguracionOperacion, hito_id: str):
        """Crea e inicia una nueva operación de trading."""
        initial_capital = self._balance_manager.get_initial_total_capital() + self.get_total_pnl_realized()
        
        nueva_operacion = Operacion(
            id=f"op_{uuid.uuid4()}",
            configuracion=config_operacion,
            capital_inicial_usdt=initial_capital,
            tiempo_inicio_ejecucion=datetime.datetime.now(datetime.timezone.utc)
        )
        self.operacion_activa = nueva_operacion
        tendencia = nueva_operacion.configuracion.tendencia
        self._memory_logger.log(f"OPERACIÓN INICIADA: Modo '{tendencia}' activado por hito ...{hito_id[-6:]}", "INFO")

    def _end_operation(self, reason: str):
        """Finaliza la operación activa y transiciona a una operación NEUTRAL, transfiriendo posiciones si es necesario."""
        if self.operacion_activa and self.operacion_activa.configuracion.tendencia != 'NEUTRAL':
            tendencia_anterior = self.operacion_activa.configuracion.tendencia
            self._memory_logger.log(f"OPERACIÓN FINALIZADA: Modo '{tendencia_anterior}' terminado. Razón: {reason}", "INFO")

            # Crear config para la nueva operación NEUTRAL, heredando parámetros base.
            config_neutral = ConfiguracionOperacion(
                tendencia='NEUTRAL',
                tamaño_posicion_base_usdt=self.operacion_activa.configuracion.tamaño_posicion_base_usdt,
                max_posiciones_logicas=self.operacion_activa.configuracion.max_posiciones_logicas,
                apalancamiento=self.operacion_activa.configuracion.apalancamiento,
                sl_posicion_individual_pct=0.0, tsl_activacion_pct=0.0, tsl_distancia_pct=0.0
            )

            capital_actual = self.operacion_activa.capital_inicial_usdt + self.operacion_activa.pnl_realizado_usdt
            
            op_neutral = Operacion(
                id=f"op_neutral_{uuid.uuid4()}",
                configuracion=config_neutral,
                capital_inicial_usdt=capital_actual,
                posiciones_activas=self.operacion_activa.posiciones_activas # Transferir posiciones
            )
            self.operacion_activa = op_neutral
            # Sincronizar el PositionState con las posiciones transferidas
            self._position_state.sync_logical_positions(op_neutral.posiciones_activas)
    # --- FIN DE LA MODIFICACIÓN ---

    def _can_open_new_position(self, side: str) -> bool:
        """Verifica si es posible abrir una nueva posición lógica."""
        if self._session_tp_hit or not self.operacion_activa: return False
        
        # trend_config = self._active_trend['config'] # Comentado
        config_op = self.operacion_activa.configuracion
        
        # if trend_config.limit_trade_count is not None and self._active_trend['trades_executed'] >= trend_config.limit_trade_count:
        #     return False
            
        open_positions_count = len(self.operacion_activa.posiciones_activas.get(side, []))
        if open_positions_count >= config_op.max_posiciones_logicas:
            return False
            
        if self._balance_manager.get_available_margin(side) < 1.0: # Umbral de ~1 USDT
            return False
            
        return True

    def _open_logical_position(self, side: str, entry_price: float, timestamp: datetime.datetime):
        """Calcula el margen a usar y delega la apertura al ejecutor."""
        if not self.operacion_activa: return

        config_op = self.operacion_activa.configuracion
        open_positions_count = len(self.operacion_activa.posiciones_activas.get(side, []))
        available_slots = config_op.max_posiciones_logicas - open_positions_count
        if available_slots <= 0: return

        available_margin = self._balance_manager.get_available_margin(side)
        margin_per_slot = self._utils.safe_division(available_margin, available_slots)
        
        margin_to_use = min(config_op.tamaño_posicion_base_usdt, margin_per_slot)

        if margin_to_use < 1.0:
            self._memory_logger.log(f"Apertura omitida: Margen a usar ({margin_to_use:.4f} USDT) es menor al umbral mínimo.", level="WARN")
            return

        # trend_config = self._active_trend['config'] # Comentado
        result = self._executor.execute_open(
            side=side, entry_price=entry_price, timestamp=timestamp, 
            margin_to_use=margin_to_use, sl_pct=config_op.sl_posicion_individual_pct,
            leverage=config_op.apalancamiento # Pasar el apalancamiento de la operación
        )
        if result and result.get('success'):
            # self._active_trend['trades_executed'] += 1 # Comentado
            new_pos_obj = result.get('logical_position_object')
            if new_pos_obj:
                self.operacion_activa.posiciones_activas[side].append(new_pos_obj)
                self._position_state.add_logical_position_obj(side, new_pos_obj)


    def _update_trailing_stop(self, side, position_obj: LogicalPosition, index: int, current_price: float):
        """Actualiza el estado del Trailing Stop para una posición."""
        if not self.operacion_activa: return
        
        config_op = self.operacion_activa.configuracion
        activation_pct = config_op.tsl_activacion_pct
        distance_pct = config_op.tsl_distancia_pct
        
        is_ts_active = position_obj.ts_is_active
        entry_price = position_obj.entry_price

        if not is_ts_active and activation_pct > 0 and entry_price:
            activation_price = entry_price * (1 + activation_pct / 100) if side == 'long' else entry_price * (1 - activation_pct / 100)
            if (side == 'long' and current_price >= activation_price) or (side == 'short' and current_price <= activation_price):
                self.operacion_activa.posiciones_activas[side][index].ts_is_active = True
                self.operacion_activa.posiciones_activas[side][index].ts_peak_price = current_price
        
        # Re-evaluar `is_ts_active` por si acaba de cambiar
        if self.operacion_activa.posiciones_activas[side][index].ts_is_active:
            peak_price = self.operacion_activa.posiciones_activas[side][index].ts_peak_price or current_price
            if (side == 'long' and current_price > peak_price) or (side == 'short' and current_price < peak_price):
                self.operacion_activa.posiciones_activas[side][index].ts_peak_price = current_price
            
            # Recalcular usando el peak_price potencialmente actualizado
            new_peak_price = self.operacion_activa.posiciones_activas[side][index].ts_peak_price
            new_stop_price = new_peak_price * (1 - distance_pct / 100) if side == 'long' else new_peak_price * (1 + distance_pct / 100)
            self.operacion_activa.posiciones_activas[side][index].ts_stop_price = new_stop_price

    def _close_logical_position(self, side: str, index: int, exit_price: float, timestamp: datetime.datetime, reason: str) -> bool:
        """Delega el cierre de una posición al ejecutor y maneja el resultado."""
        if not self._executor or not self.operacion_activa: return False
        
        pos_to_close = self.operacion_activa.posiciones_activas[side][index]
        
        result = self._executor.execute_close(pos_to_close, side, exit_price, timestamp, reason)
        
        if result and result.get('success', False):
            # Eliminar la posición de la operación activa
            self.operacion_activa.posiciones_activas[side].pop(index)
            # Sincronizar el PositionState
            self._position_state.remove_logical_position(side, index)

            pnl = result.get('pnl_net_usdt', 0.0)
            # Actualizar PNL de sesión (global)
            if side == 'long': self._total_realized_pnl_long += pnl
            else: self._total_realized_pnl_short += pnl
            
            # Actualizar PNL y contadores de la operación actual
            self.operacion_activa.pnl_realizado_usdt += pnl
            self.operacion_activa.comercios_cerrados_contador += 1

            transfer_amount = result.get('amount_transferable_to_profit', 0.0)
            if _transfer_executor and transfer_amount >= getattr(self._config, 'POSITION_MIN_TRANSFER_AMOUNT_USDT', 0.1):
                transferred = _transfer_executor.execute_transfer(
                    amount=transfer_amount, 
                    from_account_side=side,
                    exchange_adapter=self._exchange,
                    config=self._config,
                    balance_manager=self._balance_manager
                )
                if transferred > 0: self._balance_manager.record_real_profit_transfer(transferred)
        
        return result.get('success', False)

    def _handle_position_management_on_force_trigger(
        self,
        long_pos_action: str,
        short_pos_action: str
    ):
        """
        Ejecuta las acciones de cierre sobre las posiciones existentes antes de
        forzar una nueva tendencia.
        """
        self._memory_logger.log(
            f"Gestión de posiciones pre-activación: LONGS={long_pos_action}, SHORTS={short_pos_action}",
            "INFO"
        )
        reason = "FORCE_TRIGGER_TRANSITION"
        if long_pos_action == 'close':
            self.close_all_logical_positions('long', reason=reason)
        if short_pos_action == 'close':
            self.close_all_logical_positions('short', reason=reason)

    def _cleanup_completed_milestones(self):
        """Limpia el árbol, eliminando hitos obsoletos para evitar acumulación."""
        completed_milestones = sorted(
            [m for m in self._milestones if m.status == 'COMPLETED'],
            key=lambda m: m.created_at,
            reverse=True
        )
        
        last_completed = completed_milestones[0] if completed_milestones else None
        
        def should_keep(hito: Hito) -> bool:
            if hito.status in ['PENDING', 'ACTIVE']: return True
            if hito == last_completed: return True
            return False

        initial_count = len(self._milestones)
        self._milestones = [m for m in self._milestones if should_keep(m)]
        removed_count = initial_count - len(self._milestones)
        if removed_count > 0:
            self._memory_logger.log(f"LIMPIEZA DE HITOS: {removed_count} hito(s) obsoletos eliminados.", "INFO")