# core/strategy/pm/_entities.py

"""
Módulo de Entidades de Dominio para el Position Manager.

Este archivo define las estructuras de datos fundamentales utilizadas en la lógica
de negocio del Position Manager, utilizando `dataclasses` para un tipado explícito
y una mayor claridad.

v2.1 (Refactor de Hitos):
- Corregido el orden de los atributos en `MilestoneAction` para cumplir con
  las reglas de Python sobre argumentos por defecto.

v3.0 (Modelo de Operaciones):
- Introducida la clase `Operacion` como entidad central del estado.
- Refactorizados los Hitos para dividirse conceptualmente en tipos de
  'Inicialización' y 'Finalización' con estructuras de condición y acción
  especializadas.
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


# --- (COMENTADO) Entidades Antiguas para el Árbol de Decisiones (Hitos y Tendencias) ---
# Se conservan comentadas como referencia durante la transición.

# @dataclass
# class TrendConfig:
#     """
#     Encapsula todos los parámetros que definen una Tendencia operativa.
#     """
#     mode: str
#     individual_sl_pct: float = 0.0
#     trailing_stop_activation_pct: float = 0.0
#     trailing_stop_distance_pct: float = 0.0
#     limit_trade_count: Optional[int] = None
#     limit_duration_minutes: Optional[int] = None
#     limit_tp_roi_pct: Optional[float] = None
#     limit_sl_roi_pct: Optional[float] = None


# @dataclass
# class MilestoneCondition:
#     """Define la condición de precio que activa un Hito."""
#     type: str
#     value: float


# @dataclass
# class MilestoneAction:
#     """
#     Define la acción que se ejecuta cuando un Hito se activa.
#     """
#     params: TrendConfig
#     type: str = "START_TREND"


# @dataclass
# class Milestone:
#     """
#     Representa un Hito (Trigger) en el árbol de decisiones.
#     """
#     id: str
#     condition: MilestoneCondition
#     action: MilestoneAction
    
#     parent_id: Optional[str] = None
#     level: int = 1
    
#     status: str = 'PENDING'
    
#     one_shot: bool = True
#     created_at: datetime.datetime = field(default_factory=datetime.datetime.now)


# --- INICIO: NUEVAS ENTIDADES PARA EL MODELO DE OPERACIONES SECUENCIALES ---

# --- 1. La Entidad Central: Operacion ---

@dataclass
class ConfiguracionOperacion:
    """
    Define los parámetros de configuración inmutables para una Operacion de trading.
    Esta configuración es establecida por un Hito de Inicialización.
    """
    tendencia: str  # 'LONG_ONLY', 'SHORT_ONLY', 'LONG_SHORT', o 'NEUTRAL'
    tamaño_posicion_base_usdt: float
    max_posiciones_logicas: int
    apalancamiento: float
    sl_posicion_individual_pct: float
    tsl_activacion_pct: float
    tsl_distancia_pct: float


@dataclass
class Operacion:
    """
    Representa un ciclo de vida completo de trading. Contiene tanto la
    configuración de la operación como su estado dinámico en tiempo real.
    """
    id: str
    configuracion: ConfiguracionOperacion
    
    # --- Estado dinámico de la operación ---
    capital_inicial_usdt: float
    pnl_realizado_usdt: float = 0.0
    comercios_cerrados_contador: int = 0
    tiempo_inicio_ejecucion: Optional[datetime.datetime] = None
    posiciones_activas: Dict[str, List[LogicalPosition]] = field(default_factory=lambda: {'long': [], 'short': []})


# --- 2. Entidades para los Nuevos Hitos Especializados ---

@dataclass
class CondicionPrecioDosPasos:
    """
    Define la condición de activación de precio de dos pasos. El hito se "arma"
    cuando se cumple la primera condición y se "dispara" cuando se cumple la segunda.
    """
    # El valor puede ser un float o el string 'market_price'
    activacion_mayor_a: Union[float, str]
    activacion_menor_a: Union[float, str]
    
    # Estado interno de la condición
    estado_mayor_a_cumplido: bool = False
    estado_menor_a_cumplido: bool = False


@dataclass
class CondicionHito:
    """
    Contenedor para todas las posibles condiciones que pueden activar un hito.
    El tipo de hito ('INICIALIZACION' o 'FINALIZACION') determinará qué
    atributos son relevantes.
    """
    # Para Hitos de Inicialización
    condicion_precio: Optional[CondicionPrecioDosPasos] = None
    
    # Para Hitos de Finalización
    tp_roi_pct: Optional[float] = None
    sl_roi_pct: Optional[float] = None
    tiempo_maximo_min: Optional[int] = None
    max_comercios: Optional[int] = None


@dataclass
class AccionHito:
    """
    Define la acción que se ejecuta cuando un Hito se activa.
    """
    # Para Hitos de Inicialización
    configuracion_nueva_operacion: Optional[ConfiguracionOperacion] = None
    
    # Para Hitos de Finalización
    cerrar_posiciones_al_finalizar: bool = False


@dataclass
class Hito:
    """
    La nueva entidad Hito, que representa un nodo en el árbol de decisiones.
    Es agnóstica a su contenido, que está definido en CondicionHito y AccionHito.
    """
    id: str
    tipo_hito: str  # 'INICIALIZACION' o 'FINALIZACION'
    condicion: CondicionHito
    accion: AccionHito
    
    # --- Atributos de gestión del árbol (igual que antes) ---
    parent_id: Optional[str] = None
    level: int = 1
    status: str = 'PENDING'  # PENDING, ACTIVE, COMPLETED, CANCELLED
    one_shot: bool = True
    created_at: datetime.datetime = field(default_factory=datetime.datetime.now)

# --- FIN: NUEVAS ENTIDADES ---