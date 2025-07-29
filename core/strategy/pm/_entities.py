"""
Módulo de Entidades de Dominio para el Position Manager.

v6.3 (Condición de Salida por Precio):
- Se añaden los campos `tipo_cond_salida` y `valor_cond_salida` a la entidad
  `Operacion` para permitir la finalización de una estrategia basada en un
  nivel de precio específico, además de los límites existentes.
"""
import datetime
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Union

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
    
    # Parámetros de Trailing Stop fijados en el momento de la apertura
    tsl_activation_pct_at_open: float = 0.0
    tsl_distance_pct_at_open: float = 0.0
    
    # Estado dinámico del Trailing Stop
    ts_is_active: bool = False
    ts_peak_price: Optional[float] = None
    ts_stop_price: Optional[float] = None
    
    # Datos de la API
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


# --- Entidad de Operación Única ---

@dataclass
class Operacion:
    """
    Representa una única Operación Estratégica configurable. Contiene toda la
    lógica de estado, condiciones y parámetros de trading.
    """
    # Identificación y Estado
    id: str
    estado: str = 'EN_ESPERA'

    # Condición de Entrada
    tipo_cond_entrada: Optional[str] = 'MARKET'
    valor_cond_entrada: Optional[float] = 0.0

    # Parámetros de Trading
    tendencia: str = 'NEUTRAL'
    tamaño_posicion_base_usdt: float = 1.0
    max_posiciones_logicas: int = 5
    apalancamiento: float = 10.0
    sl_posicion_individual_pct: float = 10.0
    tsl_activacion_pct: float = 0.4
    tsl_distancia_pct: float = 0.1

    # Condiciones de Salida (Límites)
    tp_roi_pct: Optional[float] = None
    sl_roi_pct: Optional[float] = None
    tiempo_maximo_min: Optional[int] = None
    max_comercios: Optional[int] = None
    
    # --- INICIO DE LA MODIFICACIÓN ---
    # Nueva Condición de Salida por Precio
    tipo_cond_salida: Optional[str] = None # 'PRICE_ABOVE', 'PRICE_BELOW'
    valor_cond_salida: Optional[float] = None
    # --- FIN DE LA MODIFICACIÓN ---
    
    # Estado Dinámico
    capital_inicial_usdt: float = 0.0
    pnl_realizado_usdt: float = 0.0
    comercios_cerrados_contador: int = 0
    tiempo_inicio_ejecucion: Optional[datetime.datetime] = None
    posiciones_activas: Dict[str, List[LogicalPosition]] = field(default_factory=lambda: {'long': [], 'short': []})