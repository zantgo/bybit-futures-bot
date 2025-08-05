# ./core/strategy/pm/logical_position_table.py

"""
Módulo que define la clase LogicalPositionTable para gestionar una lista de
posiciones lógicas abiertas para un lado específico (long/short).

v2.2 (Sincronización):
- Añadido el método `sync_positions` para permitir la sobrescritura completa
  del estado de la tabla, necesario para la transición entre Operaciones.
- Mejorado el tipado interno para usar la entidad `LogicalPosition`.
"""
import datetime
import traceback
import copy
import threading
from typing import Optional, Dict, Any, List, Union, TYPE_CHECKING
import pandas as pd

# --- Dependencias (se inyectan en __init__) ---
try:
    from core.exchange import AbstractExchange
    from core.logging import memory_logger
    # Importar la entidad específica para un tipado más fuerte
    from ._entities import LogicalPosition
except ImportError:
    class AbstractExchange: pass
    class LogicalPosition: pass # Fallback
    class MemoryLoggerFallback:
        def log(self, msg, level="INFO"): print(f"[{level}] {msg}")
    memory_logger = MemoryLoggerFallback()

if TYPE_CHECKING:
    import config as cfg_mod
    from core import utils as ut_mod
    
    class ConfigFallback:
        LOG_LEVEL = "INFO"
        PRICE_PRECISION = 4
        DEFAULT_QTY_PRECISION = 3
    config = ConfigFallback()

