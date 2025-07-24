"""
Módulo que define la clase LogicalPositionTable para gestionar una lista de
posiciones lógicas abiertas para un lado específico (long/short).

v2.0 (Exchange Agnostic Refactor):
- Se reemplaza la dependencia de `live_operations` por `exchange_adapter`.
"""
import datetime
import traceback
import copy
import time
from typing import Optional, Dict, Any, List, Tuple, Union, TYPE_CHECKING
import pandas as pd

# --- Dependencias (se inyectan en __init__) ---
try:
    from core.exchange import AbstractExchange
except ImportError:
    class AbstractExchange: pass

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
    """
    def __init__(self,
                 side: str,
                 is_live_mode: bool,
                 config_param: Optional[Any] = None,
                 utils: Optional[Any] = None,
                 exchange_adapter: Optional[AbstractExchange] = None # <-- CAMBIO CLAVE
                 ):
        """
        Inicializa la tabla de posiciones lógicas.
        """
        if side not in ['long', 'short']: raise ValueError(f"Lado inválido '{side}'.")
        if is_live_mode and not exchange_adapter: 
            print(f"WARN [LPT Init {side}]: Modo Live pero exchange_adapter no fue proporcionado.")

        self.side = side
        self.is_live_mode = is_live_mode
        self._config_param = config_param
        self._utils = utils
        self._exchange = exchange_adapter # <-- CAMBIO CLAVE
        self._positions: List[Dict[str, Any]] = []

        print(f"[LPT {self.side.upper()}] Tabla inicializada. Modo Live: {self.is_live_mode}")

    # --- Métodos de Gestión Básica ---
    def add_position(self, position_data: Dict[str, Any]) -> bool:
        if not isinstance(position_data, dict): 
            print(f"ERROR [LPT {self.side.upper()} Add]: Dato no es dict."); return False
        if 'id' not in position_data: 
            print(f"ERROR [LPT {self.side.upper()} Add]: Falta 'id'."); return False
        
        self._positions.append(copy.deepcopy(position_data))
        
        # Usar config_param inyectado para el control de logs
        log_level = "INFO"
        if self._config_param:
            log_level = getattr(self._config_param, 'LOG_LEVEL', 'INFO').upper()

        # --- INICIO DE LA MODIFICACIÓN ---
        # Comentamos la impresión de nivel DEBUG para reducir el ruido.
        # if log_level == "DEBUG":
        #     print(f"DEBUG [LPT {self.side.upper()} Add]: Posición ID ...{str(position_data['id'])[-6:]} añadida. Total: {len(self._positions)}")
        # --- FIN DE LA MODIFICACIÓN ---
        return True

    def remove_position_by_index(self, index: int) -> Optional[Dict[str, Any]]:
        try:
            if 0 <= index < len(self._positions):
                removed_position = self._positions.pop(index)
                
                log_level = "INFO"
                if self._config_param:
                    log_level = getattr(self._config_param, 'LOG_LEVEL', 'INFO').upper()
                
                # --- INICIO DE LA MODIFICACIÓN ---
                # Comentamos la impresión de nivel DEBUG para reducir el ruido.
                # if log_level == "DEBUG":
                #     print(f"DEBUG [LPT {self.side.upper()} Remove Idx]: Posición índice {index} (ID ...{str(removed_position.get('id','N/A'))[-6:]}) eliminada. Total: {len(self._positions)}")
                # --- FIN DE LA MODIFICACIÓN ---
                return copy.deepcopy(removed_position)
            else: 
                print(f"ERROR [LPT {self.side.upper()} Remove Idx]: Índice {index} fuera de rango."); return None
        except Exception as e: 
            print(f"ERROR [LPT {self.side.upper()} Remove Idx]: Excepción {index}: {e}"); traceback.print_exc(); return None

    def remove_position_by_id(self, position_id: str) -> Optional[Dict[str, Any]]:
        index_to_remove = -1
        for i, pos in enumerate(self._positions):
            if pos.get('id') == position_id: 
                index_to_remove = i
                break
        if index_to_remove != -1: 
            return self.remove_position_by_index(index_to_remove)
        else: 
            print(f"WARN [LPT {self.side.upper()} Remove ID]: ID {position_id} no encontrado."); return None

    def update_position_details(self, position_id: str, details_to_update: Dict[str, Any]) -> bool:
        if not isinstance(details_to_update, dict): 
            print(f"ERROR [LPT {self.side.upper()} Update]: details no es dict."); return False
        found = False
        for i, pos in enumerate(self._positions):
            if pos.get('id') == position_id:
                try:
                    self._positions[i].update(details_to_update)
                    
                    log_level = "INFO"
                    if self._config_param:
                        log_level = getattr(self._config_param, 'LOG_LEVEL', 'INFO').upper()

                    # --- INICIO DE LA MODIFICACIÓN ---
                    # Comentamos la impresión de nivel DEBUG para reducir el ruido.
                    # if log_level == "DEBUG":
                    #     print(f"DEBUG [LPT {self.side.upper()} Update]: Pos ID ...{str(position_id)[-6:]} actualizada con: {details_to_update}")
                    # --- FIN DE LA MODIFICACIÓN ---
                    found = True
                    break
                except Exception as e: 
                    print(f"ERROR [LPT {self.side.upper()} Update]: Excepción ID {position_id}: {e}"); traceback.print_exc(); return False
        if not found: 
            print(f"WARN [LPT {self.side.upper()} Update]: ID {position_id} no encontrado.")
        return found

    # --- Métodos de Acceso y Cálculo ---
    def get_positions(self) -> List[Dict[str, Any]]:
        return copy.deepcopy(self._positions)

    def get_position_by_id(self, position_id: str) -> Optional[Dict[str, Any]]:
        for pos in self._positions:
            if pos.get('id') == position_id: 
                return copy.deepcopy(pos)
        return None

    def get_position_by_index(self, index: int) -> Optional[Dict[str, Any]]:
        try:
            if 0 <= index < len(self._positions): 
                return copy.deepcopy(self._positions[index])
            else: 
                print(f"WARN [LPT {self.side.upper()} Get Idx]: Índice {index} fuera de rango."); return None
        except Exception as e: 
            print(f"ERROR [LPT {self.side.upper()} Get Idx]: Excepción {index}: {e}"); return None

    def get_count(self) -> int:
        return len(self._positions)

    def get_total_size(self) -> float:
        if not self._utils: return 0.0
        total_size = 0.0
        for pos in self._positions: 
            total_size += self._utils.safe_float_convert(pos.get('size_contracts'), 0.0)
        return total_size

    def get_total_used_margin(self) -> float:
         if not self._utils: return 0.0
         total_margin = 0.0
         for pos in self._positions: 
             total_margin += self._utils.safe_float_convert(pos.get('margin_usdt'), 0.0)
         return total_margin

    def get_average_entry_price(self) -> float:
        if not self._utils: return 0.0
        total_value = 0.0; total_size = 0.0
        for pos in self._positions:
            size = self._utils.safe_float_convert(pos.get('size_contracts'), 0.0)
            price = self._utils.safe_float_convert(pos.get('entry_price'), 0.0)
            if size > 0 and price > 0: 
                total_value += size * price
                total_size += size
        return self._utils.safe_division(total_value, total_size, default=0.0)

    # --- Visualización ---
    def display_table(self):
        config_to_use = self._config_param
        log_level = "INFO"
        if config_to_use:
            log_level = getattr(config_to_use, 'LOG_LEVEL', 'INFO').upper()

        if not self._positions:
            # --- INICIO DE LA MODIFICACIÓN ---
            # Comentamos la impresión de nivel DEBUG para reducir el ruido.
            # if log_level == "DEBUG":
            #     print(f"\n--- Tabla Posiciones Lógicas {self.side.upper()} ---\n(Vacía)\n" + "-" * 60)
            # --- FIN DE LA MODIFICACIÓN ---
            return
        
        data_for_df = []
        columns = ['ID', 'Entry Time', 'Entry Price', 'Size', 'Margin', 'Leverage', 'Stop Loss', 'API Order ID']
        price_prec = 4; qty_prec = 3
        
        if config_to_use:
             try: 
                 price_prec = int(getattr(config_to_use, 'PRICE_PRECISION', 4))
                 qty_prec = int(getattr(config_to_use, 'DEFAULT_QTY_PRECISION', 3))
             except Exception: 
                 print("WARN [LPT Display]: Error obteniendo precisiones config."); price_prec = 4; qty_prec = 3
        
        for pos in self._positions:
            entry_ts = pos.get('entry_timestamp')
            entry_ts_str = self._utils.format_datetime(entry_ts, '%Y-%m-%d %H:%M:%S') if self._utils and entry_ts else "N/A"
            sl_price = pos.get('stop_loss_price')
            
            data_for_df.append({
                'ID': str(pos.get('id', 'N/A'))[-6:], 
                'Entry Time': entry_ts_str,
                'Entry Price': f"{self._utils.safe_float_convert(pos.get('entry_price'), 0.0):.{price_prec}f}" if self._utils else pos.get('entry_price'),
                'Size': f"{self._utils.safe_float_convert(pos.get('size_contracts'), 0.0):.{qty_prec}f}" if self._utils else pos.get('size_contracts'),
                'Margin': f"{self._utils.safe_float_convert(pos.get('margin_usdt'), 0.0):.2f}" if self._utils else pos.get('margin_usdt'),
                'Leverage': f"{float(pos.get('leverage', 1.0)):.1f}x" if pos.get('leverage') else 'N/A',
                'Stop Loss': f"{self._utils.safe_float_convert(sl_price, 0.0):.{price_prec}f}" if self._utils and sl_price else 'N/A',
                'API Order ID': str(pos.get('api_order_id', 'N/A'))[-8:]
            })
        try:
             df = pd.DataFrame(data_for_df, columns=columns)
             print(f"\n--- Tabla Posiciones Lógicas {self.side.upper()} (Total: {len(self._positions)}) ---")
             if not df.empty:
                 table_string = df.to_string(index=False, justify='right')
                 print(table_string)
                 print("-" * (len(table_string.split('\n')[0]) if table_string else 60))
             else: 
                 print("(Tabla vacía)")
                 print("-" * 60)
        except Exception as e_df: 
            print(f"ERROR [LPT Display]: Creando DataFrame: {e_df}")
            print("-" * 60)