"""
Módulo del Position Manager: Ciclo de Vida.

Contiene la lógica de inicialización y configuración base de la clase PositionManager,
incluyendo el constructor y los métodos de arranque de la sesión.
"""
import datetime
import time
import copy
from typing import Optional, Dict, Any, List

# Importamos timezone para crear datetimes "aware"
from datetime import timezone

# --- Dependencias del Proyecto (inyectadas) ---
try:
    from .._entities import Milestone
    from core.exchange import AbstractExchange
except ImportError:
    class Milestone: pass
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
                 helpers: Any
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

        # --- Estado de la Sesión (Global) ---
        self._initialized: bool = False
        self._operation_mode: str = "unknown"
        self._leverage: float = 1.0
        self._max_logical_positions: int = 1
        self._initial_base_position_size_usdt: float = 0.0

        self._session_start_time: Optional[datetime.datetime] = None
        self._session_tp_hit: bool = False
        self._global_stop_loss_roi_pct: Optional[float] = None
        self._global_take_profit_roi_pct: Optional[float] = None
        
        # --- Estado de PNL ---
        self._total_realized_pnl_long: float = 0.0
        self._total_realized_pnl_short: float = 0.0

        # --- Estado del Árbol de Decisiones ---
        self._milestones: List[Milestone] = []
        
        # --- Modelo de Estado basado en Tendencia Activa ---
        # Si _active_trend es None, el bot está en modo NEUTRAL.
        self._active_trend: Optional[Dict[str, Any]] = None

    def set_executor(self, executor: Any):
        """Inyecta el executor después de la inicialización para romper la dependencia circular."""
        self._executor = executor
        
    def initialize(self, operation_mode: str, base_size: float, max_pos: int):
        """Inicializa el PM para una nueva sesión."""
        self._reset_all_states()
        self._operation_mode = operation_mode
        self._leverage = getattr(self._config, 'POSITION_LEVERAGE', 1.0)
        self._max_logical_positions = max_pos
        self._initial_base_position_size_usdt = base_size
        # Se crea el timestamp de inicio de sesión como "aware" en UTC.
        self._session_start_time = datetime.datetime.now(timezone.utc)
        
        # Límites globales de la sesión (disyuntores)
        self._global_stop_loss_roi_pct = getattr(self._config, 'SESSION_STOP_LOSS_ROI_PCT', 0.0)
        self._global_take_profit_roi_pct = getattr(self._config, 'SESSION_TAKE_PROFIT_ROI_PCT', 0.0)

        self._balance_manager.set_state_manager(self)
        self._position_state.initialize(is_live_mode=True)
        
        self._initialized = True
        self._memory_logger.log("PositionManager inicializado bajo el nuevo modelo de Hitos/Tendencias.", level="INFO")