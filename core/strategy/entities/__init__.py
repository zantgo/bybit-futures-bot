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
from typing import Optional, Dict, List

# --- Entidad de Balance (Usada por Operacion) ---

@dataclass
class LogicalBalances:
    """Encapsula y gestiona el capital lógico para una única operación."""
    operational_margin: float = 0.0
    used_margin: float = 0.0
    profit_balance: float = 0.0

    @property
    def available_margin(self) -> float:
        return max(0.0, self.operational_margin - self.used_margin)

    def decrease_available_margin(self, amount: float):
        if isinstance(amount, (int, float)) and amount > 0:
            self.used_margin += abs(amount)

    def increase_available_margin(self, amount: float):
        if isinstance(amount, (int, float)) and amount > 0:
            self.used_margin = max(0.0, self.used_margin - abs(amount))
            
    def record_profit_transfer(self, amount_transferred: float):
        if isinstance(amount_transferred, (int, float)) and amount_transferred > 0:
            self.profit_balance += amount_transferred

    def reset(self):
        self.operational_margin = 0.0
        self.used_margin = 0.0
        self.profit_balance = 0.0

# --- Entidades de Posición (Usadas por Operacion y PM) ---

@dataclass
class LogicalPosition:
    """Representa una única operación de trading lógica (un 'slot')."""
    id: str
    entry_timestamp: datetime.datetime
    entry_price: float
    margin_usdt: float
    size_contracts: float
    leverage: float
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

# --- Entidad de Operación (Usada por OM) ---

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
        self.tamaño_posicion_base_usdt: float = 1.0
        self.max_posiciones_logicas: int = 5
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
        self.comercios_cerrados_contador: int = 0
        self.tiempo_inicio_ejecucion: Optional[datetime.datetime] = None
        self.posiciones_activas: Dict[str, List['LogicalPosition']] = {'long': [], 'short': []}
        self.tsl_roi_activo: bool = False
        self.tsl_roi_peak_pct: float = 0.0
        self.comisiones_totales_usdt: float = 0.0
        self.balances: LogicalBalances = LogicalBalances()

    def reset(self):
        """Resetea el estado dinámico de la operación a sus valores por defecto."""
        self.estado = 'DETENIDA'
        self.capital_inicial_usdt = 0.0
        self.pnl_realizado_usdt = 0.0
        self.comercios_cerrados_contador = 0
        self.tiempo_inicio_ejecucion = None
        self.tsl_roi_activo = False
        self.tsl_roi_peak_pct = 0.0
        self.comisiones_totales_usdt = 0.0
        if hasattr(self, 'balances') and self.balances and hasattr(self.balances, 'reset'):
            self.balances.reset()
        else:
            self.balances = LogicalBalances()