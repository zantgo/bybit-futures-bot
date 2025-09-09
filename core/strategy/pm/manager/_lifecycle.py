# core/strategy/pm/manager/_lifecycle.py

import datetime
import time
import copy
from typing import Optional, Dict, Any, List
import uuid

from datetime import timezone

try:
    # --- INICIO DE LA MODIFICACIÓN ---
    from core.strategy.entities import Operacion, LogicalPosition
    # --- FIN DE LA MODIFICACIÓN ---
    from core.exchange import AbstractExchange
except ImportError:
    class Operacion: pass
    class AbstractExchange: pass

class _LifecycleManager:
    """Clase base que gestiona el ciclo de vida del PositionManager."""

    # Reemplaza la función __init__ completa en _lifecycle.py
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
        self._total_realized_pnl_long: float = 0.0
        self._total_realized_pnl_short: float = 0.0
        # --- INICIO DE LA SOLUCIÓN: Añadir la bandera de estado ---
        self._manual_close_in_progress: bool = False
        # --- FIN DE LA SOLUCIÓN ---
        
        # --- INICIO DE LA CORRECCIÓN: Añadir contadores de fallos de sincronización ---
        self._sync_failure_counters: Dict[str, int] = {'long': 0, 'short': 0}
        self._MAX_SYNC_FAILURES: int = 3 # Umbral de fallos consecutivos antes de tomar acción
        # --- FIN DE LA CORRECCIÓN ---


    # Reemplaza la función _reset_all_states completa en _lifecycle.py
    def _reset_all_states(self):
        """Resetea todos los atributos de estado del manager a sus valores iniciales."""
        self._initialized = False
        self._operation_mode = "unknown"
        self._total_realized_pnl_long = 0.0
        self._total_realized_pnl_short = 0.0
        self._session_start_time = None
        # --- INICIO DE LA SOLUCIÓN: Resetear la bandera en cada nueva sesión ---
        self._manual_close_in_progress = False
        # --- FIN DE LA SOLUCIÓN ---
        
        # --- INICIO DE LA CORRECCIÓN: Resetear contadores de fallos ---
        self._sync_failure_counters = {'long': 0, 'short': 0}
        # --- FIN DE LA CORRECCIÓN ---
        
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
     
        self._position_state.initialize(is_live_mode=True)
        self._initialized = True
        self._memory_logger.log("PositionManager inicializado. Gestionando estado de posiciones.", level="INFO")