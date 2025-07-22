"""
Módulo del BalanceManager.

Define la clase BalanceManager, responsable de gestionar los balances LÓGICOS
de las cuentas (Long Margin, Short Margin, Profit Balance) durante la
operación del bot. También gestiona una caché de los balances REALES para
evitar sobrecargar la API.

v2.1: Refactorizado para eliminar la lógica de backtesting y enfocarse
      exclusivamente en el modo 'live_interactive'.
"""
import time
import traceback
from typing import Optional, Dict, Any

class BalanceManager:
    """Gestiona los balances lógicos y una caché de balances reales."""

    _REAL_BALANCES_CACHE_EXPIRY_SECONDS = 30

    def __init__(self, config: Any, utils: Any, live_operations: Any, connection_manager: Any):
        """
        Inicializa el BalanceManager con sus dependencias.
        """
        # Inyección de dependencias
        self._config = config
        self._utils = utils
        self._live_operations = live_operations
        self._connection_manager = connection_manager

        # Atributos de estado de la instancia
        self._initialized: bool = False
        
        # Balances lógicos
        self.operational_long_margin: float = 0.0
        self.operational_short_margin: float = 0.0
        self.used_long_margin: float = 0.0
        self.used_short_margin: float = 0.0
        self.profit_balance: float = 0.0
        
        # Balances iniciales para cálculos de sesión
        self.initial_operational_long_margin: float = 0.0
        self.initial_operational_short_margin: float = 0.0
        
        # Caché de balances reales
        self._real_balances_cache: Dict[str, Any] = {}
        self._real_balances_last_update: float = 0.0
        
        # La referencia al state_manager se inyecta post-inicialización
        self._state_manager: Optional[Any] = None

    def set_state_manager(self, state_manager: Any):
        """Inyecta una referencia al state_manager después de la inicialización."""
        self._state_manager = state_manager

    def initialize(
        self,
        real_balances_data: Dict[str, Dict[str, Any]],
        base_position_size_usdt: float,
        initial_max_logical_positions: int
    ):
        """
        Inicializa o resetea los balances lógicos para una nueva sesión en vivo.
        """
        if not all([self._config, self._utils, self._live_operations, self._connection_manager]):
            print("ERROR CRITICO [BM Init]: Faltan dependencias core.")
            self._initialized = False
            return

        print("[Balance Manager] Inicializando balances lógicos...")
        self._reset_logical_balances()

        # Obtener configuración
        trading_mode_config = getattr(self._config, 'POSITION_TRADING_MODE', 'LONG_SHORT')
        
        print(f"  Usando Tamaño Base para sesión: {base_position_size_usdt:.4f} USDT")
        print(f"  Usando Slots por Lado para sesión: {initial_max_logical_positions}")

        # Lógica de inicialización para modo Live
        self._initialize_live_balances(
            trading_mode_config,
            base_position_size_usdt,
            initial_max_logical_positions,
            real_balances_data
        )
        
        # Guardar balances iniciales para cálculos de ROI de sesión
        self.initial_operational_long_margin = self.operational_long_margin
        self.initial_operational_short_margin = self.operational_short_margin
        
        print(f"[Balance Manager] Balances LÓGICOS inicializados -> OpLong: {self.operational_long_margin:.4f}, OpShort: {self.operational_short_margin:.4f}")
        self._initialized = True
        
        # Calcular el tamaño dinámico inicial
        if self._state_manager:
            self.recalculate_dynamic_base_sizes()

    def _reset_logical_balances(self):
        """Método privado para resetear todos los atributos de balance."""
        self._initialized = False
        self.operational_long_margin = 0.0
        self.operational_short_margin = 0.0
        self.used_long_margin = 0.0
        self.used_short_margin = 0.0
        self.profit_balance = 0.0
        self.initial_operational_long_margin = 0.0
        self.initial_operational_short_margin = 0.0
        self._real_balances_cache = {}
        self._real_balances_last_update = 0.0

    def _initialize_live_balances(self, trading_mode, base_size, slots, real_balances_data):
        """Lógica para inicializar balances en modo Live."""
        print("  Modo Live: Estableciendo márgenes lógicos iniciales desde API...")
        
        long_acc_name = getattr(self._config, 'ACCOUNT_LONGS', self._config.ACCOUNT_MAIN)
        short_acc_name = getattr(self._config, 'ACCOUNT_SHORTS', self._config.ACCOUNT_MAIN)
        
        real_long_margin = self._get_usdt_wallet_balance_from_data(real_balances_data, long_acc_name)
        real_short_margin = self._get_usdt_wallet_balance_from_data(real_balances_data, short_acc_name)

        logical_capital_needed = base_size * slots
        
        if trading_mode in ["LONG_ONLY", "LONG_SHORT"]:
            self.operational_long_margin = min(logical_capital_needed, real_long_margin)
            if logical_capital_needed > real_long_margin:
                print(f"    ADVERTENCIA (Long): Capital lógico ({logical_capital_needed:.2f}) > real ({real_long_margin:.2f}). Usando real.")

        if trading_mode in ["SHORT_ONLY", "LONG_SHORT"]:
            self.operational_short_margin = min(logical_capital_needed, real_short_margin)
            if logical_capital_needed > real_short_margin:
                print(f"    ADVERTENCIA (Short): Capital lógico ({logical_capital_needed:.2f}) > real ({real_short_margin:.2f}). Usando real.")

    def _get_usdt_wallet_balance_from_data(self, data, acc_name) -> float:
        """Auxiliar para extraer el balance USDT de los datos de la API."""
        if acc_name in data and data.get(acc_name):
            balance_info = data[acc_name].get('unified_balance')
            if balance_info:
                return self._utils.safe_float_convert(balance_info.get('usdt_balance', 0.0))
        print(f"    WARN: No hay datos de balance para '{acc_name}'. Asumiendo 0.")
        return 0.0

    # --- Métodos Públicos ---
    
    def get_available_margin(self, side: str) -> float:
        if not self._initialized: return 0.0
        if side == 'long':
            return max(0.0, self.operational_long_margin - self.used_long_margin)
        elif side == 'short':
            return max(0.0, self.operational_short_margin - self.used_short_margin)
        return 0.0

    def decrease_used_margin(self, side: str, amount: float):
        if not self._initialized or not isinstance(amount, (int, float)): return
        if side == 'long':
            self.used_long_margin += abs(amount)
        elif side == 'short':
            self.used_short_margin += abs(amount)

    def increase_available_margin(self, side: str, amount: float):
        if not self._initialized or not isinstance(amount, (int, float)): return
        amount_to_release = abs(amount)
        if side == 'long':
            self.used_long_margin = max(0.0, self.used_long_margin - amount_to_release)
        elif side == 'short':
            self.used_short_margin = max(0.0, self.used_short_margin - amount_to_release)

    def update_operational_margins_based_on_slots(self, new_max_slots: int, base_size: float):
        if not self._initialized or new_max_slots < 0: return
        trading_mode = getattr(self._config, 'POSITION_TRADING_MODE', 'LONG_SHORT')
        if trading_mode != "SHORT_ONLY":
            self.operational_long_margin = max(base_size * new_max_slots, self.used_long_margin)
        if trading_mode != "LONG_ONLY":
            self.operational_short_margin = max(base_size * new_max_slots, self.used_short_margin)
        self.recalculate_dynamic_base_sizes()

    def record_real_profit_transfer(self, amount_transferred: float):
        if not self._initialized or not isinstance(amount_transferred, (int, float)) or amount_transferred < 0: return
        self.profit_balance += amount_transferred

    def get_balances_summary(self) -> dict:
        if not self._initialized: return {"error": "Balance Manager no inicializado"}
        return {
            "available_long_margin": round(self.get_available_margin('long'), 8),
            "available_short_margin": round(self.get_available_margin('short'), 8),
            "used_long_margin": round(self.used_long_margin, 8),
            "used_short_margin": round(self.used_short_margin, 8),
            "operational_long_margin": round(self.operational_long_margin, 8), 
            "operational_short_margin": round(self.operational_short_margin, 8),
            "profit_balance": round(self.profit_balance, 8)
        }

    def get_initial_total_capital(self) -> float:
        return self.initial_operational_long_margin + self.initial_operational_short_margin

    def recalculate_dynamic_base_sizes(self):
        if not self._initialized or not self._state_manager: return
        try:
            max_pos = self._state_manager.get_max_logical_positions()
            base_size_ref = self._state_manager.get_initial_base_position_size()
            long_size = max(base_size_ref, self._utils.safe_division(self.get_available_margin('long'), max_pos))
            short_size = max(base_size_ref, self._utils.safe_division(self.get_available_margin('short'), max_pos))
            self._state_manager.set_dynamic_base_size(long_size, short_size)
        except Exception:
            pass

    def update_real_balances_cache(self):
        """Actualiza la caché de balances reales si ha expirado."""
        if not self._initialized or not self._live_operations or not self._connection_manager: return
        now = time.time()
        if (now - self._real_balances_last_update) < self._REAL_BALANCES_CACHE_EXPIRY_SECONDS:
            return
            
        new_cache = {}
        accounts = [
            self._config.ACCOUNT_MAIN, self._config.ACCOUNT_LONGS,
            self._config.ACCOUNT_SHORTS, self._config.ACCOUNT_PROFIT
        ]
        for name in sorted(list(set(acc for acc in accounts if acc))):
            if name in self._connection_manager.get_initialized_accounts():
                info = self._live_operations.get_unified_account_balance_info(name)
                new_cache[name] = info or "Error al obtener balance"
        
        self._real_balances_cache = new_cache
        self._real_balances_last_update = now

    def get_real_balances_cache(self) -> Dict[str, Any]:
        """Devuelve una copia de la caché de balances reales."""
        return self._real_balances_cache.copy()