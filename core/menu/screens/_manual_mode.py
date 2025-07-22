# core/menu/screens/_manual_mode.py

"""
Módulo para la Pantalla del Modo Manual Guiado.

Permite al usuario iniciar y gestionar "Tendencias Manuales", que son períodos
de trading con un modo operativo y condiciones de finalización explícitas.
"""
import time
from typing import Any

try:
    from simple_term_menu import TerminalMenu
except ImportError:
    TerminalMenu = None

# --- Dependencias del Menú ---
from .._helpers import clear_screen, print_tui_header, press_enter_to_continue, get_input, MENU_STYLE

def show_manual_mode_screen(pm_api: Any):
    """
    Muestra el menú principal para la gestión del Modo Manual Guiado.

    Args:
        pm_api: El objeto API del Position Manager para interactuar con él.
    """
    if not TerminalMenu:
        print("Error: 'simple-term-menu' no está instalado.")
        time.sleep(2)
        return

    while True:
        clear_screen()
        print_tui_header("Modo Manual Guiado")
        
        # Obtener estado actual
        manual_state = pm_api.get_manual_state()
        current_mode = manual_state.get('mode', 'N/A')
        
        print(f"\nEstado Actual: El bot está en modo -> {current_mode}\n")
        if "ONLY" in current_mode or "SHORT" in current_mode:
             print("Una tendencia manual está actualmente activa.")
        else:
             print("El bot está en modo NEUTRAL o LONG_SHORT general. Puedes iniciar una nueva tendencia.")

        menu_items = [
            "[1] Iniciar/Cambiar Tendencia Manual",
            "[2] Configurar Límites para la PRÓXIMA Tendencia",
            None,
            "[b] Volver al Dashboard Principal"
        ]
        main_menu = TerminalMenu(menu_items, title="Selecciona una acción:", **MENU_STYLE)
        choice = main_menu.show()

        if choice == 0:
            _set_manual_trend(pm_api)
        elif choice == 1:
            _configure_next_trend_limits(pm_api)
        else:
            break

def _set_manual_trend(pm_api: Any):
    """Maneja la lógica para cambiar el modo de trading de la tendencia actual."""
    current_mode = pm_api.get_manual_state().get('mode', 'N/A')
    
    title = f"Selecciona el nuevo modo de trading\nModo actual: {current_mode}"
    mode_menu = TerminalMenu(
        ["[1] LONG_ONLY", "[2] SHORT_ONLY", "[3] LONG_SHORT", "[4] NEUTRAL"],
        title=title,
        **MENU_STYLE
    )
    choice = mode_menu.show()
    
    if choice is None: return

    new_mode = ["LONG_ONLY", "SHORT_ONLY", "LONG_SHORT", "NEUTRAL"][choice]
    
    close_open = False
    # Preguntar si cerrar posiciones si el cambio es restrictivo
    if (current_mode == "LONG_SHORT" and new_mode == "SHORT_ONLY") or \
       (current_mode == "LONG_ONLY" and new_mode != "LONG_ONLY"):
        if pm_api.get_position_summary().get('open_long_positions_count', 0) > 0:
            confirm_menu = TerminalMenu(["[1] Sí, cerrar forzosamente", "[2] No, dejar abiertas"], title=f"Al cambiar a {new_mode}, ¿cerrar posiciones LONG actuales?").show()
            if confirm_menu == 0: close_open = True
    
    if (current_mode == "LONG_SHORT" and new_mode == "LONG_ONLY") or \
       (current_mode == "SHORT_ONLY" and new_mode != "SHORT_ONLY"):
        if pm_api.get_position_summary().get('open_short_positions_count', 0) > 0:
            confirm_menu = TerminalMenu(["[1] Sí, cerrar forzosamente", "[2] No, dejar abiertas"], title=f"Al cambiar a {new_mode}, ¿cerrar posiciones SHORT actuales?").show()
            if confirm_menu == 0: close_open = True

    # Los límites de la tendencia ya configurados se aplicarán automáticamente
    # al iniciar una nueva tendencia (pasar de NEUTRAL a otro modo).
    success, msg = pm_api.set_manual_trading_mode(new_mode, close_open=close_open)
    print(f"\n{msg}")
    if success and new_mode != "NEUTRAL":
        print("Los límites pre-configurados para la próxima tendencia (si existen) están ahora activos.")
    time.sleep(2.5)

def _configure_next_trend_limits(pm_api: Any):
    """Permite al usuario pre-configurar los límites para la próxima tendencia que inicie."""
    clear_screen()
    print_tui_header("Configurar Límites para la Próxima Tendencia Manual")
    print("\nEstos límites se activarán la próxima vez que inicies un modo LONG_ONLY o SHORT_ONLY.")
    
    # Obtener valores actuales para mostrarlos como default
    current_limits = pm_api.get_trend_limits()
    current_trade_limit = pm_api.get_manual_state().get('limit')
    
    # --- Recopilar nuevos valores del usuario ---
    print("\nIntroduce los nuevos valores (deja en blanco para mantener el actual).")
    
    trade_limit = get_input(
        "Límite de trades (0 para ilimitado)", 
        int, 
        current_trade_limit or 0, 
        min_val=0
    )
    
    duration = get_input(
        "Duración máxima (minutos, 0 para ilimitado)", 
        int, 
        current_limits.get("duration_minutes") or 0, 
        min_val=0
    )
    
    tp_roi = get_input(
        "Objetivo de TP por ROI de la canasta (%, ej: 2.5, 0 para desactivar)",
        float, 
        current_limits.get("tp_roi_pct") or 0.0, 
        min_val=0.0
    )

    sl_roi = get_input(
        "Stop Loss por ROI de la canasta (%, ej: -1.5, 0 para desactivar)",
        float, 
        current_limits.get("sl_roi_pct") or 0.0, 
        max_val=0.0
    )
    
    # No hay opción de precio aquí, ya que eso se manejará con los Triggers (Hitos)
    # en el modo automático para mantener la separación de conceptos.

    # Confirmar antes de guardar
    print("\nResumen de nuevos límites para la próxima tendencia:")
    print(f" - Límite de Trades: {'Ilimitados' if trade_limit == 0 else trade_limit}")
    print(f" - Duración: {'Ilimitada' if duration == 0 else f'{duration} minutos'}")
    print(f" - TP por ROI: {'Desactivado' if tp_roi == 0 else f'+{tp_roi:.2f}%'}")
    print(f" - SL por ROI: {'Desactivado' if sl_roi == 0 else f'{sl_roi:.2f}%'}")

    confirm_menu = TerminalMenu(["[1] Guardar y Volver", "[2] Descartar y Volver"], title="\n¿Guardar esta configuración de límites?").show()
    
    if confirm_menu == 0:
        success, msg = pm_api.set_trend_limits(
            duration=duration, 
            tp_roi_pct=tp_roi, 
            sl_roi_pct=sl_roi, 
            trade_limit=trade_limit
        )
        print(f"\n{msg}")
    else:
        print("\nCambios descartados.")
        
    time.sleep(2)