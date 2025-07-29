"""
Módulo de Entidades de Dominio para el Operation Manager (OM).

Define las estructuras de datos clave que el OM gestiona, principalmente la
entidad `Operacion`, que representa una estrategia de trading completa desde
su concepción hasta su finalización.
"""
import datetime
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List

# --- Dependencia Cruzada ---
# La Operación contiene una lista de Posiciones Lógicas, que son gestionadas
# por el Position Manager. Por lo tanto, importamos la entidad desde su módulo.
try:
    from core.strategy.pm._entities import LogicalPosition
except ImportError:
    # Fallback para permitir análisis estático y evitar errores de importación circular
    # si los archivos se cargan en un orden inesperado.
    class LogicalPosition: pass

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
    
    # Nueva Condición de Salida por Precio
    tipo_cond_salida: Optional[str] = None # 'PRICE_ABOVE', 'PRICE_BELOW'
    valor_cond_salida: Optional[float] = None
    
    # Estado Dinámico
    capital_inicial_usdt: float = 0.0
    pnl_realizado_usdt: float = 0.0
    comercios_cerrados_contador: int = 0
    tiempo_inicio_ejecucion: Optional[datetime.datetime] = None
    posiciones_activas: Dict[str, List[LogicalPosition]] = field(default_factory=lambda: {'long': [], 'short': []})