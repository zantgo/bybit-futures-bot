"""
Módulo del Position Manager: Ciclo de Vida.

v8.0 (Capital Lógico por Operación):
- Se elimina la dependencia del `balance_manager` en el constructor.
- El método `initialize` se simplifica, ya que la lógica de capital ahora
  reside en las entidades `Operacion`.
"""
# (COMENTARIO) Docstring de la versión anterior (v7.0) para referencia:
# """
# Módulo del Position Manager: Ciclo de Vida.
# 
# v7.0 (Desacoplamiento Final):
# - Se actualiza la firma del método `initialize` para eliminar los parámetros
#   `base_size` y `max_pos`, completando el desacoplamiento de la lógica de la
#   Operación y solucionando el `TypeError` de inicialización.
# - El PM ahora se inicializa con el `operation_mode` y recibe la API del OM
#   como una dependencia a través del constructor.
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
                 # --- INICIO DE LA MODIFICACIÓN ---
                 # Se elimina el parámetro `balance_manager` del constructor.
                 # balance_manager: Any,
                 # --- FIN DE LA MODIFICACIÓN ---
                 position_state: Any,
                 exchange_adapter: AbstractExchange,
                 config: Any,
                 utils: Any,
                 memory_logger: Any,
                 helpers: Any,
                 operation_manager_api: Any
                 ):
        # --- Inyección de Dependencias ---
        # --- INICIO DE LA MODIFICACIÓN ---
        # Se comenta la asignación del balance_manager.
        # self._balance_manager = balance_manager
        # --- FIN DE LA MODIFICACIÓN ---
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
        Ya no es responsable de gestionar el capital.
        """
        self._reset_all_states()
        self._operation_mode = operation_mode
    
        self._session_start_time = datetime.datetime.now(timezone.utc)
        
        self._global_stop_loss_roi_pct = getattr(self._config, 'SESSION_STOP_LOSS_ROI_PCT', 0.0)
        self._global_take_profit_roi_pct = getattr(self._config, 'SESSION_TAKE_PROFIT_ROI_PCT', 0.0)

        # --- INICIO DE LA MODIFICACIÓN ---
        # Se elimina la configuración del state manager en el balance_manager, ya que no existe.
        # self._balance_manager.set_state_manager(self)
        # --- FIN DE LA MODIFICACIÓN ---
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