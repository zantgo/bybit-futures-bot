# core/menu/screens/operation_manager/manual_position_manager/__init__.py

"""
Fachada del paquete del Gestor Manual de Posiciones.

Expone la función principal de la pantalla para que sea accesible
desde el módulo `_main.py` del `operation_manager`.
"""

from ._main import show_manual_position_manager_screen

__all__ = [
    'show_manual_position_manager_screen',
]