class LogicalPositionTable:
    """
    Gestiona una tabla (lista) de posiciones lógicas para un lado (long/short).
    Esta clase es thread-safe.
    """
    def __init__(self,
                 side: str,
                 is_live_mode: bool,
                 config_param: Optional[Any] = None,
                 utils: Optional[Any] = None,
                 exchange_adapter: Optional[AbstractExchange] = None
                 ):
        """
        Inicializa la tabla de posiciones lógicas.
        """
        if side not in ['long', 'short']: raise ValueError(f"Lado inválido '{side}'.")
        if is_live_mode and not exchange_adapter: 
            memory_logger.log(f"WARN [LPT Init {side}]: Modo Live pero exchange_adapter no fue proporcionado.", level="WARN")

        self.side = side
        self.is_live_mode = is_live_mode
        self._config_param = config_param
        self._utils = utils
        self._exchange = exchange_adapter
        self._positions: List[LogicalPosition] = []
        self._lock = threading.Lock()

        memory_logger.log(f"[LPT {self.side.upper()}] Tabla inicializada. Modo Live: {self.is_live_mode}", level="INFO")

    def sync_positions(self, new_positions: List[LogicalPosition]):
        """
        Sobrescribe completamente la lista interna de posiciones con una nueva lista.
        Este método es crucial para sincronizar el estado después de una transición de Operación.
        """
        if not isinstance(new_positions, list):
            memory_logger.log(f"ERROR [LPT Sync {self.side.upper()}]: El dato proporcionado no es una lista.", level="ERROR")
            return
        
        with self._lock:
            # Se usa deepcopy para asegurar que la tabla tenga su propia copia de los objetos
            self._positions = copy.deepcopy(new_positions)
        
        memory_logger.log(f"[LPT Sync {self.side.upper()}]: Tabla sincronizada con {len(new_positions)} posiciones.", level="DEBUG")

    # --- Métodos de Gestión Básica (con tipado mejorado) ---
    def add_position(self, position_data: LogicalPosition) -> bool:
        """Añade un objeto LogicalPosition a la tabla."""
        if not isinstance(position_data, LogicalPosition): 
            memory_logger.log(f"ERROR [LPT {self.side.upper()} Add]: El dato no es un objeto LogicalPosition válido.", level="ERROR"); return False
        
        with self._lock:
            self._positions.append(copy.deepcopy(position_data))
        
        return True

    def remove_position_by_index(self, index: int) -> Optional[LogicalPosition]:
        """Elimina una posición por su índice y la devuelve."""
        try:
            with self._lock:
                if 0 <= index < len(self._positions):
                    removed_position = self._positions.pop(index)
                    return copy.deepcopy(removed_position)
            
            memory_logger.log(f"ERROR [LPT {self.side.upper()} Remove Idx]: Índice {index} fuera de rango.", level="ERROR")
            return None
            
        except Exception as e:
            memory_logger.log(f"ERROR [LPT {self.side.upper()} Remove Idx]: Excepción {index}: {e}", level="ERROR")
            memory_logger.log(traceback.format_exc(), level="ERROR")
            return None

    def remove_position_by_id(self, position_id: str) -> Optional[LogicalPosition]:
        """Elimina una posición por su ID y la devuelve."""
        with self._lock:
            index_to_remove = -1
            for i, pos in enumerate(self._positions):
                if pos.id == position_id: 
                    index_to_remove = i
                    break
        
        if index_to_remove != -1: 
            return self.remove_position_by_index(index_to_remove)
        else: 
            memory_logger.log(f"WARN [LPT {self.side.upper()} Remove ID]: ID {position_id} no encontrado.", level="WARN")
            return None

    def update_position_details(self, position_id: str, details_to_update: Dict[str, Any]) -> bool:
        """Actualiza atributos de una posición existente por su ID."""
        if not isinstance(details_to_update, dict): 
            memory_logger.log(f"ERROR [LPT {self.side.upper()} Update]: details no es dict.", level="ERROR"); return False
        
        found = False
        with self._lock:
            for pos in self._positions:
                if pos.id == position_id:
                    try:
                        for key, value in details_to_update.items():
                            if hasattr(pos, key):
                                setattr(pos, key, value)
                        found = True
                        break
                    except Exception as e:
                        memory_logger.log(f"ERROR [LPT {self.side.upper()} Update]: Excepción ID {position_id}: {e}", level="ERROR")
                        memory_logger.log(traceback.format_exc(), level="ERROR")
                        return False

        if not found: 
            memory_logger.log(f"WARN [LPT {self.side.upper()} Update]: ID {position_id} no encontrado para actualizar.", level="WARN")
        return found

    # --- Métodos de Acceso y Cálculo ---
    def get_positions(self) -> List[LogicalPosition]:
        """Devuelve una copia de la lista de objetos LogicalPosition."""
        with self._lock:
            return copy.deepcopy(self._positions)

    def get_position_by_id(self, position_id: str) -> Optional[LogicalPosition]:
        """Busca y devuelve una copia de una posición por su ID."""
        with self._lock:
            for pos in self._positions:
                if pos.id == position_id: 
                    return copy.deepcopy(pos)
        return None

    def get_position_by_index(self, index: int) -> Optional[LogicalPosition]:
        """Obtiene una copia de una posición por su índice."""
        try:
            with self._lock:
                if 0 <= index < len(self._positions): 
                    return copy.deepcopy(self._positions[index])
            
            memory_logger.log(f"WARN [LPT {self.side.upper()} Get Idx]: Índice {index} fuera de rango.", level="WARN")
            return None
        except Exception as e: 
            memory_logger.log(f"ERROR [LPT {self.side.upper()} Get Idx]: Excepción {index}: {e}", level="ERROR")
            return None

    def get_count(self) -> int:
        with self._lock:
            return len(self._positions)

    def get_total_size(self) -> float:
        if not self._utils: return 0.0
        with self._lock:
            positions_copy = copy.deepcopy(self._positions)
        
        total_size = sum(pos.size_contracts for pos in positions_copy)
        return total_size

    def get_total_used_margin(self) -> float:
        if not self._utils: return 0.0
        with self._lock:
            positions_copy = copy.deepcopy(self._positions)
            
        total_margin = sum(pos.margin_usdt for pos in positions_copy)
        return total_margin

    def get_average_entry_price(self) -> float:
        if not self._utils: return 0.0
        with self._lock:
            positions_copy = copy.deepcopy(self._positions)
            
        if not positions_copy: return 0.0
        
        total_value = sum(pos.size_contracts * pos.entry_price for pos in positions_copy)
        total_size = sum(pos.size_contracts for pos in positions_copy)
        
        return self._utils.safe_division(total_value, total_size, default=0.0)

    # --- INICIO DE LA MODIFICACIÓN: `display_table` actualizada ---
    def display_table(self):
        """Muestra una representación en tabla de las posiciones, incluyendo todas las propiedades relevantes."""
        from dataclasses import asdict
        with self._lock:
            positions_copy = self.get_positions() # Usa el método que ya devuelve una copia
            positions_count = len(positions_copy)

        if positions_count == 0:
            return
        
        price_prec = getattr(self._config_param, 'PRICE_PRECISION', 4)
        qty_prec = getattr(self._config_param, 'DEFAULT_QTY_PRECISION', 3)

        data_for_df = []
        columns = [
            'ID', 'Entry Time', 'Entry Price', 'Size', 'Margin', 'Leverage', 
            'Stop Loss', 'TP Act. (Price)', 'TS Status'
        ]
        
        for pos in positions_copy:
            entry_ts = pos.entry_timestamp
            entry_ts_str = self._utils.format_datetime(entry_ts, '%H:%M:%S') if self._utils and entry_ts else "N/A"
            
            # Calcular el precio de activación del Take Profit (Trailing Stop)
            tp_activation_price = 'N/A'
            if pos.tsl_activation_pct_at_open > 0:
                if self.side == 'long':
                    price = pos.entry_price * (1 + pos.tsl_activation_pct_at_open / 100)
                else: # short
                    price = pos.entry_price * (1 - pos.tsl_activation_pct_at_open / 100)
                tp_activation_price = f"{price:.{price_prec}f}"
            
            # Determinar el estado del Trailing Stop
            ts_status = "Inactivo"
            if pos.ts_is_active:
                if pos.ts_stop_price:
                    ts_status = f"Activo @ {pos.ts_stop_price:.{price_prec}f}"
                else:
                    ts_status = "Activo (Calculando)"

            data_for_df.append({
                'ID': str(pos.id)[-6:], 
                'Entry Time': entry_ts_str,
                'Entry Price': f"{pos.entry_price:.{price_prec}f}",
                'Size': f"{pos.size_contracts:.{qty_prec}f}",
                'Margin': f"{pos.margin_usdt:.2f}",
                'Leverage': f"{pos.leverage:.1f}x",
                'Stop Loss': f"{pos.stop_loss_price:.{price_prec}f}" if pos.stop_loss_price else 'N/A',
                'TP Act. (Price)': tp_activation_price,
                'TS Status': ts_status
            })
            
        try:
             df = pd.DataFrame(data_for_df, columns=columns)
             print(f"\n--- Tabla Posiciones Lógicas {self.side.upper()} (Total: {positions_count}) ---")
             if not df.empty:
                 table_string = df.to_string(index=False, justify='right')
                 print(table_string)
                 print("-" * (len(table_string.split('\n')[0]) if table_string else 60))
             else: 
                 print("(Tabla vacía)")
                 print("-" * 60)
        except Exception as e_df: 
            memory_logger.log(f"ERROR [LPT Display]: Creando DataFrame: {e_df}", level="ERROR")
            print("-" * 60)
    # --- FIN DE LA MODIFICACIÓN ---