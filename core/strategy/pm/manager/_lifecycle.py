# ./core/strategy/pm/manager/_lifecycle.py
import datetime
import time
import copy
from typing import Optional, Dict, Any, List
import uuid

from datetime import timezone

try:
    from .._entities import Operacion
    from core.exchange import AbstractExchange
except ImportError:
    class Operacion: pass
    class AbstractExchange: pass

class _LifecycleManager:
    """Clase base que gestiona el ciclo de vida del PositionManager."""
    def __init__(self,
                 position_state: Any,
                 exchange_adapter: AbstractExchange,
                 config: Any,
                 utils: Any,
                 memory_logger: Any,
                 helpers: Any,
                 operation_manager_api: Any
                 ):
        self._position_state = position_state
        self._executor: Optional[Any] = None
        self._exchange = exchange_adapter
        self._config = config
        self._utils = utils
        self._memory_logger = memory_logger
        self._helpers = helpers
        self._om_api = operation_manager_api
        self._initialized: bool = False
        self._operation_mode: str = "unknown"
        self._session_start_time: Optional[datetime.datetime] = None
        self._session_tp_hit: bool = False
        self._global_stop_loss_roi_pct: Optional[float] = None
        self._global_take_profit_roi_pct: Optional[float] = None
        self._total_realized_pnl_long: float = 0.0
        self._total_realized_pnl_short: float = 0.0

    def set_executor(self, executor: Any):
        """Inyecta el executor después de la inicialización para romper la dependencia circular."""
        self._executor = executor
        
    def initialize(self, operation_mode: str):
        """
        Inicializa el estado del PositionManager para una nueva sesión.
        """
        self._reset_all_states()
        self._operation_mode = operation_mode
        self._session_start_time = datetime.datetime.now(timezone.utc)
        
        # --- INICIO DE LA CORRECCIÓN ---
        session_limits = self._config.SESSION_CONFIG["SESSION_LIMITS"]
        self._global_stop_loss_roi_pct = session_limits["ROI_SL"]["PERCENTAGE"] if session_limits["ROI_SL"]["ENABLED"] else 0.0
        self._global_take_profit_roi_pct = session_limits["ROI_TP"]["PERCENTAGE"] if session_limits["ROI_TP"]["ENABLED"] else 0.0
        # --- FIN DE LA CORRECCIÓN ---

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