"""
Módulo del PositionState.

Define la clase PositionState, responsable de almacenar y gestionar el estado
de las posiciones lógicas (delegado a instancias de LogicalPositionTable) y
físicas (agregadas) para ambos lados (long y short).

v2.1 (Exchange Agnostic Refactor):
- Elimina la dependencia de `live_operations`.
- Pasa el `exchange_adapter` a las `LogicalPositionTable` que instancia.
"""
import datetime
import copy
import traceback
from typing import List, Dict, Optional, Any

# --- Dependencias del Proyecto ---
try:
    from ._logical_table import LogicalPositionTable
    from ._entities import LogicalPosition, PhysicalPosition
    from core.exchange import AbstractExchange
except ImportError:
    # Fallbacks
    class LogicalPositionTable: pass
    class LogicalPosition: pass
    class PhysicalPosition: pass
    class AbstractExchange: pass


class PositionState:
    """Gestiona el estado de las posiciones lógicas y físicas."""

    def __init__(self,
                 config: Any,
                 utils: Any,
                 exchange_adapter: AbstractExchange # <-- CAMBIO CLAVE
                 ):
        """
        Inicializa el gestor de estado de posiciones.
        """
        # Inyección de dependencias
        self._config = config
        self._utils = utils
        self._exchange = exchange_adapter # <-- CAMBIO CLAVE
        
        # Atributos de estado de la instancia
        self._initialized: bool = False
        self._long_table: Optional[LogicalPositionTable] = None
        self._short_table: Optional[LogicalPositionTable] = None
        self.physical_long_position: PhysicalPosition = PhysicalPosition()
        self.physical_short_position: PhysicalPosition = PhysicalPosition()

    def initialize(self, is_live_mode: bool):
        """
        Inicializa o resetea el estado para una nueva sesión.
        Crea las instancias de LogicalPositionTable.
        """
        print("[Position State] Inicializando estado...")
        self._initialized = False

        # Resetear estado físico
        self.reset_physical_position_state('long')
        self.reset_physical_position_state('short')

        # Validar dependencias para las tablas lógicas
        if not all([self._config, self._utils, self._exchange, LogicalPositionTable]):
            print("ERROR CRITICO [PS Init]: Faltan dependencias para LogicalPositionTable.")
            return

        try:
            # Crear instancias de las tablas lógicas, inyectando el adaptador de exchange
            self._long_table = LogicalPositionTable(
                side='long',
                is_live_mode=is_live_mode,
                config_param=self._config,
                utils=self._utils,
                exchange_adapter=self._exchange if is_live_mode else None # <-- CAMBIO CLAVE
            )
            self._short_table = LogicalPositionTable(
                side='short',
                is_live_mode=is_live_mode,
                config_param=self._config,
                utils=self._utils,
                exchange_adapter=self._exchange if is_live_mode else None # <-- CAMBIO CLAVE
            )
            self._initialized = True
            print("[Position State] Estado y Tablas Lógicas inicializados.")

        except Exception as e:
            print(f"ERROR CRITICO [PS Init]: Falló la inicialización de LogicalPositionTable: {e}")
            traceback.print_exc()
            self._initialized = False

    def _get_table_for_side(self, side: str) -> Optional[LogicalPositionTable]:
        """Método auxiliar para obtener la tabla correcta."""
        if side == 'long':
            return self._long_table
        elif side == 'short':
            return self._short_table
        return None

    # --- Métodos para Posiciones Lógicas (Sin cambios en su lógica interna) ---
    
    def add_logical_position(self, side: str, position_data: Dict[str, Any]) -> bool:
        """Añade una nueva posición lógica a la tabla correspondiente."""
        if not self._initialized: return False
        table = self._get_table_for_side(side)
        return table.add_position(position_data) if table else False

    def remove_logical_position(self, side: str, index: int) -> Optional[Dict[str, Any]]:
        """Elimina una posición lógica por índice."""
        if not self._initialized: return None
        table = self._get_table_for_side(side)
        return table.remove_position_by_index(index) if table else None

    def get_open_logical_positions(self, side: str) -> List[Dict[str, Any]]:
        """Devuelve una copia de las posiciones lógicas abiertas."""
        if not self._initialized: return []
        table = self._get_table_for_side(side)
        return table.get_positions() if table else []
        
    def update_logical_position_details(self, side: str, position_id: str, details_to_update: Dict[str, Any]) -> bool:
        """Actualiza detalles de una posición lógica específica."""
        if not self._initialized: return False
        table = self._get_table_for_side(side)
        return table.update_position_details(position_id, details_to_update) if table else False

    def display_logical_table(self, side: str):
        """Solicita a la tabla lógica que imprima su estado."""
        if not self._initialized: return
        table = self._get_table_for_side(side)
        if table:
            table.display_table()

    # --- Métodos para Posiciones Físicas (Sin cambios en su lógica interna) ---

    def get_physical_position_state(self, side: str) -> Dict[str, Any]:
        """Devuelve una copia del estado físico en formato de diccionario."""
        if not self._initialized: return {}
        
        target_physical: PhysicalPosition = self.physical_long_position if side == 'long' else self.physical_short_position
        
        # Convertir dataclass a diccionario para mantener la compatibilidad con la TUI
        from dataclasses import asdict
        state_dict = asdict(target_physical)
        
        # Formatear el timestamp para la visualización
        ts = state_dict.get('last_update_ts')
        if self._utils and ts and isinstance(ts, datetime.datetime):
            state_dict['last_update_ts'] = self._utils.format_datetime(ts)
        elif ts is not None:
            state_dict['last_update_ts'] = str(ts)
            
        return state_dict

    def update_physical_position_state(
        self,
        side: str,
        avg_price: float,
        total_size: float,
        total_margin: float,
        liq_price: Optional[float],
        timestamp: datetime.datetime
    ):
        """Actualiza el estado de la posición física."""
        if not self._initialized: return
        
        target_physical = self.physical_long_position if side == 'long' else self.physical_short_position
        
        target_physical.avg_entry_price = self._utils.safe_float_convert(avg_price, 0.0)
        target_physical.total_size_contracts = self._utils.safe_float_convert(total_size, 0.0)
        target_physical.total_margin_usdt = self._utils.safe_float_convert(total_margin, 0.0)
        target_physical.est_liq_price = self._utils.safe_float_convert(liq_price)
        target_physical.last_update_ts = timestamp

    def reset_physical_position_state(self, side: str):
        """Resetea el estado físico a sus valores por defecto."""
        if side == 'long':
            self.physical_long_position = PhysicalPosition()
        elif side == 'short':
            self.physical_short_position = PhysicalPosition()