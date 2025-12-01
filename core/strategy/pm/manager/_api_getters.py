import datetime
import copy
from typing import Optional, Dict, Any, List
from dataclasses import asdict

try:
    from core.strategy.entities import Operacion, LogicalPosition
except ImportError:
    class Operacion: pass
    class LogicalPosition: pass

class _ApiGetters:
    """Clase base que contiene los getters públicos de la API del PositionManager."""
    
    def is_initialized(self) -> bool: 
        return self._initialized

    def get_position_summary(self) -> dict:
        """
        Genera un resumen completo del estado actual de las posiciones y operaciones.
        Actualizado para usar la nueva estructura de la entidad Operacion.
        """
        if not self._initialized:
            return {"error": "PM no inicializado"}
        
        long_op = self._om_api.get_operation_by_side('long')
        short_op = self._om_api.get_operation_by_side('short')

        if not long_op or not short_op:
            return {"error": "Operaciones Long/Short no disponibles en el OM"}

        ticker_data = self._exchange.get_ticker(self._config.BOT_CONFIG["TICKER"]["SYMBOL"])
        current_market_price = ticker_data.price if ticker_data else (self.get_current_market_price() or 0.0)

        open_longs = long_op.posiciones_abiertas
        open_shorts = short_op.posiciones_abiertas
        
        long_live_perf = long_op.get_live_performance(current_market_price, self._utils)
        short_live_perf = short_op.get_live_performance(current_market_price, self._utils)
        
        operation_long_pnl = long_live_perf.get("pnl_total", 0.0)
        operation_short_pnl = short_live_perf.get("pnl_total", 0.0)
        operation_long_roi = long_live_perf.get("roi_twrr_vivo", 0.0)
        operation_short_roi = short_live_perf.get("roi_twrr_vivo", 0.0)
        
        initial_capital_ops = long_op.capital_inicial_usdt + short_op.capital_inicial_usdt

        active_tendencies = []
        if long_op.estado == 'ACTIVA': active_tendencies.append(long_op.tendencia)
        if short_op.estado == 'ACTIVA': active_tendencies.append(short_op.tendencia)
        display_tendencia = ' & '.join(active_tendencies) if active_tendencies else 'NEUTRAL'

        def get_op_details(op: Operacion):
            if not op: return {}
            start_time = op.tiempo_inicio_ejecucion
            duration_str = "N/A"
            if op.estado == 'ACTIVA' and start_time:
                 duration = datetime.datetime.now(datetime.timezone.utc) - start_time
                 duration_str = str(datetime.timedelta(seconds=int(duration.total_seconds())))
            
            return {
                "id": op.id, "estado": op.estado, "tendencia": op.tendencia,
                "duracion_activa": duration_str
            }
        
        operations_info = { 'long': get_op_details(long_op), 'short': get_op_details(short_op) }
        reference_op = long_op if long_op.estado == 'ACTIVA' else short_op
        
        op_status_summary = {
            'tendencia': display_tendencia, 'apalancamiento': reference_op.apalancamiento,
            'posiciones_long': f"{len(open_longs)} / {len(long_op.posiciones)}",
            'posiciones_short': f"{len(open_shorts)} / {len(short_op.posiciones)}",
            'capital_logico_total': f"L:${long_op.capital_operativo_logico_actual:.2f} / S:${short_op.capital_operativo_logico_actual:.2f}"
        }

        return {
            "initialized": True, "operation_mode": display_tendencia,
            "operation_status": op_status_summary, "operations_info": operations_info,
            "operation_long_pnl": operation_long_pnl, "operation_short_pnl": operation_short_pnl,
            "operation_long_roi": operation_long_roi, "operation_short_roi": operation_short_roi,
            "open_long_positions_count": len(open_longs), "open_short_positions_count": len(open_shorts),
            "open_long_positions": open_longs,
            "open_short_positions": open_shorts,
            "total_realized_pnl_session": self.get_total_pnl_realized(),
            "initial_total_capital": initial_capital_ops,
            "current_market_price": current_market_price,
        }

    def get_unrealized_pnl(self, current_price: float) -> float:
        total_pnl = 0.0
        long_op = self._om_api.get_operation_by_side('long')
        short_op = self._om_api.get_operation_by_side('short')
        
        if long_op:
            for pos in long_op.posiciones_abiertas:
                if pos.entry_price and pos.size_contracts:
                    total_pnl += (current_price - pos.entry_price) * pos.size_contracts
        if short_op:
            for pos in short_op.posiciones_abiertas:
                 if pos.entry_price and pos.size_contracts:
                    total_pnl += (pos.entry_price - current_price) * pos.size_contracts
        
        return total_pnl
    
    def get_session_start_time(self) -> Optional[datetime.datetime]: 
        return self._session_start_time
        
    def get_total_pnl_realized(self) -> float: 
        return self._total_realized_pnl_long + self._total_realized_pnl_short

    def get_current_market_price(self) -> Optional[float]:
        try:
            return self._exchange.get_latest_price()
        except (AttributeError, TypeError):
            return None
