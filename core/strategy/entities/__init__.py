# core/strategy/entities/__init__.py

"""
Paquete Central de Entidades de Dominio.

Este paquete contiene todas las definiciones de las clases de datos (entidades)
utilizadas por los diferentes gestores de la estrategia (OM, PM, etc.).

Al centralizar las entidades aquí, rompemos las dependencias circulares entre
los paquetes 'pm' y 'om', asegurando un flujo de dependencias unidireccional
y robusto.
"""
import datetime
import config
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any 

try:
    from core._utils import safe_division
except ImportError:
    def safe_division(n, d, default=0): return default if d == 0 else n / d

@dataclass
class CapitalFlow:
    """Representa un único evento de flujo de capital externo."""
    timestamp: datetime.datetime
    equity_before_flow: float
    flow_amount: float # Positivo para depósitos, negativo para retiros

@dataclass
class LogicalPosition:
    """
    Representa una única operación de trading lógica. Entidad independiente
    con su propio estado y capital asignado.
    """
    id: str
    capital_asignado: float
    
    estado: str = 'PENDIENTE'
    
    entry_timestamp: Optional[datetime.datetime] = None
    entry_price: Optional[float] = None
    margin_usdt: float = 0.0
    size_contracts: Optional[float] = None
    valor_nominal: float = 0.0

    stop_loss_price: Optional[float] = None
    est_liq_price: Optional[float] = None
    tsl_activation_pct_at_open: float = 0.0
    tsl_distance_pct_at_open: float = 0.0
    ts_is_active: bool = False
    ts_peak_price: Optional[float] = None
    ts_stop_price: Optional[float] = None
    api_order_id: Optional[str] = None
    api_avg_fill_price: Optional[float] = None
    api_filled_qty: Optional[float] = None

@dataclass
class PhysicalPosition:
    """Representa el estado agregado de todas las posiciones lógicas de un lado."""
    avg_entry_price: float = 0.0
    total_size_contracts: float = 0.0
    total_margin_usdt: float = 0.0
    est_liq_price: Optional[datetime.datetime] = None
    last_update_ts: Optional[datetime.datetime] = None

