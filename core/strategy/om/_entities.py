# ./core/strategy/om/_entities.py

"""
Módulo de Entidades de Dominio para el Operation Manager (OM).
Única fuente de verdad para la entidad 'Operacion'.
"""
import datetime
from dataclasses import field
from typing import Optional, Dict, Any, List

# --- INICIO DE LA MODIFICACIÓN CRÍTICA ---
# La Operación DEPENDE de entidades del PM, por lo que las importa directamente.
# Se separa cada importación en su propio try-except para un mejor diagnóstico de errores.
try:
    from core.strategy.pm._entities import LogicalPosition
except ImportError:
    print("ERROR CRÍTICO: No se pudo importar 'LogicalPosition' en 'om._entities'.")
    LogicalPosition = None # Forzar un error diferente si esto falla

try:
    from core.strategy.pm._entities import LogicalBalances
except ImportError:
    print("ERROR CRÍTICO: No se pudo importar 'LogicalBalances' en 'om._entities'.")
    LogicalBalances = None # Forzar un error diferente si esto falla
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
        self.posiciones_activas: Dict[str, List[LogicalPosition]] = {'long': [], 'short': []}
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