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

# ==============================================================================
# --- INICIO DEL CÓDIGO A REEMPLAZAR (Función __init__ en la clase Operacion) ---
# ==============================================================================

    def __init__(self, id: str):
        self.id: str = id
        self.estado: str = 'DETENIDA'
        self.estado_razon: str = 'Estado inicial'
        
        # --- Parámetros de Configuración ---
        self.tipo_cond_entrada: Optional[str] = 'MARKET'
        self.valor_cond_entrada: Optional[float] = 0.0
        self.tendencia: Optional[str] = None
        self.apalancamiento: float = 10.0
        self.averaging_distance_pct: float = 0.5
        self.sl_posicion_individual_pct: float = 10.0
        self.tsl_activacion_pct: float = 0.4
        self.tsl_distancia_pct: float = 0.1
        self.tsl_roi_activacion_pct: Optional[float] = None
        self.tsl_roi_distancia_pct: Optional[float] = None
        self.sl_roi_pct: Optional[float] = None
        self.dynamic_roi_sl_enabled: bool = False
        self.dynamic_roi_sl_trail_pct: Optional[float] = None
        self.tiempo_maximo_min: Optional[int] = None
        self.max_comercios: Optional[int] = None
        self.tipo_cond_salida: Optional[str] = None
        self.valor_cond_salida: Optional[float] = None
        self.accion_al_finalizar: str = 'PAUSAR'
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
        
        # --- INICIO DE LA MODIFICACIÓN: Añadir los nuevos atributos de tiempo ---
        self.tiempo_acumulado_activo_seg: float = 0.0
        self.tiempo_ultimo_inicio_activo: Optional[datetime.datetime] = None
        # --- FIN DE LA MODIFICACIÓN ---
        
        # --- Listas de Objetos ---
        self.posiciones: List['LogicalPosition'] = []
        self.capital_flows: List['CapitalFlow'] = []
        self.sub_period_returns: List[float] = []
        
        # Banderas de Estado de Salida
        self.tsl_roi_activo: bool = False
        self.tsl_roi_peak_pct: float = 0.0

# ==============================================================================
# --- FIN DEL CÓDIGO A REEMPLAZAR ---
# ==============================================================================

    @property
    def capital_operativo_logico_actual(self) -> float:
        """Suma el capital de todas las posiciones lógicas (abiertas o no). Es la base de capital actual de la operación."""
        return sum(p.capital_asignado for p in self.posiciones)

    @property
    def capital_en_uso(self) -> float:
        """Suma el capital de las posiciones que están actualmente abiertas en el mercado."""
        return sum(p.capital_asignado for p in self.posiciones if p.estado == 'ABIERTA')

    @property
    def capital_disponible(self) -> float:
        """Calcula el capital que aún no ha sido asignado a posiciones abiertas."""
        return self.capital_operativo_logico_actual - self.capital_en_uso

    @property
    def valor_nominal_total(self) -> float:
        """Suma el valor nominal (tamaño * precio) de todas las posiciones abiertas."""
        return sum(p.valor_nominal for p in self.posiciones_abiertas)

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
    def realized_twrr_roi(self) -> float:
        """
        Calcula el Time-Weighted Rate of Return (TWRR) basado únicamente en el PNL realizado
        y los flujos de capital. Esto proporciona un ROI preciso a pesar de los cambios
        en el capital operativo a lo largo del tiempo.
        """
        # 1. Determinar el capital inicial para el período de cálculo actual.
        equity_inicial_periodo_actual = self.capital_inicial_usdt
        if self.capital_flows:
            last_flow = self.capital_flows[-1]
            equity_inicial_periodo_actual = last_flow.equity_before_flow + last_flow.flow_amount

        # 2. Calcular el PNL del período actual (solo PNL realizado).
        # El equity actual basado en PNL realizado es `equity_total_usdt`.
        pnl_periodo_actual = self.equity_total_usdt - equity_inicial_periodo_actual
        
        # 3. Calcular el retorno del período actual.
        retorno_periodo_actual = safe_division(pnl_periodo_actual, equity_inicial_periodo_actual)
        
        # 4. Encadenar con los retornos de los sub-períodos anteriores.
        total_return_factor = 1.0
        for r in self.sub_period_returns:
            total_return_factor *= r
        
        total_return_factor *= (1 + retorno_periodo_actual)
        
        # 5. Calcular el ROI final.
        return (total_return_factor - 1) * 100

