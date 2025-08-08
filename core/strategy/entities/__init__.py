# ./core/strategy/entities/__init__.py

"""
Paquete Central de Entidades de Dominio.

Este paquete contiene todas las definiciones de las clases de datos (entidades)
utilizadas por los diferentes gestores de la estrategia (OM, PM, etc.).

Al centralizar las entidades aquí, rompemos las dependencias circulares entre
los paquetes 'pm' y 'om', asegurando un flujo de dependencias unidireccional
y robusto.
"""
import datetime
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any # <<-- CAMBIO: Se añade 'Any' para type hinting

try:
    from core._utils import safe_division
except ImportError:
    def safe_division(n, d): return 0 if d == 0 else n / d

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
    est_liq_price: Optional[float] = None
    last_update_ts: Optional[datetime.datetime] = None

class Operacion:
    """
    Representa una única Operación Estratégica configurable.
    """
    def __init__(self, id: str):
        self.id: str = id
        self.estado: str = 'DETENIDA'
        self.tipo_cond_entrada: Optional[str] = 'MARKET'
        self.valor_cond_entrada: Optional[float] = 0.0
        self.tendencia: Optional[str] = None
        
        self.apalancamiento: float = 10.0
        
        self.sl_posicion_individual_pct: float = 10.0
        self.tsl_activacion_pct: float = 0.4
        self.tsl_distancia_pct: float = 0.1
        self.tsl_roi_activacion_pct: Optional[float] = None
        self.tsl_roi_distancia_pct: Optional[float] = None
        self.sl_roi_pct: Optional[float] = None
        self.tiempo_maximo_min: Optional[int] = None
        self.max_comercios: Optional[int] = None
        self.tipo_cond_salida: Optional[str] = None
        self.valor_cond_salida: Optional[float] = None
        self.accion_al_finalizar: str = 'PAUSAR'
        
        self.capital_inicial_usdt: float = 0.0
        self.pnl_realizado_usdt: float = 0.0
        # Este PNL no realizado es una "caché" que el EventProcessor actualiza.
        self.pnl_no_realizado_usdt_vivo: float = 0.0
        
        self.total_reinvertido_usdt: float = 0.0
        self.comercios_cerrados_contador: int = 0
        self.comisiones_totales_usdt: float = 0.0
        self.profit_balance_acumulado: float = 0.0
        
        self.tiempo_inicio_ejecucion: Optional[datetime.datetime] = None
        
        self.posiciones: List['LogicalPosition'] = []
        self.capital_flows: List['CapitalFlow'] = []
        self.sub_period_returns: List[float] = []
        
        self.tsl_roi_activo: bool = False
        self.tsl_roi_peak_pct: float = 0.0

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
        return sum(p.valor_nominal for p in self.posiciones)

    @property
    def posiciones_abiertas(self) -> List['LogicalPosition']:
        return [p for p in self.posiciones if p.estado == 'ABIERTA']
    
    @property
    def posiciones_pendientes(self) -> List['LogicalPosition']:
        return [p for p in self.posiciones if p.estado == 'PENDIENTE']

    @property
    def posiciones_abiertas_count(self) -> int:
        return len(self.posiciones_abiertas)

    @property
    def posiciones_pendientes_count(self) -> int:
        return len(self.posiciones_pendientes)
        
    @property
    def equity_total_usdt(self) -> float:
        """Calcula el Equity Histórico (contable) de la operación."""
        return self.capital_inicial_usdt + self.pnl_realizado_usdt

    @property
    def equity_actual_vivo(self) -> float:
        """
        Calcula el Equity "vivo" (valor de mercado).
        Usa la caché `pnl_no_realizado_usdt_vivo` que es actualizada externamente.
        """
        return self.equity_total_usdt + self.pnl_no_realizado_usdt_vivo
    
    @property
    def twrr_roi(self) -> float:
        """
        Calcula el TWRR usando la caché de PNL no realizado.
        """
        equity_inicial_periodo_actual = self.capital_inicial_usdt
        if self.capital_flows:
            last_flow = self.capital_flows[-1]
            equity_inicial_periodo_actual = last_flow.equity_before_flow + last_flow.flow_amount

        pnl_periodo_actual = self.equity_actual_vivo - equity_inicial_periodo_actual
        retorno_periodo_actual = safe_division(pnl_periodo_actual, equity_inicial_periodo_actual)

        if not self.sub_period_returns:
            return retorno_periodo_actual * 100

        total_return_factor = 1.0
        for r in self.sub_period_returns:
            total_return_factor *= r

        total_return_factor *= (1 + retorno_periodo_actual)
        return (total_return_factor - 1) * 100

    # --- INICIO DE LA NUEVA IMPLEMENTACIÓN ---
    def get_live_performance(self, current_price: float, utils_module: Any) -> Dict[str, float]:
        """
        Calcula y devuelve las métricas de rendimiento "en vivo" que dependen
        del precio de mercado actual.
        Recibe el módulo 'utils' para hacer divisiones seguras.
        """
        if not isinstance(current_price, (int, float)) or current_price <= 0:
            current_price = 0.0

        # 1. Calcular PNL No Realizado
        pnl_no_realizado = 0.0
        posiciones_abiertas = self.posiciones_abiertas
        side = 'long' if self.tendencia == 'LONG_ONLY' else 'short'

        for pos in posiciones_abiertas:
            if pos.entry_price and pos.entry_price > 0 and pos.size_contracts and pos.size_contracts > 0:
                if side == 'long':
                    pnl_no_realizado += (current_price - pos.entry_price) * pos.size_contracts
                else:
                    pnl_no_realizado += (pos.entry_price - current_price) * pos.size_contracts
        
        # 2. Calcular PNL Total (Realizado + No Realizado)
        pnl_total = self.pnl_realizado_usdt + pnl_no_realizado

        # 3. Calcular Equity Actual "Vivo"
        equity_actual_vivo = self.equity_total_usdt + pnl_no_realizado
        
        # 4. Calcular ROI (TWRR) "Vivo"
        equity_inicial_periodo_actual = self.capital_inicial_usdt
        if self.capital_flows:
            last_flow = self.capital_flows[-1]
            equity_inicial_periodo_actual = last_flow.equity_before_flow + last_flow.flow_amount

        pnl_periodo_actual = equity_actual_vivo - equity_inicial_periodo_actual
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
    # --- FIN DE LA NUEVA IMPLEMENTACIÓN ---

    def reset(self):
        self.estado = 'DETENIDA'
        self.capital_inicial_usdt = 0.0
        self.pnl_realizado_usdt = 0.0
        self.total_reinvertido_usdt = 0.0
        self.comercios_cerrados_contador = 0
        self.tiempo_inicio_ejecucion = None
        self.tsl_roi_activo = False
        self.tsl_roi_peak_pct = 0.0
        self.comisiones_totales_usdt = 0.0
        self.profit_balance_acumulado = 0.0
        self.pnl_no_realizado_usdt_vivo = 0.0
        self.posiciones = []
        self.capital_flows = []
        self.sub_period_returns = []