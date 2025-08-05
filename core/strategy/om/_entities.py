# ./core/strategy/om/_entities.py

"""
Módulo de Entidades de Dominio para el Operation Manager (OM).
Única fuente de verdad para las entidades 'Operacion' y 'LogicalBalances'.
"""
import datetime
from dataclasses import dataclass, field
from typing import Optional, Dict, List

# --- INICIO DE LA MODIFICACIÓN CRÍTICA ---
# Se importa LogicalPosition usando un chequeo de tipado para romper el ciclo en tiempo de ejecución.
# Esto es una técnica estándar para resolver dependencias circulares.
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from core.strategy.pm._entities import LogicalPosition

# Se mueve la definición de LogicalBalances aquí, ya que está lógicamente ligada a una Operacion.
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
# --- FIN DE LA MODIFICACIÓN CRÍTICA ---

class Operacion:
    """
    Representa una única Operación Estratégica configurable. Contiene toda la
    lógica de estado, condiciones y parámetros de trading.
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
        self.posiciones_activas: Dict[str, List['LogicalPosition']] = {'long': [], 'short': []} # Se usa como string
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