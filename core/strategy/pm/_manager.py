"""
Módulo del Position Manager Principal.

Define la clase PositionManager, el corazón de la gestión de posiciones,
capital y riesgo. Esta clase orquesta sus componentes dependientes (BalanceManager,
PositionState, PositionExecutor) y encapsula el estado general, las reglas y
las acciones de la estrategia.

v1.0: Creado como parte de la refactorización a Clean Architecture.
"""
import datetime
import threading
import time
import copy
from typing import Optional, Dict, Any, Tuple, List

# --- Dependencias del Proyecto (inyectadas) ---
# Se importan las entidades para el type-hinting y la creación de instancias
from ._entities import Milestone, MilestoneCondition, MilestoneAction
# Se importa el transfer_executor para usarlo directamente
from . import _transfer_executor

class PositionManager:
    """
    Orquesta la gestión de posiciones, capital, riesgo y automatización.
    """
    def __init__(self,
                 # --- Clases de Dependencia ---
                 balance_manager: Any,
                 position_state: Any,
                 executor: Any,
                 # --- Módulos de Utilidad ---
                 config: Any,
                 utils: Any,
                 memory_logger: Any,
                 connection_ticker: Any,
                 helpers: Any, # Módulo _helpers
                 # --- Dependencias para Lógica Externa ---
                 live_operations: Any,
                 connection_manager: Any
                 ):
        """
        Inicializa la instancia del PositionManager con todas sus dependencias.
        """
        # --- Inyección de Dependencias ---
        self._balance_manager = balance_manager
        self._position_state = position_state
        self._executor = executor
        self._config = config
        self._utils = utils
        self._memory_logger = memory_logger
        self._connection_ticker = connection_ticker
        self._helpers = helpers
        self._live_operations = live_operations
        self._connection_manager = connection_manager

        # --- Estado General (Migrado desde _state.py) ---
        self._initialized: bool = False
        self._operation_mode: str = "unknown"
        self._leverage: float = 1.0
        self._max_logical_positions: int = 1
        self._initial_base_position_size_usdt: float = 0.0
        self._dynamic_base_size_long: float = 0.0
        self._dynamic_base_size_short: float = 0.0
        self._global_stop_loss_roi_pct: Optional[float] = None
        self._global_take_profit_roi_pct: Optional[float] = None
        self._session_tp_hit: bool = False
        self._individual_stop_loss_pct: float = 0.0
        self._trailing_stop_activation_pct: float = 0.0
        self._trailing_stop_distance_pct: float = 0.0

        # --- Estado de Límites de Sesión y Tendencia ---
        self._session_start_time: Optional[datetime.datetime] = None
        self._session_max_duration_minutes: int = 0
        self._session_time_limit_action: str = "NEUTRAL"
        self._trend_start_time: Optional[datetime.datetime] = None
        self._trend_limit_duration_minutes: Optional[int] = None
        self._trend_limit_tp_roi_pct: Optional[float] = None
        self._trend_limit_sl_roi_pct: Optional[float] = None
        
        # --- Estado de PNL ---
        self._total_realized_pnl_long: float = 0.0
        self._total_realized_pnl_short: float = 0.0

        # --- Estado del Modo Manual ---
        self._manual_mode: str = "NEUTRAL"
        self._manual_trade_limit: Optional[int] = None
        self._manual_trades_executed: int = 0
        self._initial_pnl_at_trend_start: float = 0.0
        
        # --- Estado de Tendencia Automática (Legado) ---
        self._trend_status: Dict[str, Any] = {}

        # --- Estado del Árbol de Decisiones ---
        self._milestones: List[Milestone] = []

    # ==============================================================================
    # --- MÉTODOS PÚBLICOS PRINCIPALES (Puntos de Entrada del Sistema) ---
    # ==============================================================================

    def initialize(self, operation_mode: str, base_size: float, max_pos: int, real_balances: Dict):
        """Inicializa el PM y todos sus componentes para una nueva sesión."""
        self._reset_all_states()
        self._operation_mode = operation_mode
        
        # Cargar configuración inicial
        self._leverage = getattr(self._config, 'POSITION_LEVERAGE', 1.0)
        self._max_logical_positions = max_pos
        self._initial_base_position_size_usdt = base_size
        self._global_stop_loss_roi_pct = getattr(self._config, 'SESSION_STOP_LOSS_ROI_PCT', 0.0)
        self._global_take_profit_roi_pct = getattr(self._config, 'SESSION_TAKE_PROFIT_ROI_PCT', 0.0)
        self._session_max_duration_minutes = getattr(self._config, 'SESSION_MAX_DURATION_MINUTES', 0)
        self._session_time_limit_action = getattr(self._config, 'SESSION_TIME_LIMIT_ACTION', "NEUTRAL")
        self._individual_stop_loss_pct = getattr(self._config, 'POSITION_INDIVIDUAL_STOP_LOSS_PCT', 0.0)
        self._trailing_stop_activation_pct = getattr(self._config, 'TRAILING_STOP_ACTIVATION_PCT', 0.0)
        self._trailing_stop_distance_pct = getattr(self._config, 'TRAILING_STOP_DISTANCE_PCT', 0.0)
        self._session_start_time = datetime.datetime.now()

        # Inicializar componentes dependientes
        self._balance_manager.set_state_manager(self)
        self._balance_manager.initialize(real_balances, base_size, max_pos)
        self._position_state.initialize(is_live_mode=True)
        
        self._initialized = True
        self._memory_logger.log("PositionManager y sus componentes han sido inicializados.", level="INFO")

    def handle_low_level_signal(self, signal: str, entry_price: float, timestamp: datetime.datetime):
        """Punto de entrada para señales desde el `event_processor`."""
        if not self._initialized: return

        side_to_open = 'long' if signal == "BUY" else 'short'
        side_allowed_by_mode = (side_to_open == 'long' and self._manual_mode in ["LONG_ONLY", "LONG_SHORT"]) or \
                               (side_to_open == 'short' and self._manual_mode in ["SHORT_ONLY", "LONG_SHORT"])
        
        if side_allowed_by_mode and self._can_open_new_position(side_to_open):
            self._open_logical_position(side_to_open, entry_price, timestamp)

    def check_and_close_positions(self, current_price: float, timestamp: datetime.datetime):
        """Revisa SL y TS para todas las posiciones abiertas en cada tick."""
        if not self._initialized: return

        for side in ['long', 'short']:
            open_positions = self._position_state.get_open_logical_positions(side)
            if not open_positions: continue

            indices_to_close = []
            reasons = {}
            for i, pos in enumerate(open_positions):
                pos_id = pos.get('id')
                if not pos_id: continue

                sl_price = pos.get('stop_loss_price')
                if sl_price and ((side == 'long' and current_price <= sl_price) or (side == 'short' and current_price >= sl_price)):
                    indices_to_close.append(i); reasons[i] = "SL"; continue

                self._update_trailing_stop(side, pos, current_price)
                ts_stop_price = pos.get('ts_stop_price')
                if ts_stop_price and ((side == 'long' and current_price <= ts_stop_price) or (side == 'short' and current_price >= ts_stop_price)):
                    indices_to_close.append(i); reasons[i] = "TS"

            for index in sorted(list(set(indices_to_close)), reverse=True):
                self._close_logical_position(side, index, current_price, timestamp, reason=reasons.get(index, "UNKNOWN"))

    # ==============================================================================
    # --- MÉTODOS PÚBLICOS DE LA API (Para la TUI y otros consumidores) ---
    # ==============================================================================

    def is_initialized(self) -> bool: return self._initialized

    def get_position_summary(self) -> dict:
        # Lógica completa de get_position_summary de _api.py
        if not self._initialized: return {"error": "PM no inicializado"}
        open_longs = self._position_state.get_open_logical_positions('long')
        open_shorts = self._position_state.get_open_logical_positions('short')
        from dataclasses import asdict
        milestones_as_dicts = [asdict(m) for m in self._milestones]

        return {
            "initialized": True, "operation_mode": self._operation_mode,
            "manual_mode_status": self.get_manual_state(), "trend_status": self.get_trend_state(),
            "leverage": self._leverage, "max_logical_positions": self._max_logical_positions,
            "initial_base_position_size_usdt": self._initial_base_position_size_usdt,
            "dynamic_base_size_long": self._dynamic_base_size_long,
            "dynamic_base_size_short": self._dynamic_base_size_short,
            "bm_balances": self._balance_manager.get_balances_summary(),
            "open_long_positions_count": len(open_longs),
            "open_short_positions_count": len(open_shorts),
            "open_long_positions": [self._helpers.format_pos_for_summary(p, self._utils) for p in open_longs],
            "open_short_positions": [self._helpers.format_pos_for_summary(p, self._utils) for p in open_shorts],
            "total_realized_pnl_session": self.get_total_pnl_realized(),
            "initial_total_capital": self._balance_manager.get_initial_total_capital(),
            "real_account_balances": self._balance_manager.get_real_balances_cache(),
            "session_limits": {
                "time_limit": self.get_session_time_limit(),
                "trade_limit": self._manual_trade_limit,
                "trades_executed": self._manual_trades_executed },
            "all_milestones": milestones_as_dicts }

    def get_unrealized_pnl(self, current_price: float) -> float:
        # Lógica completa de get_unrealized_pnl de _api.py
        total_pnl = 0.0
        for side in ['long', 'short']:
            for pos in self._position_state.get_open_logical_positions(side):
                entry = pos.get('entry_price', 0.0); size = pos.get('size_contracts', 0.0)
                if side == 'long': total_pnl += (current_price - entry) * size
                else: total_pnl += (entry - current_price) * size
        return total_pnl

    def get_manual_state(self) -> Dict[str, Any]:
        return {"mode": self._manual_mode, "limit": self._manual_trade_limit, "executed": self._manual_trades_executed}

    def get_session_start_time(self) -> Optional[datetime.datetime]: return self._session_start_time
    def get_global_tp_pct(self) -> Optional[float]: return self._global_take_profit_roi_pct
    def is_session_tp_hit(self) -> bool: return self._session_tp_hit
    def get_individual_stop_loss_pct(self) -> float: return self._individual_stop_loss_pct
    def get_trailing_stop_params(self) -> Dict[str, float]: return {"activation": self._trailing_stop_activation_pct, "distance": self._trailing_stop_distance_pct}
    def get_trend_limits(self) -> Dict[str, Any]: return {"start_time": self._trend_start_time, "duration_minutes": self._trend_limit_duration_minutes, "tp_roi_pct": self._trend_limit_tp_roi_pct, "sl_roi_pct": self._trend_limit_sl_roi_pct}
    def get_trend_state(self) -> Dict[str, Any]: return self._trend_status # Mantenido por compatibilidad
    def get_global_sl_pct(self) -> Optional[float]: return self._global_stop_loss_roi_pct
    def get_all_milestones(self) -> List[Milestone]: return copy.deepcopy(self._milestones)
    def get_session_time_limit(self) -> Dict[str, Any]: return {"duration": self._session_max_duration_minutes, "action": self._session_time_limit_action}
    def get_total_pnl_realized(self) -> float: return self._total_realized_pnl_long + self._total_realized_pnl_short

    # --- Métodos de la API para modificar el estado ---
    def set_manual_trading_mode(self, mode: str, trade_limit: Optional[int] = None, close_open: bool = False) -> Tuple[bool, str]:
        # Lógica completa de set_manual_trading_mode de _api.py
        if close_open:
            if self._manual_mode in ["LONG_ONLY", "LONG_SHORT"] and mode not in ["LONG_ONLY", "LONG_SHORT"]: self.close_all_logical_positions('long', "Cierre por cambio de modo")
            if self._manual_mode in ["SHORT_ONLY", "LONG_SHORT"] and mode not in ["SHORT_ONLY", "LONG_SHORT"]: self.close_all_logical_positions('short', "Cierre por cambio de modo")
        if mode != self._manual_mode or trade_limit != self._manual_trade_limit: self._manual_trades_executed = 0
        self._manual_mode = mode.upper()
        self._manual_trade_limit = trade_limit if trade_limit is not None and trade_limit > 0 else None
        if self._manual_mode != "NEUTRAL": self._trend_start_time = datetime.datetime.now(); self._initial_pnl_at_trend_start = self.get_total_pnl_realized()
        else: self._trend_start_time = None
        return True, f"Modo actualizado a {self._manual_mode}."

    def manual_close_logical_position_by_index(self, side: str, index: int) -> Tuple[bool, str]:
        # Lógica completa de manual_close_logical_position_by_index de _api.py
        price = self.get_current_price_for_exit()
        if not price: return False, "No se pudo obtener el precio de mercado actual."
        success = self._close_logical_position(side, index, price, datetime.datetime.now(), reason="MANUAL")
        return (True, f"Orden de cierre para {side.upper()} #{index} enviada.") if success else (False, f"Fallo al enviar orden de cierre.")

    def close_all_logical_positions(self, side: str, reason: str = "MANUAL_ALL") -> bool:
        # Lógica completa de close_all_logical_positions de _api.py
        price = self.get_current_price_for_exit()
        if not price: self._memory_logger.log(f"CIERRE TOTAL FALLIDO: Sin precio para {side.upper()}.", level="ERROR"); return False
        initial_count = len(self._position_state.get_open_logical_positions(side))
        if initial_count == 0: return True
        self._memory_logger.log(f"Iniciando cierre total de {initial_count} posiciones {side.upper()}.", level="INFO")
        for i in range(initial_count - 1, -1, -1):
            self._close_logical_position(side, i, price, datetime.datetime.now(), reason)
        remaining = len(self._position_state.get_open_logical_positions(side))
        if remaining == 0: self._memory_logger.log(f"ÉXITO: Todas las posiciones {side.upper()} cerradas.", level="INFO"); return True
        else: self._memory_logger.log(f"FALLO: Quedan {remaining} posiciones {side.upper()}.", level="ERROR"); return False

    def add_max_logical_position_slot(self) -> Tuple[bool, str]:
        self._max_logical_positions += 1
        self._balance_manager.update_operational_margins_based_on_slots(self._max_logical_positions, self._initial_base_position_size_usdt)
        return True, f"Slots incrementados a {self._max_logical_positions}."
    
    def remove_max_logical_position_slot(self) -> Tuple[bool, str]:
        if self._max_logical_positions <= 1: return False, "Mínimo 1 slot."
        open_count = max(len(self._position_state.get_open_logical_positions('long')), len(self._position_state.get_open_logical_positions('short')))
        if (self._max_logical_positions - 1) < open_count: return False, "No se puede remover, hay más posiciones abiertas que el nuevo límite."
        self._max_logical_positions -= 1
        self._balance_manager.update_operational_margins_based_on_slots(self._max_logical_positions, self._initial_base_position_size_usdt)
        return True, f"Slots decrementados a {self._max_logical_positions}."

    def set_base_position_size(self, new_size_usdt: float) -> Tuple[bool, str]:
        if not isinstance(new_size_usdt, (int, float)) or new_size_usdt <= 0: return False, "Tamaño inválido."
        old_size = self._initial_base_position_size_usdt
        self._initial_base_position_size_usdt = new_size_usdt
        self._balance_manager.recalculate_dynamic_base_sizes()
        return True, f"Tamaño base actualizado de {old_size:.2f} a {new_size_usdt:.2f} USDT."

    def set_leverage(self, new_leverage: float) -> Tuple[bool, str]:
        if not isinstance(new_leverage, (int, float)) or not (1 <= new_leverage <= 100): return False, "Apalancamiento inválido."
        self._leverage = new_leverage
        symbol = getattr(self._config, 'TICKER_SYMBOL', 'N/A')
        success = self._live_operations.set_leverage(symbol, str(new_leverage), str(new_leverage))
        return (True, f"Apalancamiento actualizado a {new_leverage}x.") if success else (False, f"Error al aplicar apalancamiento en el exchange.")
    
    def set_individual_stop_loss_pct(self, value: float) -> Tuple[bool, str]:
        if not isinstance(value, (int, float)) or value < 0: return False, "Valor inválido."
        self._individual_stop_loss_pct = value
        return True, f"Stop Loss individual para nuevas posiciones ajustado a {value:.2f}%."

    def set_trailing_stop_params(self, activation_pct: float, distance_pct: float) -> Tuple[bool, str]:
        if not all(isinstance(v, (int, float)) and v >= 0 for v in [activation_pct, distance_pct]): return False, "Valores inválidos."
        self._trailing_stop_activation_pct = activation_pct
        self._trailing_stop_distance_pct = distance_pct
        return True, f"Trailing Stop ajustado (Activación: {activation_pct:.2f}%, Distancia: {distance_pct:.2f}%)."

    def set_global_stop_loss_pct(self, value: float) -> Tuple[bool, str]:
        self._global_stop_loss_roi_pct = value
        return True, f"Stop Loss Global actualizado a -{value}%." if value > 0 else "Stop Loss Global desactivado."

    def set_global_take_profit_pct(self, value: float) -> Tuple[bool, str]:
        self._global_take_profit_roi_pct = value; self._session_tp_hit = False
        return True, f"Take Profit Global actualizado a +{value}%." if value > 0 else "Take Profit Global desactivado."

    def set_session_time_limit(self, duration: int, action: str) -> Tuple[bool, str]:
        self._session_max_duration_minutes = duration; self._session_time_limit_action = action
        return True, f"Límite de tiempo a {duration} min, acción: {action.upper()}." if duration > 0 else "Límite de tiempo desactivado."

    def set_manual_trade_limit(self, limit: Optional[int]) -> Tuple[bool, str]:
        new_limit = limit if limit is not None and limit > 0 else None
        self.set_manual_trading_mode(self._manual_mode, new_limit)
        limit_str = f"{new_limit} trades" if new_limit else "ilimitados"
        return True, f"Límite de sesión establecido a {limit_str}."

    def set_trend_limits(self, duration: Optional[int], tp_roi_pct: Optional[float], sl_roi_pct: Optional[float], trade_limit: Optional[int] = None) -> Tuple[bool, str]:
        if trade_limit is not None: self.set_manual_trade_limit(trade_limit)
        self._trend_limit_duration_minutes = duration if duration is not None and duration > 0 else None
        self._trend_limit_tp_roi_pct = abs(tp_roi_pct) if tp_roi_pct is not None and tp_roi_pct > 0 else None
        self._trend_limit_sl_roi_pct = -abs(sl_roi_pct) if sl_roi_pct is not None and sl_roi_pct < 0 else None
        msg_parts = [p for p in [f"Duración: {duration} min" if duration else None, f"Trades: {trade_limit or 'Ilimitados'}" if trade_limit is not None else None, f"TP ROI: +{tp_roi_pct:.2f}%" if self._trend_limit_tp_roi_pct else None, f"SL ROI: {self._trend_limit_sl_roi_pct:.2f}%" if self._trend_limit_sl_roi_pct else None] if p]
        return (True, f"Límites para próxima tendencia: {', '.join(msg_parts)}.") if msg_parts else (True, "Límites de tendencia desactivados.")

    def add_milestone(self, condition_data: Dict, action_data: Dict, parent_id: Optional[str] = None) -> Tuple[bool, str]:
        # Lógica completa de add_milestone de _api.py
        try:
            condition = MilestoneCondition(**condition_data)
            action = MilestoneAction(**action_data)
            level, status = 1, 'ACTIVE'
            if parent_id:
                parent = next((m for m in self._milestones if m.id == parent_id), None)
                if not parent: return False, f"Hito padre con ID '{parent_id}' no encontrado."
                level = parent.level + 1; status = 'PENDING'
            milestone_id = f"mstone_{int(time.time() * 1000)}"
            new_milestone = Milestone(id=milestone_id, condition=condition, action=action, parent_id=parent_id, level=level, status=status)
            self._milestones.append(new_milestone)
            return True, f"Hito '{milestone_id}' añadido en Nivel {level} (Estado: {status})."
        except Exception as e: return False, f"Error creando hito: {e}"

    def remove_milestone(self, milestone_id: str) -> Tuple[bool, str]:
        initial_len = len(self._milestones)
        self._milestones = [m for m in self._milestones if m.id != milestone_id]
        return (True, f"Hito '{milestone_id}' eliminado.") if len(self._milestones) < initial_len else (False, f"No se encontró el hito.")

    def process_triggered_milestone(self, milestone_id: str):
        parent_id_of_completed = next((m.parent_id for m in self._milestones if m.id == milestone_id), "NOT_FOUND")
        if parent_id_of_completed == "NOT_FOUND": return
        for m in self._milestones:
            if m.id == milestone_id: m.status = 'COMPLETED'
            elif m.parent_id == parent_id_of_completed and m.status in ['PENDING', 'ACTIVE']: m.status = 'CANCELLED'
            elif m.parent_id == milestone_id and m.status == 'PENDING': m.status = 'ACTIVE'

    def start_manual_trend(self, mode: str, trade_limit: Optional[int], duration_limit: Optional[int], tp_roi_limit: Optional[float], sl_roi_limit: Optional[float]) -> Tuple[bool, str]:
        self.set_trend_limits(duration_limit, tp_roi_limit, sl_roi_limit)
        return self.set_manual_trading_mode(mode, trade_limit=trade_limit, close_open=False)

    def end_current_trend_and_ask(self): self._manual_mode = "NEUTRAL"

    def get_current_price_for_exit(self) -> Optional[float]:
        try: return self._connection_ticker.get_latest_price().get('price')
        except (AttributeError, TypeError): return None

    def get_rrr_potential(self) -> Optional[float]:
        if self._individual_stop_loss_pct > 0 and self._trailing_stop_activation_pct > 0:
            return self._utils.safe_division(self._trailing_stop_activation_pct, self._individual_stop_loss_pct)
        return None

    # ==============================================================================
    # --- MÉTODOS PRIVADOS (Lógica Interna Migrada) ---
    # ==============================================================================
    
    def _reset_all_states(self):
        # Lógica completa de reset_all_states de _state.py
        self._initialized = False; self._operation_mode = "unknown"; self._leverage = 1.0
        self._max_logical_positions = 1; self._initial_base_position_size_usdt = 0.0
        self._total_realized_pnl_long = 0.0; self._total_realized_pnl_short = 0.0
        self._manual_mode = "NEUTRAL"; self._manual_trade_limit = None; self._manual_trades_executed = 0
        self._global_stop_loss_roi_pct = None; self._global_take_profit_roi_pct = None
        self._session_tp_hit = False; self._session_start_time = None
        self._session_max_duration_minutes = 0; self._session_time_limit_action = "NEUTRAL"
        self._individual_stop_loss_pct = 0.0; self._trailing_stop_activation_pct = 0.0; self._trailing_stop_distance_pct = 0.0
        self._milestones = []; self._trend_start_time = None; self._trend_limit_duration_minutes = None
        self._trend_limit_tp_roi_pct = None; self._trend_limit_sl_roi_pct = None

    def _can_open_new_position(self, side: str) -> bool:
        # Lógica completa de can_open_new_position de _rules.py
        if self._session_tp_hit: return False
        if self._manual_mode == 'NEUTRAL' or \
           (side == 'long' and self._manual_mode == 'SHORT_ONLY') or \
           (side == 'short' and self._manual_mode == 'LONG_ONLY'):
            return False
        if self._manual_trade_limit is not None and self._manual_trades_executed >= self._manual_trade_limit:
            if not self._session_tp_hit: self._memory_logger.log(f"Límite de trades ({self._manual_trade_limit}) alcanzado.", "INFO"); self._session_tp_hit = True
            return False
        if len(self._position_state.get_open_logical_positions(side)) >= self._max_logical_positions: return False
        margin_needed = self._dynamic_base_size_long if side == 'long' else self._dynamic_base_size_short
        if self._balance_manager.get_available_margin(side) < margin_needed - 1e-6: return False
        return True

    def _open_logical_position(self, side: str, entry_price: float, timestamp: datetime.datetime):
        # Lógica completa de open_logical_position de _actions.py
        open_positions = self._position_state.get_open_logical_positions(side)
        if open_positions:
            last_entry = self._utils.safe_float_convert(open_positions[-1].get('entry_price'), 0.0)
            if last_entry > 1e-9:
                diff_pct = self._utils.safe_division(entry_price - last_entry, last_entry) * 100.0
                long_thresh = getattr(self._config, 'POSITION_MIN_PRICE_DIFF_LONG_PCT', -1.0)
                short_thresh = getattr(self._config, 'POSITION_MIN_PRICE_DIFF_SHORT_PCT', 1.0)
                if (side == 'long' and diff_pct > long_thresh) or (side == 'short' and diff_pct < short_thresh): return
        margin_to_use = self._dynamic_base_size_long if side == 'long' else self._dynamic_base_size_short
        result = self._executor.execute_open(side, entry_price, timestamp, margin_to_use)
        if result and result.get('success'): self._manual_trades_executed += 1

    def _close_logical_position(self, side: str, index: int, exit_price: float, timestamp: datetime.datetime, reason: str) -> bool:
        # Lógica completa de close_logical_position de _actions.py
        result = self._executor.execute_close(side, index, exit_price, timestamp, reason)
        if result and result.get('success', False):
            pnl = result.get('pnl_net_usdt', 0.0)
            if side == 'long': self._total_realized_pnl_long += pnl
            else: self._total_realized_pnl_short += pnl
            transfer_amount = result.get('amount_transferable_to_profit', 0.0)
            if transfer_amount >= getattr(self._config, 'POSITION_MIN_TRANSFER_AMOUNT_USDT', 0.1):
                transferred = _transfer_executor.execute_transfer(amount=transfer_amount, from_account_side=side, is_live_mode=True, config=self._config, live_manager=self._connection_manager, live_operations=self._live_operations, balance_manager=self._balance_manager)
                if transferred > 0: self._balance_manager.record_real_profit_transfer(transferred)
        return result.get('success', False)
        
    def _update_trailing_stop(self, side, position_data, current_price):
        # Lógica completa de check_and_close_positions (parte de TS)
        is_ts_active = position_data.get('ts_is_active', False)
        entry_price = position_data.get('entry_price')
        if not is_ts_active and self._trailing_stop_activation_pct > 0 and entry_price:
            activation_price = entry_price * (1 + self._trailing_stop_activation_pct / 100) if side == 'long' else entry_price * (1 - self._trailing_stop_activation_pct / 100)
            if (side == 'long' and current_price >= activation_price) or (side == 'short' and current_price <= activation_price):
                position_data['ts_is_active'] = True; position_data['ts_peak_price'] = current_price
        if position_data.get('ts_is_active'):
            peak_price = position_data.get('ts_peak_price', current_price)
            if (side == 'long' and current_price > peak_price) or (side == 'short' and current_price < peak_price):
                position_data['ts_peak_price'] = current_price
            new_stop_price = position_data['ts_peak_price'] * (1 - self._trailing_stop_distance_pct / 100) if side == 'long' else position_data['ts_peak_price'] * (1 + self._trailing_stop_distance_pct / 100)
            position_data['ts_stop_price'] = new_stop_price
            self._position_state.update_logical_position_details(side, position_data['id'], position_data)

    def set_dynamic_base_size(self, long_size: float, short_size: float):
        """Método llamado por BalanceManager para actualizar el estado del tamaño dinámico."""
        self._dynamic_base_size_long = long_size
        self._dynamic_base_size_short = short_size
        
    def get_max_logical_positions(self) -> int: return self._max_logical_positions
    def get_initial_base_position_size(self) -> float: return self._initial_base_position_size_usdt