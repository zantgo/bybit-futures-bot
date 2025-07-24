"""
Módulo del Position Manager: API de Getters.

Agrupa todos los métodos públicos que la TUI y otros módulos utilizan
para leer el estado del PositionManager sin modificarlo.
"""
import datetime
import copy
from typing import Optional, Dict, Any, List

# --- Dependencias de Tipado ---
try:
    from .._entities import Milestone
except ImportError:
    class Milestone: pass

class _ApiGetters:
    """Clase base que contiene los getters públicos de la API del PositionManager."""
    
    def is_initialized(self) -> bool: 
        """Verifica si el Position Manager ha sido inicializado."""
        return self._initialized

    def get_position_summary(self) -> dict:
        """
        Obtiene un resumen completo y FRESCO del estado del PM.
        Esta función es la fuente única de datos para el dashboard.
        """
        if not self._initialized: return {"error": "PM no instanciado"}
        
        ticker_data = self._exchange.get_ticker(getattr(self._config, 'TICKER_SYMBOL', 'N/A'))
        current_market_price = ticker_data.price if ticker_data else (self.get_current_market_price() or 0.0)

        open_longs = self._position_state.get_open_logical_positions('long')
        open_shorts = self._position_state.get_open_logical_positions('short')
        
        from dataclasses import asdict
        milestones_as_dicts = [asdict(m) for m in self._milestones]

        summary_data = {
            "initialized": True,
            "operation_mode": self._operation_mode,
            "trend_status": self.get_trend_state(),
            "leverage": self._leverage,
            "max_logical_positions": self._max_logical_positions,
            "initial_base_position_size_usdt": self._initial_base_position_size_usdt,
            "bm_balances": self._balance_manager.get_balances_summary(),
            "open_long_positions_count": len(open_longs),
            "open_short_positions_count": len(open_shorts),
            "open_long_positions": [self._helpers.format_pos_for_summary(p) for p in open_longs],
            "open_short_positions": [self._helpers.format_pos_for_summary(p) for p in open_shorts],
            "total_realized_pnl_session": self.get_total_pnl_realized(),
            "initial_total_capital": self._balance_manager.get_initial_total_capital(),
            "real_account_balances": self._balance_manager.get_real_balances_cache(),
            "session_limits": { "time_limit": self.get_session_time_limit() },
            "all_milestones": milestones_as_dicts,
            "current_market_price": current_market_price,
        }
        return summary_data

    def get_unrealized_pnl(self, current_price: float) -> float:
        """Calcula el PNL no realizado total de todas las posiciones abiertas."""
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

    def get_session_start_time(self) -> Optional[datetime.datetime]: 
        """Obtiene la hora de inicio de la sesión."""
        return self._session_start_time
        
    def get_global_tp_pct(self) -> Optional[float]: 
        """Obtiene el umbral de Take Profit Global por ROI de la sesión."""
        return self._global_take_profit_roi_pct
        
    def is_session_tp_hit(self) -> bool: 
        """Verifica si se ha alcanzado el TP global de la sesión."""
        return self._session_tp_hit
        
    def get_global_sl_pct(self) -> Optional[float]: 
        """Obtiene el umbral de Stop Loss Global por ROI de la sesión."""
        return self._global_stop_loss_roi_pct
        
    def get_all_milestones(self) -> List[Milestone]: 
        """Obtiene todos los hitos (triggers) como objetos Milestone."""
        return copy.deepcopy(self._milestones)
        
    def get_session_time_limit(self) -> Dict[str, Any]:
        """Obtiene la configuración del límite de tiempo de la sesión."""
        return {"duration": getattr(self._config, 'SESSION_MAX_DURATION_MINUTES', 0),
                "action": getattr(self._config, 'SESSION_TIME_LIMIT_ACTION', "NEUTRAL")}
                
    def get_total_pnl_realized(self) -> float: 
        """Obtiene el PNL realizado total de la sesión."""
        return self._total_realized_pnl_long + self._total_realized_pnl_short

    def get_current_market_price(self) -> Optional[float]:
        """Obtiene el precio de mercado más reciente conocido por el ticker."""
        try:
            return self._exchange.get_latest_price()
        except (AttributeError, TypeError):
            return None

    def get_max_logical_positions(self) -> int: 
        """Obtiene el número máximo de posiciones lógicas permitidas por lado."""
        return self._max_logical_positions
        
    def get_initial_base_position_size(self) -> float: 
        """Obtiene el tamaño base inicial de las posiciones configurado para la sesión."""
        return self._initial_base_position_size_usdt
        
    def get_leverage(self) -> float: 
        """Obtiene el apalancamiento actual de la sesión."""
        return self._leverage