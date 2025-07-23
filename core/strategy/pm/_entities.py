"""
Módulo de Entidades de Dominio para el Position Manager.

Este archivo define las estructuras de datos fundamentales utilizadas en la lógica
de negocio del Position Manager, utilizando `dataclasses` para un tipado explícito
y una mayor claridad.

v2.1 (Refactor de Hitos):
- Corregido el orden de los atributos en `MilestoneAction` para cumplir con
  las reglas de Python sobre argumentos por defecto.
"""
import datetime
from dataclasses import dataclass, field
from typing import Optional, Dict, Any

# --- Entidades de Posiciones ---

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


# --- Entidades de Balance y Capital ---

@dataclass
class Balances:
    """Encapsula los balances lógicos de las cuentas operativas y de beneficios."""
    operational_long: float = 0.0
    operational_short: float = 0.0
    used_long: float = 0.0
    used_short: float = 0.0
    profit: float = 0.0
    
    @property
    def available_long(self) -> float:
        """Calcula el margen disponible para nuevas posiciones largas."""
        return max(0.0, self.operational_long - self.used_long)
        
    @property
    def available_short(self) -> float:
        """Calcula el margen disponible para nuevas posiciones cortas."""
        return max(0.0, self.operational_short - self.used_short)


# --- Entidades para el Árbol de Decisiones (Hitos y Tendencias) ---

@dataclass
class TrendConfig:
    """
    Encapsula todos los parámetros que definen una Tendencia operativa.
    """
    mode: str
    individual_sl_pct: float = 0.0
    trailing_stop_activation_pct: float = 0.0
    trailing_stop_distance_pct: float = 0.0
    limit_trade_count: Optional[int] = None
    limit_duration_minutes: Optional[int] = None
    limit_tp_roi_pct: Optional[float] = None
    limit_sl_roi_pct: Optional[float] = None


@dataclass
class MilestoneCondition:
    """Define la condición de precio que activa un Hito."""
    type: str
    value: float


# --- INICIO DE LA CORRECCIÓN ---
@dataclass
class MilestoneAction:
    """
    Define la acción que se ejecuta cuando un Hito se activa.
    """
    # El atributo sin valor por defecto (`params`) debe ir PRIMERO.
    params: TrendConfig
    # El atributo con valor por defecto (`type`) debe ir DESPUÉS.
    type: str = "START_TREND"
# --- FIN DE LA CORRECCIÓN ---


@dataclass
class Milestone:
    """
    Representa un Hito (Trigger) en el árbol de decisiones.
    """
    id: str
    condition: MilestoneCondition
    action: MilestoneAction
    
    parent_id: Optional[str] = None
    level: int = 1
    
    status: str = 'PENDING'
    
    one_shot: bool = True
    created_at: datetime.datetime = field(default_factory=datetime.datetime.now)