"""
Módulo de Entidades de Dominio para el Position Manager.

v7.0 (Capital Lógico por Operación):
- Se añade la dataclass `LogicalBalances` para encapsular la gestión de capital
  a nivel de una única Operación, eliminando la necesidad de un BalanceManager global.
- La entidad `Operacion` ahora contiene una instancia de `LogicalBalances`.
- Se reemplaza el TP por ROI estático con un TSL por ROI dinámico para las operaciones.
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

# --- INICIO DE LA MODIFICACIÓN ---

@dataclass
class LogicalBalances:
    """
    Encapsula y gestiona el capital lógico para una única operación.
    Esta clase reemplaza la lógica del BalanceManager global.
    """
    operational_margin: float = 0.0
    used_margin: float = 0.0
    profit_balance: float = 0.0 # Beneficios netos transferidos fuera de esta operación

    @property
    def available_margin(self) -> float:
        """Calcula el margen disponible para nuevas posiciones."""
        return max(0.0, self.operational_margin - self.used_margin)

    def decrease_available_margin(self, amount: float):
        """Incrementa el margen usado, reduciendo el disponible. Llamado al abrir una posición."""
        if isinstance(amount, (int, float)) and amount > 0:
            self.used_margin += abs(amount)

    def increase_available_margin(self, amount: float):
        """Disminuye el margen usado, liberando capital. Llamado al cerrar una posición."""
        if isinstance(amount, (int, float)) and amount > 0:
            self.used_margin = max(0.0, self.used_margin - abs(amount))
            
    def record_profit_transfer(self, amount_transferred: float):
        """Registra un beneficio que ha sido lógicamente 'retirado' de esta operación."""
        if isinstance(amount_transferred, (int, float)) and amount_transferred > 0:
            self.profit_balance += amount_transferred

# @dataclass
# class Balances:
#     """ (OBSOLETO) Encapsulaba los balances lógicos de las cuentas operativas y de beneficios.
#     Esta clase se ha reemplazado por `LogicalBalances` que se adjunta a cada `Operacion`.
#     """
#     operational_long: float = 0.0
#     operational_short: float = 0.0
#     used_long: float = 0.0
#     used_short: float = 0.0
#     profit: float = 0.0
    
#     @property
#     def available_long(self) -> float:
#         """Calcula el margen disponible para nuevas posiciones largas."""
#         return max(0.0, self.operational_long - self.used_long)
        
#     @property
#     def available_short(self) -> float:
#         """Calcula el margen disponible para nuevas posiciones cortas."""
#         return max(0.0, self.operational_short - self.used_short)

# --- FIN DE LA MODIFICACIÓN ---


# --- Entidad de Operación Única ---

@dataclass
class Operacion:
    """
    Representa una única Operación Estratégica configurable. Contiene toda la
    lógica de estado, condiciones y parámetros de trading.
    """
    # Identificación y Estado
    id: str
    estado: str = 'DETENIDA'  # Valores: 'DETENIDA', 'EN_ESPERA', 'ACTIVA', 'PAUSADA'

    # Condición de Entrada
    tipo_cond_entrada: Optional[str] = 'MARKET'
    valor_cond_entrada: Optional[float] = 0.0

    # Parámetros de Trading
    tendencia: Optional[str] = None # 'LONG_ONLY' o 'SHORT_ONLY'
    tamaño_posicion_base_usdt: float = 1.0
    max_posiciones_logicas: int = 5
    apalancamiento: float = 10.0
    sl_posicion_individual_pct: float = 10.0
    tsl_activacion_pct: float = 0.4
    tsl_distancia_pct: float = 0.1

    # --- INICIO DE LA MODIFICACIÓN ---
    # Condiciones de Salida (Límites de la Operación)
    # Se reemplaza el tp_roi_pct estático por un TSL por ROI dinámico.
    # tp_roi_pct: Optional[float] = None
    tsl_roi_activacion_pct: Optional[float] = None
    tsl_roi_distancia_pct: Optional[float] = None
    sl_roi_pct: Optional[float] = None
    tiempo_maximo_min: Optional[int] = None
    max_comercios: Optional[int] = None
    tipo_cond_salida: Optional[str] = None # 'PRICE_ABOVE', 'PRICE_BELOW'
    valor_cond_salida: Optional[float] = None
    accion_al_finalizar: str = 'PAUSAR'  # 'PAUSAR' o 'DETENER'
    
    # Estado Dinámico
    capital_inicial_usdt: float = 0.0
    pnl_realizado_usdt: float = 0.0
    comercios_cerrados_contador: int = 0
    tiempo_inicio_ejecucion: Optional[datetime.datetime] = None
    posiciones_activas: Dict[str, List[LogicalPosition]] = field(default_factory=lambda: {'long': [], 'short': []})

    # Nuevos campos para el estado dinámico del TSL por ROI
    tsl_roi_activo: bool = False
    tsl_roi_peak_pct: float = 0.0
    
    # Cada operación ahora es dueña de su propio gestor de balance lógico.
    balances: LogicalBalances = field(default_factory=LogicalBalances)
    # --- FIN DE LA MODIFICACIÓN ---