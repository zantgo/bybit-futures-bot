# ./core/strategy/pm/_entities.py

"""
Módulo de Entidades de Dominio para el Position Manager.
Única fuente de verdad para LogicalPosition, PhysicalPosition y LogicalBalances.
"""
import datetime
from dataclasses import dataclass, field
from typing import Optional

# --- Entidades de Posiciones ---

@dataclass
class LogicalPosition:
    """Representa una única operación de trading lógica (un 'slot')."""
    id: str
    entry_timestamp: datetime.datetime
    entry_price: float
    margin_usdt: float
    size_contracts: float
    leverage: float
    stop_loss_price: Optional[float] = None
    est_liq_price: Optional[float] = None
    tsl_activation_pct_at_open: float = 0.0
    tsl_distance_pct_at_open: float = 0.0
    ts_is_active: bool = False
    ts_peak_price: Optional[float] = None
    ts_stop_price: Optional[float] = None
    api_order_id: Optional[str] = None
    api_avg_fill_price: Optional[float] = None
    api_filled_qty: Optional[float] = None

@dataclass
class PhysicalPosition:
    """Representa el estado agregado de todas las posiciones lógicas de un lado."""
    avg_entry_price: float = 0.0
    total_size_contracts: float = 0.0
    total_margin_usdt: float = 0.0
    est_liq_price: Optional[float] = None
    last_update_ts: Optional[datetime.datetime] = None

# --- Entidades de Balance y Capital ---

@dataclass
class LogicalBalances:
    """Encapsula y gestiona el capital lógico para una única operación."""
    operational_margin: float = 0.0
    used_margin: float = 0.0
    profit_balance: float = 0.0

    @property
    def available_margin(self) -> float:
        return max(0.0, self.operational_margin - self.used_margin)

    def decrease_available_margin(self, amount: float):
        if isinstance(amount, (int, float)) and amount > 0:
            self.used_margin += abs(amount)

    def increase_available_margin(self, amount: float):
        if isinstance(amount, (int, float)) and amount > 0:
            self.used_margin = max(0.0, self.used_margin - abs(amount))
            
    def record_profit_transfer(self, amount_transferred: float):
        if isinstance(amount_transferred, (int, float)) and amount_transferred > 0:
            self.profit_balance += amount_transferred

    def reset(self):
        self.operational_margin = 0.0
        self.used_margin = 0.0
        self.profit_balance = 0.0