"""
Módulo del Position Manager Principal.

v4.0 (Refactor de Hitos):
- Se refactoriza para operar bajo un modelo jerárquico Sesión > Hito > Tendencia.
- Se elimina el estado de `_manual_mode` y se reemplaza por el estado `_active_trend`.
- La lógica de apertura de posiciones y gestión de riesgo ahora depende de la
  configuración de la tendencia activa.
- Se adapta la gestión de hitos para trabajar con la nueva entidad `TrendConfig`.
"""
import datetime
import time
import copy
from typing import Optional, Dict, Any, Tuple, List

# --- Dependencias del Proyecto (inyectadas) ---
try:
    from ._entities import Milestone, MilestoneCondition, MilestoneAction, TrendConfig
    from . import _transfer_executor
    from core.exchange import AbstractExchange
except ImportError:
    class Milestone: pass
    class MilestoneCondition: pass
    class MilestoneAction: pass
    class TrendConfig: pass
    class AbstractExchange: pass
    _transfer_executor = None

class PositionManager:
    """
    Orquesta la gestión de posiciones, capital y riesgo bajo un modelo
    de control jerárquico basado en Hitos y Tendencias.
    """
    def __init__(self,
                 balance_manager: Any,
                 position_state: Any,
                 exchange_adapter: AbstractExchange,
                 config: Any,
                 utils: Any,
                 memory_logger: Any,
                 helpers: Any
                 ):
        # --- Inyección de Dependencias ---
        self._balance_manager = balance_manager
        self._position_state = position_state
        self._executor: Optional[Any] = None
        self._exchange = exchange_adapter
        self._config = config
        self._utils = utils
        self._memory_logger = memory_logger
        self._helpers = helpers

        # --- Estado de la Sesión (Global) ---
        self._initialized: bool = False
        self._operation_mode: str = "unknown"
        self._leverage: float = 1.0
        self._max_logical_positions: int = 1
        self._initial_base_position_size_usdt: float = 0.0
        self._dynamic_base_size_long: float = 0.0
        self._dynamic_base_size_short: float = 0.0
        self._session_start_time: Optional[datetime.datetime] = None
        self._session_tp_hit: bool = False
        self._global_stop_loss_roi_pct: Optional[float] = None
        self._global_take_profit_roi_pct: Optional[float] = None
        
        # --- Estado de PNL ---
        self._total_realized_pnl_long: float = 0.0
        self._total_realized_pnl_short: float = 0.0

        # --- Estado del Árbol de Decisiones ---
        self._milestones: List[Milestone] = []
        
        # --- INICIO DE CAMBIOS: Nuevo Modelo de Estado ---
        # El estado actual del bot se define por la tendencia activa.
        # Si _active_trend es None, el bot está en modo NEUTRAL.
        self._active_trend: Optional[Dict[str, Any]] = None
        # --- FIN DE CAMBIOS ---
        

    def set_executor(self, executor: Any):
        """Inyecta el executor después de la inicialización para romper la dependencia circular."""
        self._executor = executor

    # ==============================================================================
    # --- MÉTODOS DE CICLO DE VIDA ---
    # ==============================================================================

    def initialize(self, operation_mode: str, base_size: float, max_pos: int):
        """Inicializa el PM para una nueva sesión."""
        self._reset_all_states()
        self._operation_mode = operation_mode
        self._leverage = getattr(self._config, 'POSITION_LEVERAGE', 1.0)
        self._max_logical_positions = max_pos
        self._initial_base_position_size_usdt = base_size
        self._session_start_time = datetime.datetime.now()
        
        # Límites globales de la sesión (disyuntores)
        self._global_stop_loss_roi_pct = getattr(self._config, 'SESSION_STOP_LOSS_ROI_PCT', 0.0)
        self._global_take_profit_roi_pct = getattr(self._config, 'SESSION_TAKE_PROFIT_ROI_PCT', 0.0)

        self._balance_manager.set_state_manager(self)
        self._position_state.initialize(is_live_mode=True)
        
        self._initialized = True
        self._memory_logger.log("PositionManager inicializado bajo el nuevo modelo de Hitos/Tendencias.", level="INFO")

    def handle_low_level_signal(self, signal: str, entry_price: float, timestamp: datetime.datetime):
        """Punto de entrada para señales desde el `event_processor`."""
        if not self._initialized or not self._executor or not self._active_trend:
            return

        trend_mode = self._active_trend['config'].mode
        side_to_open = 'long' if signal == "BUY" else 'short'
        
        side_allowed = (side_to_open == 'long' and trend_mode in ["LONG_ONLY", "LONG_SHORT"]) or \
                       (side_to_open == 'short' and trend_mode in ["SHORT_ONLY", "LONG_SHORT"])
        
        if side_allowed and self._can_open_new_position(side_to_open):
            self._open_logical_position(side_to_open, entry_price, timestamp)

    def check_and_close_positions(self, current_price: float, timestamp: datetime.datetime):
        """Revisa SL y TS para todas las posiciones abiertas en cada tick."""
        if not self._initialized or not self._executor:
            return

        for side in ['long', 'short']:
            open_positions = self._position_state.get_open_logical_positions(side)
            if not open_positions:
                continue

            indices_to_close = []
            reasons = {}
            for i, pos in enumerate(open_positions):
                sl_price = pos.get('stop_loss_price')
                if sl_price and ((side == 'long' and current_price <= sl_price) or (side == 'short' and current_price >= sl_price)):
                    indices_to_close.append(i)
                    reasons[i] = "SL"
                    continue

                self._update_trailing_stop(side, pos, current_price)
                ts_stop_price = pos.get('ts_stop_price')
                if ts_stop_price and ((side == 'long' and current_price <= ts_stop_price) or (side == 'short' and current_price >= ts_stop_price)):
                    indices_to_close.append(i)
                    reasons[i] = "TS"

            for index in sorted(list(set(indices_to_close)), reverse=True):
                self._close_logical_position(side, index, current_price, timestamp, reason=reasons.get(index, "UNKNOWN"))

    # ==============================================================================
    # --- MÉTODOS DE LA API PÚBLICA (GETTERS) ---
    # ==============================================================================

    def is_initialized(self) -> bool: return self._initialized

    def get_position_summary(self) -> dict:
        if not self._initialized: return {"error": "PM no inicializado"}
        open_longs = self._position_state.get_open_logical_positions('long')
        open_shorts = self._position_state.get_open_logical_positions('short')
        
        # Usamos asdict para serializar los dataclasses para la TUI
        from dataclasses import asdict
        milestones_as_dicts = [asdict(m) for m in self._milestones]
        
        self._balance_manager.update_real_balances_cache()

        return {
            "initialized": True,
            "operation_mode": self._operation_mode,
            "trend_status": self.get_trend_state(), # <-- CAMBIO: Fuente de verdad del estado
            "leverage": self._leverage,
            "max_logical_positions": self._max_logical_positions,
            "initial_base_position_size_usdt": self._initial_base_position_size_usdt,
            "dynamic_base_size_long": self._dynamic_base_size_long,
            "dynamic_base_size_short": self._dynamic_base_size_short,
            "bm_balances": self._balance_manager.get_balances_summary(),
            "open_long_positions_count": len(open_longs),
            "open_short_positions_count": len(open_shorts),
            "open_long_positions": [self._helpers.format_pos_for_summary(p) for p in open_longs],
            "open_short_positions": [self._helpers.format_pos_for_summary(p) for p in open_shorts],
            "total_realized_pnl_session": self.get_total_pnl_realized(),
            "initial_total_capital": self._balance_manager.get_initial_total_capital(),
            "real_account_balances": self._balance_manager.get_real_balances_cache(),
            "session_limits": { "time_limit": self.get_session_time_limit() },
            "all_milestones": milestones_as_dicts
        }

    def get_unrealized_pnl(self, current_price: float) -> float:
        total_pnl = 0.0
        for side in ['long', 'short']:
            for pos in self._position_state.get_open_logical_positions(side):
                entry = pos.get('entry_price', 0.0)
                size = pos.get('size_contracts', 0.0)
                if side == 'long': total_pnl += (current_price - entry) * size
                else: total_pnl += (entry - current_price) * size
        return total_pnl

    def get_trend_state(self) -> Dict[str, Any]:
        """Devuelve el estado de la tendencia activa."""
        if not self._active_trend:
            return {'mode': 'NEUTRAL'}
        
        from dataclasses import asdict
        return {
            'mode': self._active_trend['config'].mode,
            'milestone_id': self._active_trend['milestone_id'],
            'start_time': self._active_trend['start_time'],
            'trades_executed': self._active_trend['trades_executed'],
            'initial_pnl': self._active_trend['initial_pnl'],
            'config': asdict(self._active_trend['config'])
        }

    def get_trend_limits(self) -> Dict[str, Any]:
        """Devuelve los límites de la tendencia activa."""
        if not self._active_trend:
            return {}
        
        config = self._active_trend['config']
        return {
            "start_time": self._active_trend['start_time'],
            "duration_minutes": config.limit_duration_minutes,
            "tp_roi_pct": config.limit_tp_roi_pct,
            "sl_roi_pct": config.limit_sl_roi_pct,
            "trade_limit": config.limit_trade_count
        }

    def get_session_start_time(self) -> Optional[datetime.datetime]: return self._session_start_time
    def get_global_tp_pct(self) -> Optional[float]: return self._global_take_profit_roi_pct
    def is_session_tp_hit(self) -> bool: return self._session_tp_hit
    def get_global_sl_pct(self) -> Optional[float]: return self._global_stop_loss_roi_pct
    def get_all_milestones(self) -> List[Milestone]: return copy.deepcopy(self._milestones)
    def get_session_time_limit(self) -> Dict[str, Any]:
        return {"duration": getattr(self._config, 'SESSION_MAX_DURATION_MINUTES', 0),
                "action": getattr(self._config, 'SESSION_TIME_LIMIT_ACTION', "NEUTRAL")}
    def get_total_pnl_realized(self) -> float: return self._total_realized_pnl_long + self._total_realized_pnl_short

    # ==============================================================================
    # --- MÉTODOS DE LA API PÚBLICA (SETTERS Y ACCIONES) ---
    # ==============================================================================

    def add_milestone(self, condition_data: Dict, action_data: Dict, parent_id: Optional[str] = None) -> Tuple[bool, str]:
        try:
            condition = MilestoneCondition(**condition_data)
            trend_config = TrendConfig(**action_data['params'])
            action = MilestoneAction(type=action_data['type'], params=trend_config)
            
            level, status = 1, 'ACTIVE'
            if parent_id:
                parent = next((m for m in self._milestones if m.id == parent_id), None)
                if not parent: return False, f"Hito padre con ID '{parent_id}' no encontrado."
                level = parent.level + 1
                status = 'PENDING'
            
            milestone_id = f"mstone_{int(time.time() * 1000)}"
            new_milestone = Milestone(id=milestone_id, condition=condition, action=action, parent_id=parent_id, level=level, status=status)
            self._milestones.append(new_milestone)
            self._memory_logger.log(f"HITO CREADO: ID ...{milestone_id[-6:]}, Nivel {level}, Estado {status}", "INFO")
            return True, f"Hito '{milestone_id[-6:]}' añadido en Nivel {level}."
        except Exception as e:
            return False, f"Error creando hito: {e}"

    def remove_milestone(self, milestone_id: str) -> Tuple[bool, str]:
        # Implementa borrado en cascada
        ids_to_remove = {milestone_id}
        ids_to_check = [milestone_id]
        while ids_to_check:
            parent_id = ids_to_check.pop(0)
            children = [m.id for m in self._milestones if m.parent_id == parent_id]
            ids_to_remove.update(children)
            ids_to_check.extend(children)
        
        initial_len = len(self._milestones)
        self._milestones = [m for m in self._milestones if m.id not in ids_to_remove]
        
        if len(self._milestones) < initial_len:
             self._memory_logger.log(f"HITOS ELIMINADOS: {len(ids_to_remove)} hito(s) en cascada desde ...{milestone_id[-6:]}", "WARN")
             return True, f"{len(ids_to_remove)} hito(s) eliminados."
        else:
             return False, "No se encontró el hito."

    def process_triggered_milestone(self, milestone_id: str):
        triggered_milestone = next((m for m in self._milestones if m.id == milestone_id), None)
        if not triggered_milestone: return
        
        # 1. Finalizar la tendencia actual (si la hay)
        self._end_trend("Hito completado")
        
        # 2. Actualizar estados del árbol
        parent_id = triggered_milestone.parent_id
        for m in self._milestones:
            if m.id == milestone_id:
                m.status = 'COMPLETED'
            elif m.parent_id == parent_id and m.status in ['PENDING', 'ACTIVE']:
                m.status = 'CANCELLED' # Cancela hermanos
            elif m.parent_id == milestone_id and m.status == 'PENDING':
                m.status = 'ACTIVE' # Activa hijos directos

        # 3. Iniciar la nueva tendencia definida por el hito
        self._start_trend(triggered_milestone)

    def end_current_trend_and_ask(self):
        """Llamado por los limit checkers para finalizar una tendencia."""
        self._end_trend(reason="Límite de tendencia alcanzado")

    def manual_close_logical_position_by_index(self, side: str, index: int) -> Tuple[bool, str]:
        price = self.get_current_price_for_exit()
        if not price: return False, "No se pudo obtener el precio de mercado actual."
        success = self._close_logical_position(side, index, price, datetime.datetime.now(), reason="MANUAL")
        return (True, f"Orden de cierre para {side.upper()} #{index} enviada.") if success else (False, f"Fallo al enviar orden de cierre.")

    def close_all_logical_positions(self, side: str, reason: str = "MANUAL_ALL") -> bool:
        price = self.get_current_price_for_exit()
        if not price: self._memory_logger.log(f"CIERRE TOTAL FALLIDO: Sin precio para {side.upper()}.", level="ERROR"); return False
        
        count = len(self._position_state.get_open_logical_positions(side))
        if count == 0: return True
        
        for i in range(count - 1, -1, -1):
            self._close_logical_position(side, i, price, datetime.datetime.now(), reason)
        return True

    def get_current_price_for_exit(self) -> Optional[float]:
        try:
            return self._exchange.get_latest_price()
        except (AttributeError, TypeError):
            return None
    
    # ==============================================================================
    # --- MÉTODOS PRIVADOS DE GESTIÓN DE ESTADO ---
    # ==============================================================================
    
    def _reset_all_states(self):
        self._initialized = False
        self._operation_mode = "unknown"
        self._leverage = 1.0
        self._max_logical_positions = 1
        self._initial_base_position_size_usdt = 0.0
        self._total_realized_pnl_long = 0.0
        self._total_realized_pnl_short = 0.0
        self._session_tp_hit = False
        self._session_start_time = None
        self._global_stop_loss_roi_pct = None
        self._global_take_profit_roi_pct = None
        self._milestones = []
        self._active_trend = None

    def _start_trend(self, milestone: Milestone):
        """Activa una nueva tendencia basada en la configuración de un hito."""
        if self._active_trend:
            self._memory_logger.log(f"ADVERTENCIA: Se intentó iniciar una nueva tendencia mientras otra estaba activa.", "WARN")
            self._end_trend("Iniciando nueva tendencia")
        
        self._active_trend = {
            "milestone_id": milestone.id,
            "config": milestone.action.params,
            "start_time": datetime.datetime.now(),
            "trades_executed": 0,
            "initial_pnl": self.get_total_pnl_realized()
        }
        mode = self._active_trend['config'].mode
        self._memory_logger.log(f"TENDENCIA INICIADA: Modo '{mode}' activado por hito ...{milestone.id[-6:]}", "INFO")

    def _end_trend(self, reason: str):
        """Finaliza la tendencia activa y vuelve al estado NEUTRAL."""
        if self._active_trend:
            mode = self._active_trend['config'].mode
            self._memory_logger.log(f"TENDENCIA FINALIZADA: Modo '{mode}' terminado. Razón: {reason}", "INFO")
            self._active_trend = None

    def _can_open_new_position(self, side: str) -> bool:
        if self._session_tp_hit or not self._active_trend:
            return False
            
        trend_config = self._active_trend['config']
        
        if trend_config.limit_trade_count is not None and self._active_trend['trades_executed'] >= trend_config.limit_trade_count:
            return False
        
        if len(self._position_state.get_open_logical_positions(side)) >= self._max_logical_positions:
            return False
            
        margin_needed = self._dynamic_base_size_long if side == 'long' else self._dynamic_base_size_short
        if self._balance_manager.get_available_margin(side) < margin_needed - 1e-6:
            return False
            
        return True

    def _open_logical_position(self, side: str, entry_price: float, timestamp: datetime.datetime):
        if not self._active_trend: return

        # Aplicar SL y TS de la tendencia activa
        trend_config = self._active_trend['config']
        
        margin_to_use = self._dynamic_base_size_long if side == 'long' else self._dynamic_base_size_short
        result = self._executor.execute_open(
            side=side, 
            entry_price=entry_price, 
            timestamp=timestamp, 
            margin_to_use=margin_to_use,
            # Pasamos los parámetros de riesgo de la tendencia al ejecutor
            # (Esto requerirá un pequeño cambio en _executor.py)
            sl_pct=trend_config.individual_sl_pct
        )
        if result and result.get('success'):
            self._active_trend['trades_executed'] += 1

    def _update_trailing_stop(self, side, position_data, current_price):
        if not self._active_trend: return

        trend_config = self._active_trend['config']
        activation_pct = trend_config.trailing_stop_activation_pct
        distance_pct = trend_config.trailing_stop_distance_pct
        
        is_ts_active = position_data.get('ts_is_active', False)
        entry_price = position_data.get('entry_price')
        
        if not is_ts_active and activation_pct > 0 and entry_price:
            activation_price = entry_price * (1 + activation_pct / 100) if side == 'long' else entry_price * (1 - activation_pct / 100)
            if (side == 'long' and current_price >= activation_price) or (side == 'short' and current_price <= activation_price):
                position_data['ts_is_active'] = True
                position_data['ts_peak_price'] = current_price

        if position_data.get('ts_is_active'):
            peak_price = position_data.get('ts_peak_price', current_price)
            if (side == 'long' and current_price > peak_price) or (side == 'short' and current_price < peak_price):
                position_data['ts_peak_price'] = current_price
            
            new_stop_price = position_data['ts_peak_price'] * (1 - distance_pct / 100) if side == 'long' else position_data['ts_peak_price'] * (1 + distance_pct / 100)
            position_data['ts_stop_price'] = new_stop_price
            self._position_state.update_logical_position_details(side, position_data['id'], position_data)
            
    # --- MÉTODOS INTERNOS (sin cambios significativos) ---
    def _close_logical_position(self, side: str, index: int, exit_price: float, timestamp: datetime.datetime, reason: str) -> bool:
        if not self._executor: return False
        result = self._executor.execute_close(side, index, exit_price, timestamp, reason)
        if result and result.get('success', False):
            pnl = result.get('pnl_net_usdt', 0.0)
            if side == 'long': self._total_realized_pnl_long += pnl
            else: self._total_realized_pnl_short += pnl
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
    
    def set_dynamic_base_size(self, long_size: float, short_size: float):
        self._dynamic_base_size_long = long_size
        self._dynamic_base_size_short = short_size
        
    def get_max_logical_positions(self) -> int: return self._max_logical_positions
    def get_initial_base_position_size(self) -> float: return self._initial_base_position_size_usdt
    def get_leverage(self) -> float: return self._leverage