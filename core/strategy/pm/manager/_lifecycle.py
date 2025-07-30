"""
Módulo del Position Manager: Ciclo de Vida.

v7.0 (Desacoplamiento Final):
- Se actualiza la firma del método `initialize` para eliminar los parámetros
  `base_size` y `max_pos`, completando el desacoplamiento de la lógica de la
  Operación y solucionando el `TypeError` de inicialización.
- El PM ahora se inicializa con el `operation_mode` y recibe la API del OM
  como una dependencia a través del constructor.
"""
# (COMENTARIO) Docstring de la versión anterior (v6.0) para referencia:
# """
# Módulo del Position Manager: Ciclo de Vida.
# 
# v6.0 (Modelo de Operación Única):
# - El ciclo de vida ahora se centra en la inicialización de una única
#   `Operacion` estratégica en estado NEUTRAL y EN_ESPERA.
# - Se elimina por completo la gestión de la lista de Hitos.
# """
import datetime
import time
import copy
from typing import Optional, Dict, Any, List
import uuid

from datetime import timezone

# --- Dependencias del Proyecto (inyectadas) ---
try:
    from .._entities import Operacion # A pesar de que ya no la crea, la importa para el type hinting
    from core.exchange import AbstractExchange
except ImportError:
    class Operacion: pass
    class AbstractExchange: pass

class _LifecycleManager:
    """Clase base que gestiona el ciclo de vida del PositionManager."""
    def __init__(self,
                 balance_manager: Any,
                 position_state: Any,
                 exchange_adapter: AbstractExchange,
                 config: Any,
                 utils: Any,
                 memory_logger: Any,
                 helpers: Any,
                 operation_manager_api: Any
                 ):
        # --- Inyección de Dependencias ---
        self._balance_manager = balance_manager
        self._position_state = position_state
        self._executor: Optional[Any] = None
        self._exchange = exchange_adapter
        self._config = config
        self._utils = utils
        self._memory_logger = memory_logger
        self._helpers = helpers
        self._om_api = operation_manager_api

        # --- Estado de la Sesión (Global) ---
        self._initialized: bool = False
        self._operation_mode: str = "unknown"
        self._session_start_time: Optional[datetime.datetime] = None
        self._session_tp_hit: bool = False
        self._global_stop_loss_roi_pct: Optional[float] = None
        self._global_take_profit_roi_pct: Optional[float] = None
        
        # --- Estado de PNL (Global de la sesión) ---
        self._total_realized_pnl_long: float = 0.0
        self._total_realized_pnl_short: float = 0.0


    def set_executor(self, executor: Any):
        """Inyecta el executor después de la inicialización para romper la dependencia circular."""
        self._executor = executor
        
    def initialize(self, operation_mode: str):
        """
        Inicializa el estado del PositionManager para una nueva sesión.
        Ya no es responsable de crear la operación inicial.
        """
        # (COMENTARIO) Firma anterior para referencia histórica.
        # def initialize(self, operation_mode: str, base_size: float, max_pos: int):
        
        self._reset_all_states()
        self._operation_mode = operation_mode
    
        self._session_start_time = datetime.datetime.now(timezone.utc)
        
        self._global_stop_loss_roi_pct = getattr(self._config, 'SESSION_STOP_LOSS_ROI_PCT', 0.0)
        self._global_take_profit_roi_pct = getattr(self._config, 'SESSION_TAKE_PROFIT_ROI_PCT', 0.0)

        self._balance_manager.set_state_manager(self)
        self._position_state.initialize(is_live_mode=True)
        
        self._initialized = True
        self._memory_logger.log("PositionManager inicializado. Gestionando estado de posiciones.", level="INFO")

    def _reset_all_states(self):
        """Resetea todos los atributos de estado del manager a sus valores iniciales."""
        self._initialized = False
        self._operation_mode = "unknown"
        self._total_realized_pnl_long = 0.0
        self._total_realized_pnl_short = 0.0
        self._session_tp_hit = False
        self._session_start_time = None
        self._global_stop_loss_roi_pct = None
        self._global_take_profit_roi_pct = None