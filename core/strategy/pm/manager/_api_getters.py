"""
Módulo del Position Manager: API de Getters.

v6.1 (Consolidación de Entidades):
- Se actualiza `get_position_summary` para que `operation_mode` refleje
  la tendencia de la `operacion_activa` directamente.
- Se mejora `get_operation_state` para ser más robusto y añadir el
  cálculo del tiempo de ejecución.
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
        Obtiene un resumen completo y FRESCO del estado del PM.
        Esta función es la fuente única de datos para el dashboard.
        """
        if not self._initialized: return {"error": "PM no instanciado"}
        
        ticker_data = self._exchange.get_ticker(getattr(self._config, 'TICKER_SYMBOL', 'N/A'))
        current_market_price = ticker_data.price if ticker_data else (self.get_current_market_price() or 0.0)

        open_longs = self.operacion_activa.posiciones_activas['long'] if self.operacion_activa else []
        open_shorts = self.operacion_activa.posiciones_activas['short'] if self.operacion_activa else []
        
        # (COMENTADO) La referencia a _milestones es obsoleta.
        # milestones_as_dicts = [asdict(m) for m in self._milestones]
        
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

        summary_data = {
            "initialized": True,
            # (MODIFICADO) Se usa la tendencia de la operacion_activa para ser más preciso.
            "operation_mode": self.operacion_activa.tendencia if self.operacion_activa else 'NEUTRAL',
            # (COMENTADO) Código anterior
            # "operation_mode": self._operation_mode,
            "operation_status": self.get_operation_state(),
            "operation_pnl": operation_total_pnl,
            "operation_roi": operation_roi,
            "bm_balances": self._balance_manager.get_balances_summary(),
            "open_long_positions_count": len(open_longs),
            "open_short_positions_count": len(open_shorts),
            "open_long_positions": [self._helpers.format_pos_for_summary(asdict(p)) for p in open_longs],
            "open_short_positions": [self._helpers.format_pos_for_summary(asdict(p)) for p in open_shorts],
            "total_realized_pnl_session": self.get_total_pnl_realized(),
            "initial_total_capital": self._balance_manager.get_initial_total_capital(),
            "real_account_balances": self._balance_manager.get_real_balances_cache(),
            "session_limits": { "time_limit": self.get_session_time_limit() },
            # (COMENTADO) La clave "all_milestones" ya no se necesita en el resumen.
            # "all_milestones": milestones_as_dicts,
            "current_market_price": current_market_price,
        }
        return summary_data

    def get_unrealized_pnl(self, current_price: float) -> float:
        """Calcula el PNL no realizado total de todas las posiciones abiertas en la sesión."""
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
    
    # (COMENTADO) get_trend_state es obsoleto y reemplazado por get_operation_state ---
    # def get_trend_state(self) -> Dict[str, Any]: ...

    def get_operation(self) -> Optional[Operacion]:
        """Devuelve el objeto de la operación estratégica actual."""
        return self.operacion_activa

    def get_operation_state(self) -> Dict[str, Any]:
        """Devuelve un diccionario con el estado completo de la operación activa."""
        if not self.operacion_activa:
            # (MODIFICADO) Devolver un estado NEUTRAL por defecto para evitar errores en la TUI.
            return Operacion().to_dict()
            # (COMENTADO) Código anterior
            # return {'error': 'Operacion no inicializada'}
        
        op_dict = asdict(self.operacion_activa)

        # (MODIFICADO) Añadir tiempo de ejecución formateado para la TUI.
        if self.operacion_activa.tiempo_inicio_ejecucion:
            duration = datetime.datetime.now(datetime.timezone.utc) - self.operacion_activa.tiempo_inicio_ejecucion
            total_seconds = int(duration.total_seconds())
            hours, remainder = divmod(total_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            op_dict['tiempo_ejecucion_str'] = f"{hours:02}:{minutes:02}:{seconds:02}"
        else:
            op_dict['tiempo_ejecucion_str'] = "00:00:00"

        return op_dict

    def get_operation_parameters(self) -> Dict[str, Any]:
        """Devuelve solo los parámetros de configuración de la operación activa."""
        if not self.operacion_activa:
            return {}
        
        config_fields = [
            'estado', 'tipo_cond_entrada', 'valor_cond_entrada',
            'tendencia', 'tamaño_posicion_base_usdt', 'max_posiciones_logicas',
            'apalancamiento', 'sl_posicion_individual_pct', 'tsl_activacion_pct',
            'tsl_distancia_pct', 'tp_roi_pct', 'sl_roi_pct', 'tiempo_maximo_min',
            'max_comercios'
        ]
        
        op_dict = asdict(self.operacion_activa)
        return {key: op_dict.get(key) for key in config_fields}

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
        
    # (COMENTADO) get_all_milestones es obsoleto en la nueva arquitectura.
    # def get_all_milestones(self) -> List[Any]: 
    #     """Obtiene todos los hitos (triggers) como objetos Hito."""
    #     if hasattr(self, '_milestones'):
    #         return copy.deepcopy(self._milestones)
    #     return []
        
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