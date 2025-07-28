"""
Módulo de Entidades de Dominio para el Position Manager.

v5.2 (Sincronización de Entidades):
- Asegura que la definición de `CondicionHito` coincida con su uso en la TUI,
  utilizando `tipo_condicion_precio` y `valor_condicion_precio` para una
  lógica de activación de un solo paso.
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


# --- ENTIDADES PARA EL MODELO DE OPERACIONES SECUENCIALES ---

# --- 1. La Entidad Central: Operacion ---

@dataclass
class ConfiguracionOperacion:
    """
    Define los parámetros de configuración inmutables para una Operacion de trading.
    """
    tendencia: str
    tamaño_posicion_base_usdt: float
    max_posiciones_logicas: int
    apalancamiento: float
    sl_posicion_individual_pct: float
    tsl_activacion_pct: float
    tsl_distancia_pct: float


@dataclass
class Operacion:
    """
    Representa un ciclo de vida completo de trading.
    """
    id: str
    configuracion: ConfiguracionOperacion
    capital_inicial_usdt: float
    pnl_realizado_usdt: float = 0.0
    comercios_cerrados_contador: int = 0
    tiempo_inicio_ejecucion: Optional[datetime.datetime] = None
    posiciones_activas: Dict[str, List[LogicalPosition]] = field(default_factory=lambda: {'long': [], 'short': []})


# --- 2. Entidades para los Nuevos Hitos Especializados ---

# --- INICIO DE LA CORRECCIÓN: Definición correcta de CondicionHito ---
@dataclass
class CondicionHito:
    """
    Contenedor para todas las posibles condiciones que pueden activar un hito.
    """
    # Para Hitos de Inicialización (y opcionalmente de Finalización)
    # tipo_condicion_precio puede ser: 'PRICE_ABOVE', 'PRICE_BELOW', 'MARKET'
    tipo_condicion_precio: Optional[str] = None 
    valor_condicion_precio: Optional[float] = None
    
    # Para Hitos de Finalización
    tp_roi_pct: Optional[float] = None
    sl_roi_pct: Optional[float] = None
    tiempo_maximo_min: Optional[int] = None
    max_comercios: Optional[int] = None
# --- FIN DE LA CORRECCIÓN ---

@dataclass
class AccionHito:
    """
    Define la acción que se ejecuta cuando un Hito se activa.
    """
    configuracion_nueva_operacion: Optional[ConfiguracionOperacion] = None
    cerrar_posiciones_al_finalizar: bool = False


@dataclass
class Hito:
    """
    La entidad Hito, que representa un nodo en el árbol de decisiones.
    """
    id: str
    tipo_hito: str
    condicion: CondicionHito
    accion: AccionHito
    parent_id: Optional[str] = None
    level: int = 1
    status: str = 'PENDING'
    one_shot: bool = True
    created_at: datetime.datetime = field(default_factory=datetime.datetime.now)