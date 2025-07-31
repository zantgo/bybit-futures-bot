"""
Módulo del Position Manager: API de Getters.

v7.3 (Corrección Final de Getters):
- Se corrige la función `get_unrealized_pnl` para que obtenga las operaciones
  LONG y SHORT de forma independiente usando `get_operation_by_side`.
- Esta corrección elimina la última llamada a la función obsoleta `get_operation`
  dentro del PM, solucionando el `AttributeError` persistente.
"""
import datetime
import copy
from typing import Optional, Dict, Any, List
from dataclasses import asdict

# --- Dependencias de Tipado ---
try:
    from .._entities import Operacion
except ImportError:
    class Operacion: pass

class _ApiGetters:
    """Clase base que contiene los getters públicos de la API del PositionManager."""
    
    def is_initialized(self) -> bool: 
        """Verifica si el Position Manager ha sido inicializado."""
        return self._initialized

    def get_position_summary(self) -> dict:
        """
        Obtiene un resumen completo y FRESCO del estado del PM, adaptado para la
        arquitectura de operaciones duales (LONG y SHORT).
        """
        if not self._initialized:
            return {"error": "PM no instanciado"}
        
        long_op = self._om_api.get_operation_by_side('long')
        short_op = self._om_api.get_operation_by_side('short')

        if not long_op or not short_op:
            return {"error": "Operaciones Long/Short no disponibles en el OM"}

        ticker_data = self._exchange.get_ticker(getattr(self._config, 'TICKER_SYMBOL', 'N/A'))
        current_market_price = ticker_data.price if ticker_data else (self.get_current_market_price() or 0.0)

        open_longs = long_op.posiciones_activas.get('long', [])
        open_shorts = short_op.posiciones_activas.get('short', [])
        
        unrealized_pnl_long = sum((current_market_price - pos.entry_price) * pos.size_contracts for pos in open_longs)
        unrealized_pnl_short = sum((pos.entry_price - current_market_price) * pos.size_contracts for pos in open_shorts)
        total_unrealized_pnl = unrealized_pnl_long + unrealized_pnl_short
        
        total_realized_pnl_ops = long_op.pnl_realizado_usdt + short_op.pnl_realizado_usdt
        total_pnl_ops = total_realized_pnl_ops + total_unrealized_pnl
        
        initial_capital_ops = long_op.capital_inicial_usdt + short_op.capital_inicial_usdt
        operation_roi = self._utils.safe_division(total_pnl_ops, initial_capital_ops) * 100 if initial_capital_ops > 0 else 0.0

        operation_long_pnl = long_op.pnl_realizado_usdt + unrealized_pnl_long
        operation_short_pnl = short_op.pnl_realizado_usdt + unrealized_pnl_short
        operation_long_roi = self._utils.safe_division(operation_long_pnl, long_op.capital_inicial_usdt) * 100 if long_op.capital_inicial_usdt > 0 else 0.0
        operation_short_roi = self._utils.safe_division(operation_short_pnl, short_op.capital_inicial_usdt) * 100 if short_op.capital_inicial_usdt > 0 else 0.0

        active_tendencies = []
        if long_op.estado == 'ACTIVA': active_tendencies.append(long_op.tendencia)
        if short_op.estado == 'ACTIVA': active_tendencies.append(short_op.tendencia)
        display_tendencia = ' & '.join(active_tendencies) if active_tendencies else 'NEUTRAL'

        reference_op = long_op if long_op.estado == 'ACTIVA' else short_op
        
        op_status_summary = {
            'tendencia': display_tendencia,
            'apalancamiento': reference_op.apalancamiento,
            'tamaño_posicion_base_usdt': reference_op.tamaño_posicion_base_usdt,
            'max_posiciones_logicas': f"L:{long_op.max_posiciones_logicas}/S:{short_op.max_posiciones_logicas}",
            'tiempo_ejecucion_str': "N/A"
        }

        summary_data = {
            "initialized": True,
            "operation_mode": display_tendencia,
            "operation_status": op_status_summary,
            "operation_pnl": total_pnl_ops,
            "operation_roi": operation_roi,
            "operation_long_pnl": operation_long_pnl,
            "operation_short_pnl": operation_short_pnl,
            "operation_long_roi": operation_long_roi,
            "operation_short_roi": operation_short_roi,
            "bm_balances": self._balance_manager.get_balances_summary(),
            "open_long_positions_count": len(open_longs),
            "open_short_positions_count": len(open_shorts),
            "open_long_positions": [self._helpers.format_pos_for_summary(asdict(p)) for p in open_longs],
            "open_short_positions": [self._helpers.format_pos_for_summary(asdict(p)) for p in open_shorts],
            "total_realized_pnl_session": self.get_total_pnl_realized(),
            "initial_total_capital": self._balance_manager.get_initial_total_capital(),
            "real_account_balances": self._balance_manager.get_real_balances_cache(),
            "session_limits": { "time_limit": self.get_session_time_limit() },
            "current_market_price": current_market_price,
        }
        return summary_data

    def get_unrealized_pnl(self, current_price: float) -> float:
        """Calcula el PNL no realizado total de todas las posiciones abiertas en la sesión."""
        total_pnl = 0.0
        
        long_op = self._om_api.get_operation_by_side('long')
        short_op = self._om_api.get_operation_by_side('short')
        
        if long_op:
            for pos in long_op.posiciones_activas.get('long', []):
                total_pnl += (current_price - pos.entry_price) * pos.size_contracts
        if short_op:
            for pos in short_op.posiciones_activas.get('short', []):
                total_pnl += (pos.entry_price - current_price) * pos.size_contracts
                
        return total_pnl
    
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