# ==============================================================================
# --- INICIO DEL CÓDIGO A REEMPLAZAR (Función en la clase Operacion) ---
# ==============================================================================

    def get_roi_sl_tp_price(self) -> Optional[float]:
        """
        Calcula el precio de mercado al que se alcanzaría el SL/TP por ROI configurado,
        recalculando el tamaño de la posición basado en el apalancamiento actual.
        """
        sl_roi_pct_target = self.sl_roi_pct
        if self.dynamic_roi_sl_enabled and self.dynamic_roi_sl_trail_pct is not None:
            sl_roi_pct_target = self.realized_twrr_roi - self.dynamic_roi_sl_trail_pct

        if sl_roi_pct_target is None:
            return None

        open_positions = self.posiciones_abiertas
        if not open_positions:
            return None

        # --- INICIO DE LA CORRECCIÓN: Recalcular tamaño y promedio ---
        total_value = 0.0
        total_size = 0.0
        for pos in open_positions:
            if pos.entry_price is None or pos.entry_price <= 0: continue
            # Recalcula el tamaño usando el apalancamiento actual de la operación
            size = safe_division(pos.capital_asignado * self.apalancamiento, pos.entry_price)
            if size > 0:
                total_value += pos.entry_price * size
                total_size += size
        # --- FIN DE LA CORRECCIÓN ---
        
        if total_size <= 1e-12:
            return None
            
        avg_entry_price = safe_division(total_value, total_size)

        base_capital = self.capital_en_uso
        if base_capital <= 0:
            return None
            
        pnl_target = (sl_roi_pct_target / 100) * base_capital
        unrealized_pnl_needed = pnl_target

        if self.tendencia == 'LONG_ONLY':
            target_price = avg_entry_price + safe_division(unrealized_pnl_needed, total_size)
        elif self.tendencia == 'SHORT_ONLY':
            target_price = avg_entry_price - safe_division(unrealized_pnl_needed, total_size)
        else:
            return None
            
        return target_price if target_price > 0 else None

# ==============================================================================
# --- FIN DEL CÓDIGO A REEMPLAZAR ---
# ==============================================================================
# ==============================================================================
# --- FIN DEL CÓDIGO A REEMPLAZAR ---
# ==============================================================================
    def get_live_performance(self, current_price: float, utils_module: Any) -> Dict[str, float]:
        """
        Calcula y devuelve las métricas de rendimiento "en vivo" que dependen
        del precio de mercado actual.
        """
        if not isinstance(current_price, (int, float)) or current_price <= 0:
            current_price = 0.0

        pnl_no_realizado = 0.0
        posiciones_abiertas = self.posiciones_abiertas
        side = 'long' if self.tendencia == 'LONG_ONLY' else 'short'

        for pos in posiciones_abiertas:
            if pos.entry_price and pos.entry_price > 0 and pos.size_contracts and pos.size_contracts > 0:
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

# ==============================================================================
# --- INICIO DEL CÓDIGO A REEMPLAZAR (Función reset en la clase Operacion) ---
# ==============================================================================

    def reset(self):
        """
        Limpia la operación para una nueva configuración, PERO CONSERVA los
        resultados financieros y la razón del último ciclo.
        """
        self.capital_inicial_usdt = 0.0
        self.total_reinvertido_usdt = 0.0
        self.comercios_cerrados_contador = 0
        self.profit_balance_acumulado = 0.0
        self.auto_reinvest_enabled = False
        self.tsl_roi_activo = False
        self.tsl_roi_peak_pct = 0.0
        self.reinvestable_profit_balance = 0.0
        self.dynamic_roi_sl_enabled = False
        self.dynamic_roi_sl_trail_pct = None
        
        self.posiciones = []
        self.capital_flows = []
        self.sub_period_returns = []
        
        self.tiempo_espera_minutos = None
        self.tiempo_inicio_espera = None
        
        # --- INICIO DE LA MODIFICACIÓN: Resetear los nuevos atributos de tiempo ---
        self.tiempo_acumulado_activo_seg = 0.0
        self.tiempo_ultimo_inicio_activo = None
        # --- FIN DE LA MODIFICACIÓN ---

# ==============================================================================
# --- FIN DEL CÓDIGO A REEMPLAZAR ---
# ==============================================================================