class Operacion:
    """
    Representa una única Operación Estratégica configurable.
    """

    def __init__(self, id: str):
        self.id: str = id
        self.estado: str = 'DETENIDA'
        self.estado_razon: str = 'Estado inicial'
        self.precio_de_transicion: Optional[float] = None
        
        # --- Parámetros de Configuración ---
        self.tendencia: Optional[str] = None
        self.apalancamiento: float = 10.0
        self.averaging_distance_pct: float = 0.5
        self.sl_posicion_individual_pct: Optional[float] = 10.0
        self.tsl_activacion_pct: Optional[float] = 0.4
        self.tsl_distancia_pct: Optional[float] = 0.1
        
        self.roi_sl: Optional[Dict[str, Any]] = None
        self.roi_tp: Optional[Dict[str, Any]] = None
        self.roi_tsl: Optional[Dict[str, Any]] = None
        self.dynamic_roi_sl: Optional[Dict[str, Any]] = None
        self.be_sl: Optional[Dict[str, Any]] = None
        self.be_tp: Optional[Dict[str, Any]] = None
        
        self.tiempo_maximo_min: Optional[int] = None
        self.max_comercios: Optional[int] = None
        
        self.cond_entrada_above: Optional[float] = None
        self.cond_entrada_below: Optional[float] = None
        
        self.cond_salida_above: Optional[Dict[str, Any]] = None
        self.cond_salida_below: Optional[Dict[str, Any]] = None
        
        self.accion_por_limite_tiempo: str = 'PAUSAR'
        self.accion_por_limite_trades: str = 'PAUSAR'
        
        self.auto_reinvest_enabled: bool = False 
        self.tiempo_espera_minutos: Optional[int] = None
        self.tiempo_inicio_espera: Optional[datetime.datetime] = None
        
        # --- Atributos de Estado Financiero y Contadores ---
        self.capital_inicial_usdt: float = 0.0
        self.pnl_realizado_usdt: float = 0.0
        self.total_reinvertido_usdt: float = 0.0
        self.comercios_cerrados_contador: int = 0
        self.comisiones_totales_usdt: float = 0.0
        self.profit_balance_acumulado: float = 0.0
        self.reinvestable_profit_balance: float = 0.0
        
        self.tiempo_inicio_ejecucion: Optional[datetime.datetime] = None 
        self.tiempo_acumulado_activo_seg: float = 0.0
        self.tiempo_ultimo_inicio_activo: Optional[datetime.datetime] = None
        
        # --- Listas de Objetos ---
        self.posiciones: List['LogicalPosition'] = []
        self.capital_flows: List['CapitalFlow'] = []
        self.sub_period_returns: List[float] = []
        
        # Banderas de Estado de Salida
        self.tsl_roi_activo: bool = False
        self.tsl_roi_peak_pct: float = 0.0
        self.tiempo_inicio_sesion_activa: Optional[datetime.datetime] = None
        self.trades_en_sesion_activa: int = 0

    @property
    def capital_operativo_logico_actual(self) -> float:
        return sum(p.capital_asignado for p in self.posiciones)

    @property
    def capital_en_uso(self) -> float:
        return sum(p.capital_asignado for p in self.posiciones if p.estado == 'ABIERTA')

    @property
    def capital_disponible(self) -> float:
        return self.capital_operativo_logico_actual - self.capital_en_uso

    @property
    def valor_nominal_total(self) -> float:
        return sum(p.valor_nominal for p in self.posiciones_abiertas)

    @property
    def posiciones_abiertas(self) -> List['LogicalPosition']:
        return [p for p in self.posiciones if p.estado == 'ABIERTA']
    
    @property
    def posiciones_pendientes(self) -> List['LogicalPosition']:
        return [p for p in self.posiciones if p.estado == 'PENDIENTE']
    
    @property
    def avg_entry_price(self) -> Optional[float]:
        open_positions = self.posiciones_abiertas
        if not open_positions:
            return None
        total_value = 0.0
        total_size = 0.0
        for pos in open_positions:
            if pos.entry_price is not None and pos.size_contracts is not None and pos.size_contracts > 1e-12:
                 total_value += pos.entry_price * pos.size_contracts
                 total_size += pos.size_contracts
        if total_size <= 1e-12:
            return None
        return safe_division(total_value, total_size)
    
    @property
    def posiciones_abiertas_count(self) -> int:
        return len(self.posiciones_abiertas)

    @property
    def posiciones_pendientes_count(self) -> int:
        return len(self.posiciones_pendientes)
        
    @property
    def equity_total_usdt(self) -> float:
        return self.capital_inicial_usdt + self.pnl_realizado_usdt

    @property
    def realized_twrr_roi(self) -> float:
        equity_inicial_periodo_actual = self.capital_inicial_usdt
        if self.capital_flows:
            last_flow = self.capital_flows[-1]
            equity_inicial_periodo_actual = last_flow.equity_before_flow + last_flow.flow_amount
        pnl_periodo_actual = self.equity_total_usdt - equity_inicial_periodo_actual
        retorno_periodo_actual = safe_division(pnl_periodo_actual, equity_inicial_periodo_actual)
        total_return_factor = 1.0
        for r in self.sub_period_returns:
            total_return_factor *= r
        total_return_factor *= (1 + retorno_periodo_actual)
        return (total_return_factor - 1) * 100

    def get_live_performance(self, current_price: float, utils_module: Any) -> Dict[str, float]:
        if not isinstance(current_price, (int, float)) or current_price <= 0:
            current_price = 0.0
        pnl_no_realizado = 0.0
        side = 'long' if self.tendencia == 'LONG_ONLY' else 'short'
        for pos in self.posiciones_abiertas:
            if pos.entry_price is not None and pos.entry_price > 0 and pos.size_contracts is not None and pos.size_contracts > 0:
                if side == 'long':
                    pnl_no_realizado += (current_price - pos.entry_price) * pos.size_contracts
                else:
                    pnl_no_realizado += (pos.entry_price - current_price) * pos.size_contracts
        pnl_total = self.pnl_realizado_usdt + pnl_no_realizado
        equity_actual_vivo = self.capital_operativo_logico_actual + pnl_no_realizado
        equity_inicial_periodo_actual = self.capital_inicial_usdt
        if self.capital_flows:
            last_flow = self.capital_flows[-1]
            equity_inicial_periodo_actual = last_flow.equity_before_flow + last_flow.flow_amount
        pnl_periodo_actual = (self.equity_total_usdt + pnl_no_realizado) - equity_inicial_periodo_actual
        retorno_periodo_actual = utils_module.safe_division(pnl_periodo_actual, equity_inicial_periodo_actual)
        total_return_factor = 1.0
        for r in self.sub_period_returns:
            total_return_factor *= r
        total_return_factor *= (1 + retorno_periodo_actual)
        roi_twrr_vivo = (total_return_factor - 1) * 100
        return {
            "pnl_no_realizado": pnl_no_realizado,
            "pnl_total": pnl_total,
            "equity_actual_vivo": equity_actual_vivo,
            "roi_twrr_vivo": roi_twrr_vivo
        }

    def reset(self):
        self.capital_inicial_usdt = 0.0
        self.total_reinvertido_usdt = 0.0
        self.comercios_cerrados_contador = 0
        self.profit_balance_acumulado = 0.0
        self.auto_reinvest_enabled = False
        self.posiciones = []
        self.capital_flows = []
        self.sub_period_returns = []
        self.tiempo_espera_minutos = None
        self.tiempo_inicio_espera = None
        self.tiempo_inicio_ejecucion = None
        self.tiempo_acumulado_activo_seg = 0.0
        self.tiempo_ultimo_inicio_activo = None
        self.roi_sl = None
        self.roi_tp = None
        self.roi_tsl = None
        self.dynamic_roi_sl = None
        self.be_sl = None
        self.be_tp = None
        self.tsl_roi_activo = False
        self.tsl_roi_peak_pct = 0.0
        self.reinvestable_profit_balance = 0.0
        self.precio_de_transicion = None
        self.tiempo_inicio_sesion_activa = None
        self.trades_en_sesion_activa = 0

    def get_live_break_even_price(self) -> Optional[float]:
        open_positions = self.posiciones_abiertas
        if not open_positions:
            return None
        total_size = sum(p.size_contracts for p in open_positions if p.size_contracts is not None)
        if total_size <= 1e-12:
            return None
        commission_rate = config.SESSION_CONFIG["PROFIT"]["COMMISSION_RATE"]
        avg_entry = self.avg_entry_price
        if avg_entry is None:
            return None
        pnl_unrealized_target = -self.pnl_realizado_usdt
        if self.tendencia == 'LONG_ONLY':
            numerator = pnl_unrealized_target + (avg_entry * total_size * (1 + commission_rate))
            denominator = total_size * (1 - commission_rate)
            break_even_price = safe_division(numerator, denominator)
        elif self.tendencia == 'SHORT_ONLY':
            numerator = (avg_entry * total_size * (1 - commission_rate)) - pnl_unrealized_target
            denominator = total_size * (1 + commission_rate)
            break_even_price = safe_division(numerator, denominator)
        else:
            return None
        return break_even_price if break_even_price > 0 else None

    def get_active_sl_tp_price(self) -> Optional[float]:
        """
        Calcula el precio de mercado al que se alcanzaría el SL/TP de la operación,
        basándose únicamente en las posiciones ACTUALMENTE ABIERTAS.
        """
        target_roi_pct = None
        if self.dynamic_roi_sl:
            target_roi_pct = self.realized_twrr_roi - self.dynamic_roi_sl.get('distancia', 0)
        elif self.roi_sl:
            target_roi_pct = self.roi_sl.get('valor')
        elif self.roi_tp:
            target_roi_pct = self.roi_tp.get('valor')

        if target_roi_pct is None or not self.posiciones_abiertas:
            return None

        avg_entry_price = self.avg_entry_price
        total_size = sum(p.size_contracts for p in self.posiciones_abiertas if p.size_contracts)
        base_capital = self.capital_en_uso
        
        if not all([avg_entry_price, total_size > 1e-12, base_capital > 0]):
            return None
            
        pnl_target = (target_roi_pct / 100) * base_capital
        price_change_per_contract = safe_division(pnl_target, total_size)

        if self.tendencia == 'LONG_ONLY':
            target_price = avg_entry_price + price_change_per_contract
        elif self.tendencia == 'SHORT_ONLY':
            target_price = avg_entry_price - price_change_per_contract
        else:
            return None
            
        return target_price if target_price > 0 else None

    def get_projected_sl_tp_price(self, start_price_for_sim: float, target_roi_pct: float) -> Optional[float]:
        """
        Calcula el precio de mercado objetivo al que se alcanzaría un ROI específico,
        simulando que TODAS las posiciones (abiertas + pendientes) están activas.
        """
        if target_roi_pct is None:
            return None

        # --- Lógica de Simulación ---
        sim_total_value = 0.0
        sim_total_size = 0.0
        
        # Simular posiciones ya abiertas
        for pos in self.posiciones_abiertas:
            if pos.entry_price and pos.capital_asignado:
                size = safe_division(pos.capital_asignado * self.apalancamiento, pos.entry_price)
                if size > 0:
                    sim_total_value += pos.entry_price * size
                    sim_total_size += size
        
        # Simular posiciones pendientes
        last_sim_price = start_price_for_sim
        if self.averaging_distance_pct is not None and self.averaging_distance_pct > 0:
            for pos in self.posiciones_pendientes:
                next_entry = last_sim_price * (1 - self.averaging_distance_pct / 100) if self.tendencia == 'LONG_ONLY' else last_sim_price * (1 + self.averaging_distance_pct / 100)
                size = safe_division(pos.capital_asignado * self.apalancamiento, next_entry)
                if size <= 0: continue
                
                sim_total_value += next_entry * size
                sim_total_size += size
                last_sim_price = next_entry

        projected_avg_price = safe_division(sim_total_value, sim_total_size)
        projected_base_capital = sum(p.capital_asignado for p in self.posiciones)

        if not all([projected_avg_price > 0, sim_total_size > 1e-12, projected_base_capital > 0]):
            return None

        pnl_target = (target_roi_pct / 100) * projected_base_capital
        price_change_per_contract = safe_division(pnl_target, sim_total_size)

        if self.tendencia == 'LONG_ONLY':
            target_price = projected_avg_price + price_change_per_contract
        elif self.tendencia == 'SHORT_ONLY':
            target_price = projected_avg_price - price_change_per_contract
        else:
            return None
            
        return target_price if target_price > 0 else None
