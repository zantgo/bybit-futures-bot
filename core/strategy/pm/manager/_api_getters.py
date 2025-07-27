# core/strategy/pm/manager/_api_getters.py

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
    # --- INICIO DE LA MODIFICACIÓN: Importar nuevas entidades ---
    from .._entities import Hito, Operacion
    # from .._entities import Milestone # Comentada la antigua entidad
    # --- FIN DE LA MODIFICACIÓN ---
except ImportError:
    # --- INICIO DE LA MODIFICACIÓN: Añadir fallbacks para nuevas entidades ---
    class Hito: pass
    class Operacion: pass
    # class Milestone: pass
    # --- FIN DE LA MODIFICACIÓN ---

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

        # --- INICIO DE LA MODIFICACIÓN: Leer posiciones desde la Operación Activa ---
        open_longs = self.operacion_activa.posiciones_activas['long'] if self.operacion_activa else []
        open_shorts = self.operacion_activa.posiciones_activas['short'] if self.operacion_activa else []
        # --- FIN DE LA MODIFICACIÓN ---
        
        from dataclasses import asdict
        milestones_as_dicts = [asdict(m) for m in self._milestones]

        # --- INICIO DE LA MODIFICACIÓN: Calcular PNL y ROI de la Operación actual ---
        operation_unrealized_pnl = 0.0
        if self.operacion_activa:
            for side in ['long', 'short']:
                for pos in self.operacion_activa.posiciones_activas[side]:
                    entry = pos.entry_price
                    size = pos.size_contracts
                    if side == 'long': operation_unrealized_pnl += (current_market_price - entry) * size
                    else: operation_unrealized_pnl += (entry - current_market_price) * size
            
            operation_total_pnl = self.operacion_activa.pnl_realizado_usdt + operation_unrealized_pnl
            initial_capital_op = self.operacion_activa.capital_inicial_usdt
            operation_roi = self._utils.safe_division(operation_total_pnl, initial_capital_op) * 100 if initial_capital_op > 0 else 0.0
        else:
            operation_total_pnl = 0.0
            operation_roi = 0.0
        # --- FIN DE LA MODIFICACIÓN ---


        summary_data = {
            "initialized": True,
            "operation_mode": self._operation_mode,
            # --- INICIO DE LA MODIFICACIÓN: Adaptar al nuevo modelo de Operación ---
            "operation_status": self.get_operation_state(),
            # "trend_status": self.get_trend_state(), # Comentada la antigua clave
            # "leverage": self._leverage, # Comentado, ahora dentro de la operación
            # "max_logical_positions": self._max_logical_positions, # Comentado, ahora dentro de la operación
            # "initial_base_position_size_usdt": self._initial_base_position_size_usdt, # Comentado, ahora dentro de la operación
            "operation_pnl": operation_total_pnl,
            "operation_roi": operation_roi,
            # --- FIN DE LA MODIFICACIÓN ---
            "bm_balances": self._balance_manager.get_balances_summary(),
            "open_long_positions_count": len(open_longs),
            "open_short_positions_count": len(open_shorts),
            # --- INICIO DE LA MODIFICACIÓN: Usar asdict para las posiciones lógicas ---
            "open_long_positions": [self._helpers.format_pos_for_summary(asdict(p)) for p in open_longs],
            "open_short_positions": [self._helpers.format_pos_for_summary(asdict(p)) for p in open_shorts],
            # --- FIN DE LA MODIFICACIÓN ---
            "total_realized_pnl_session": self.get_total_pnl_realized(),
            "initial_total_capital": self._balance_manager.get_initial_total_capital(),
            "real_account_balances": self._balance_manager.get_real_balances_cache(),
            "session_limits": { "time_limit": self.get_session_time_limit() },
            "all_milestones": milestones_as_dicts,
            "current_market_price": current_market_price,
        }
        return summary_data

    def get_unrealized_pnl(self, current_price: float) -> float:
        """Calcula el PNL no realizado total de todas las posiciones abiertas en la sesión."""
        # Esta función ahora calcula el PNL total de la SESIÓN, no de la operación
        # Se mantiene para los límites globales de sesión
        total_pnl = 0.0
        if not self.operacion_activa:
            return 0.0
            
        for side in ['long', 'short']:
            for pos in self.operacion_activa.posiciones_activas[side]:
                entry = pos.entry_price
                size = pos.size_contracts
                if side == 'long': total_pnl += (current_price - entry) * size
                else: total_pnl += (entry - current_price) * size
        return total_pnl

    # --- (COMENTADO) get_trend_state ---
    # def get_trend_state(self) -> Dict[str, Any]:
    #     """Devuelve el estado de la tendencia activa."""
    #     if not self._active_trend:
    #         return {'mode': 'NEUTRAL'}
        
    #     from dataclasses import asdict
    #     return {
    #         'mode': self._active_trend['config'].mode,
    #         'milestone_id': self._active_trend['milestone_id'],
    #         'start_time': self._active_trend['start_time'],
    #         'trades_executed': self._active_trend['trades_executed'],
    #         'initial_pnl': self._active_trend['initial_pnl'],
    #         'config': asdict(self._active_trend['config'])
    #     }

    # --- INICIO DE LA MODIFICACIÓN: Nuevos getters para la Operación ---
    def get_operation_state(self) -> Dict[str, Any]:
        """Devuelve un diccionario con el estado completo de la operación activa."""
        if not self.operacion_activa:
            return {'error': 'Operacion no inicializada'}
        
        from dataclasses import asdict
        
        # Calcular capital actual y tiempo de ejecución para el estado
        current_capital = self.operacion_activa.capital_inicial_usdt + self.operacion_activa.pnl_realizado_usdt
        execution_time_str = "N/A"
        if self.operacion_activa.tiempo_inicio_ejecucion:
            duration = datetime.datetime.now(timezone.utc) - self.operacion_activa.tiempo_inicio_ejecucion
            execution_time_str = str(duration).split('.')[0]

        return {
            "id": self.operacion_activa.id,
            "configuracion": asdict(self.operacion_activa.configuracion),
            "capital_inicial_usdt": self.operacion_activa.capital_inicial_usdt,
            "capital_actual_usdt": current_capital, # Nota: No incluye PNL no realizado aquí
            "pnl_realizado_usdt": self.operacion_activa.pnl_realizado_usdt,
            "comercios_cerrados_contador": self.operacion_activa.comercios_cerrados_contador,
            "tiempo_inicio_ejecucion": self.operacion_activa.tiempo_inicio_ejecucion,
            "tiempo_ejecucion_str": execution_time_str,
            "posiciones_long_count": len(self.operacion_activa.posiciones_activas['long']),
            "posiciones_short_count": len(self.operacion_activa.posiciones_activas['short']),
        }

    # --- (COMENTADO) get_trend_limits ---
    # def get_trend_limits(self) -> Dict[str, Any]:
    #     """Devuelve los límites de la tendencia activa."""
    #     if not self._active_trend:
    #         return {}
        
    #     config = self._active_trend['config']
    #     return {
    #         "start_time": self._active_trend['start_time'],
    #         "duration_minutes": config.limit_duration_minutes,
    #         "tp_roi_pct": config.limit_tp_roi_pct,
    #         "sl_roi_pct": config.limit_sl_roi_pct,
    #         "trade_limit": config.limit_trade_count
    #     }

    def get_operation_parameters(self) -> Dict[str, Any]:
        """Devuelve solo los parámetros de configuración de la operación activa."""
        if not self.operacion_activa:
            return {}
        from dataclasses import asdict
        return asdict(self.operacion_activa.configuracion)
    # --- FIN DE LA MODIFICACIÓN ---

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
        
    def get_all_milestones(self) -> List[Hito]: 
        """Obtiene todos los hitos (triggers) como objetos Hito."""
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

    # --- (COMENTADO) Getters de atributos que ahora son parte de la operación ---
    # def get_max_logical_positions(self) -> int: 
    #     """Obtiene el número máximo de posiciones lógicas permitidas por lado."""
    #     return self._max_logical_positions
        
    # def get_initial_base_position_size(self) -> float: 
    #     """Obtiene el tamaño base inicial de las posiciones configurado para la sesión."""
    #     return self._initial_base_position_size_usdt
        
    # def get_leverage(self) -> float: 
    #     """Obtiene el apalancamiento actual de la sesión."""
    #     return self._leverage