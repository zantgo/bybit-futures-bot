"""
Módulo de Entidades de Dominio para el Position Manager.

v6.0 (Modelo de Operación Estratégica Única):
- Se elimina por completo el concepto de Hitos. Las clases `Hito`,
  `CondicionHito` y `AccionHito` han sido comentadas y serán eliminadas.
- La clase `Operacion` se convierte en la única entidad estratégica,
  conteniendo ahora su propio estado, condiciones de entrada y
  condiciones de salida.
- `ConfiguracionOperacion` se fusiona dentro de `Operacion` para simplificar.
"""
import datetime
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List

# --- Entidades de Posiciones (Sin cambios) ---

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


# --- Entidades de Balance y Capital (Sin cambios) ---

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


@dataclass
class Operacion:
    """
    Representa una única Operación Estratégica configurable. Contiene toda la
    lógica de estado, condiciones y parámetros de trading.
    """
    # --- Identificación y Estado ---
    id: str
    estado: str = 'EN_ESPERA'  # 'EN_ESPERA', 'ACTIVA', 'FINALIZADA'

    # --- Condición de Entrada ---
    tipo_cond_entrada: Optional[str] = 'MARKET' # 'PRICE_ABOVE', 'PRICE_BELOW', 'MARKET'
    valor_cond_entrada: Optional[float] = 0.0

    # --- Parámetros de Trading (antes en ConfiguracionOperacion) ---
    tendencia: str = 'NEUTRAL'
    tamaño_posicion_base_usdt: float = 1.0
    max_posiciones_logicas: int = 5
    apalancamiento: float = 10.0
    sl_posicion_individual_pct: float = 10.0
    tsl_activacion_pct: float = 0.4
    tsl_distancia_pct: float = 0.1

    # --- Condiciones de Salida (Límites de la Operación) ---
    tp_roi_pct: Optional[float] = None
    sl_roi_pct: Optional[float] = None
    tiempo_maximo_min: Optional[int] = None
    max_comercios: Optional[int] = None
    
    # --- Estado Dinámico (se actualiza durante la ejecución) ---
    capital_inicial_usdt: float = 0.0
    pnl_realizado_usdt: float = 0.0
    comercios_cerrados_contador: int = 0
    tiempo_inicio_ejecucion: Optional[datetime.datetime] = None
    posiciones_activas: Dict[str, List[LogicalPosition]] = field(default_factory=lambda: {'long': [], 'short': []})
