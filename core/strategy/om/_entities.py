"""
Módulo de Entidades de Dominio para el Operation Manager (OM).

v8.0 (Capital Lógico por Operación):
- La entidad `Operacion` ahora contiene una instancia de `LogicalBalances`
  para gestionar su propio capital lógico, importada desde el paquete PM.
"""
import datetime
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List

# --- Dependencia Cruzada ---
# La Operación contiene entidades gestionadas por el Position Manager.
# Por lo tanto, importamos las entidades desde su módulo.
try:
    # --- INICIO DE LA MODIFICACIÓN ---
    # Importamos también la nueva clase LogicalBalances.
    from core.strategy.pm._entities import LogicalPosition, LogicalBalances
    # --- FIN DE LA MODIFICACIÓN ---
except ImportError:
    # Fallback para permitir análisis estático y evitar errores de importación circular
    # si los archivos se cargan en un orden inesperado.
    class LogicalPosition: pass
    # --- INICIO DE LA MODIFICACIÓN ---
    class LogicalBalances: pass
    # --- FIN DE LA MODIFICACIÓN ---

# --- Entidad de Operación Única ---

@dataclass
class Operacion:
    """
    Representa una única Operación Estratégica configurable. Contiene toda la
    lógica de estado, condiciones y parámetros de trading. Sigue un ciclo de vida
    ACTIVA <-> PAUSADA -> DETENIDA.
    """
    # --- Identificación y Estado ---
    id: str
    estado: str = 'DETENIDA'  # Valores: 'DETENIDA', 'EN_ESPERA', 'ACTIVA', 'PAUSADA'

    # --- Condición de Entrada ---
    tipo_cond_entrada: Optional[str] = 'MARKET'
    valor_cond_entrada: Optional[float] = 0.0
    
    # --- Parámetros de Trading ---
    tendencia: Optional[str] = None # Valores: 'LONG_ONLY' o 'SHORT_ONLY'
    tamaño_posicion_base_usdt: float = 1.0
    max_posiciones_logicas: int = 5
    apalancamiento: float = 10.0
    sl_posicion_individual_pct: float = 10.0
    tsl_activacion_pct: float = 0.4
    tsl_distancia_pct: float = 0.1

    # --- Condiciones de Salida (Límites) ---
    tsl_roi_activacion_pct: Optional[float] = None
    tsl_roi_distancia_pct: Optional[float] = None
    sl_roi_pct: Optional[float] = None
    tiempo_maximo_min: Optional[int] = None
    max_comercios: Optional[int] = None
    tipo_cond_salida: Optional[str] = None
    valor_cond_salida: Optional[float] = None
    accion_al_finalizar: str = 'PAUSAR'  # Valores: 'PAUSAR', 'DETENER'

    # --- Estado Dinámico ---
    capital_inicial_usdt: float = 0.0
    pnl_realizado_usdt: float = 0.0
    comercios_cerrados_contador: int = 0
    tiempo_inicio_ejecucion: Optional[datetime.datetime] = None
    posiciones_activas: Dict[str, List[LogicalPosition]] = field(default_factory=lambda: {'long': [], 'short': []})

    # Campos para el estado dinámico del TSL por ROI
    tsl_roi_activo: bool = False
    tsl_roi_peak_pct: float = 0.0
    
    # --- INICIO DE LA MODIFICACIÓN ---
    # Se añade el campo `balances` para que cada operación gestione su propio capital lógico.
    # Esta es la única adición necesaria en esta clase.
    balances: LogicalBalances = field(default_factory=LogicalBalances)
    # --- FIN DE LA MODIFICACIÓN ---