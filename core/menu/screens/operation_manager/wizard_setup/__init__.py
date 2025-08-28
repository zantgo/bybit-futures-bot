# core/menu/screens/operation_manager/wizard_setup/__init__.py
from typing import Dict, Any
from ._main_logic import operation_setup_wizard

# --- INICIO DE LA MODIFICACIÓN ---
def init(dependencies: Dict[str, Any]):
    """Inyecta dependencias en los módulos de este paquete."""
    from . import _main_logic
    if hasattr(_main_logic, 'init'):
        _main_logic.init(dependencies)
# --- FIN DE LA MODIFICACIÓN ---

__all__ = ['init', 'operation_setup_wizard']