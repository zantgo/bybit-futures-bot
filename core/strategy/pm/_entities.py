"""
Módulo de Entidades de Dominio para el Position Manager.

Este archivo define las estructuras de datos fundamentales utilizadas en la lógica
de negocio del Position Manager, utilizando `dataclasses` para un tipado explícito
y una mayor claridad. Estas clases representan los conceptos de negocio puros,
independientes de cualquier implementación externa.
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
    
    # Campos para el Trailing Stop
    ts_is_active: bool = False
    ts_peak_price: Optional[float] = None
    ts_stop_price: Optional[float] = None
    
    # Datos de la API post-ejecución, para sincronización y logging
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


# --- Entidades para el Árbol de Decisiones (Hitos/Triggers) ---

@dataclass
class MilestoneCondition:
    """Define la condición de precio que activa un Hito."""
    type: str  # Ej: 'PRICE_ABOVE', 'PRICE_BELOW'
    value: float


@dataclass
class MilestoneAction:
    """Define la acción que se ejecuta cuando un Hito se activa."""
    type: str      # Ej: 'START_MANUAL_TREND', 'SET_MODE', 'CLOSE_ALL_LONGS'
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Milestone:
    """
    Representa un Hito (Trigger) en el árbol de decisiones.
    """
    id: str
    condition: MilestoneCondition
    action: MilestoneAction
    
    # Atributos para la jerarquía y el estado del árbol
    parent_id: Optional[str] = None  # None o "ROOT" para hitos de Nivel 1
    level: int = 1
    
    # Estados:
    #   - PENDING: Esperando a que su padre se cumpla.
    #   - ACTIVE: Listo para ser evaluado contra el precio de mercado.
    #   - COMPLETED: Ya se ejecutó.
    #   - CANCELLED: Un hito hermano se ejecutó, cancelando este.
    status: str = 'PENDING'
    
    # Atributos de configuración
    one_shot: bool = True # Si se desactiva después de ejecutarse
    
    # Metadatos
    created_at: datetime.datetime = field(default_factory=datetime.datetime.now)