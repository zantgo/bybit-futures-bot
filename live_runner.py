# =============== INICIO ARCHIVO: live_runner.py (v13 - Menú Intervención Mejorado) ===============
"""
Contiene la lógica para ejecutar el modo Live del bot.
Adapta la inicialización para usar tamaño base por posición y número inicial de slots.
Menú de intervención manual simplificado para solo ajustar slots, con advertencia de capital.
Utiliza consistentemente los módulos pasados como parámetros.

v13:
- Integra el nuevo menú de intervención manual mejorado (`get_automatic_mode_intervention_menu`).
- Añade la lógica para manejar las nuevas opciones del menú: ajustar tamaño base de posición,
  ver estadísticas en vivo y controlar la visualización de ticks.
- Mantiene la funcionalidad existente para el modo Live Interactivo, que opera basado
  únicamente en la estrategia de bajo nivel.
"""
import time
import traceback
import json
import datetime
from decimal import Decimal, ROUND_DOWN, InvalidOperation
from typing import Optional, Dict, Any, List, Tuple, TYPE_CHECKING
import sys
import threading
import os

# NO hay imports globales de config, utils, menu aquí; se recibirán como parámetros.

# --- Imports para listener de teclas multiplataforma ---
if os.name == 'nt':
    import msvcrt
else:
    import select
    import tty
    import termios

# Importar módulos necesarios del proyecto (solo para Type Checking)
if TYPE_CHECKING:
    import config as cfg_mod 
    from core import utils as ut_mod 
    from core import menu as mn_mod 
    from core import live_operations as lo_mod
    from core.strategy import position_manager as pm_mod
    from core.strategy import balance_manager as bm_mod
    from core.strategy import position_state as ps_mod
    from core.strategy import event_processor as ep_mod
    from core.strategy import ta_manager as ta_mod
    from core.logging import open_position_snapshot_logger as opsl_mod

# --- Constantes para la Prueba de Ciclo ---
TEST_CYCLE_WAIT_SECONDS = 5
FINAL_SYNC_WAIT_SECONDS = 3

# --- Variables Globales para Intervención Manual ---
_key_pressed_event = threading.Event()
_manual_intervention_char = 'm'
_stop_key_listener_thread = threading.Event()

# --- Variables globales para almacenar la configuración de la sesión ---
_session_base_position_size_usdt: Optional[float] = None
_session_initial_max_logical_positions: Optional[int] = None
# --- NUEVA VARIABLE DE ESTADO PARA VISUALIZACIÓN DE TICKS ---
_tick_visualization_status = {"low_level": True, "ut_bot": False}


# --- Función del Hilo Listener de Teclas (Modificada para robustez) ---
def key_listener_thread_func():
    global _key_pressed_event, _manual_intervention_char, _stop_key_listener_thread
    print(f"\n[Key Listener] Hilo iniciado. Presiona '{_manual_intervention_char}' para menú manual, Ctrl+C para salir del bot.")
    
    # --- Listener para Windows ---
    if os.name == 'nt':
        while not _stop_key_listener_thread.is_set():
            if msvcrt.kbhit():
                try:
                    char_bytes = msvcrt.getch()
                    try: 
                       char = char_bytes.decode().lower()
                    except UnicodeDecodeError: 
                       continue # Ignorar bytes que no decodifican
                    if char == _manual_intervention_char:
                        print(f"\n[Key Listener] Tecla '{_manual_intervention_char}' detectada!")
                        _key_pressed_event.set()
                except Exception as e_kb: 
                   print(f"Error en listener (kbhit/getch): {e_kb}")
            time.sleep(0.1) # Pequeña pausa para no consumir 100% CPU
            
    # --- Listener para Linux / macOS (TTY) ---
    else: 
        old_settings = None # Inicializar para que exista en el finally
        try:
            # Verificar que stdin sea realmente una TTY
            if not sys.stdin.isatty():
                 print("ERROR [Key Listener]: Stdin no es una TTY. Modo interactivo no funcionará.")
                 return
                 
            old_settings = termios.tcgetattr(sys.stdin)
            tty.setcbreak(sys.stdin.fileno()) # Poner en modo Cbreak
            
            # Bucle principal del listener
            while not _stop_key_listener_thread.is_set():
                # select.select monitoriza si hay datos para leer en stdin
                rlist, _, _ = select.select([sys.stdin], [], [], 0.1) # Timeout 0.1s
                if rlist: # Si hay algo para leer
                    try:
                        char = sys.stdin.read(1).lower()
                        if char == _manual_intervention_char:
                            print(f"\n[Key Listener] Tecla '{_manual_intervention_char}' detectada!")
                            _key_pressed_event.set()
                    except Exception as e_sel: 
                        print(f"Error en listener (select/read): {e_sel}")
                        
        except Exception as e_tty_init: # Captura errores de tcgetattr o setcbreak
            print(f"ERROR [Key Listener]: Configurando TTY o durante el bucle: {e_tty_init}.")
            traceback.print_exc()
        finally:
            # --- Bloque CRÍTICO: Restaurar la configuración de la TTY ---
            if old_settings: # Solo intentar restaurar si se obtuvieron settings
                print("[Key Listener] Restaurando configuración original de la terminal...")
                try:
                   # TCSADRAIN: Espera a que toda la salida se transmita antes de cambiar
                   termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
                   print("[Key Listener] Configuración de terminal restaurada.")
                except Exception as e_restore:
                   print(f"ERROR GRAVE [Key Listener]: Falló la restauración de termios: {e_restore}")
            # else:
            #    print("[Key Listener] No hay 'old_settings' para restaurar (¿tcgetattr falló?).")
                
    print("[Key Listener] Hilo terminado.")


# --- Función para Manejar el Menú de Intervención Manual (MODIFICADA) ---
def handle_manual_intervention_menu(
    config_module: Any, 
    utils_module: Any,  
    menu_module: Any,   
    position_manager_module: Optional[Any]
):
    global _key_pressed_event, _session_base_position_size_usdt, _tick_visualization_status

    if not config_module or not utils_module or not menu_module or not position_manager_module:
        print("ERROR [Manual Menu]: Faltan dependencias."); 
        if _key_pressed_event: _key_pressed_event.clear(); 
        return

    pm_initialized = getattr(position_manager_module, '_initialized', False)
    if not pm_initialized:
        print("ERROR [Manual Menu]: Position Manager no está inicializado."); 
        return

    print("\n\n" + "="*30 + " INTERVENCIÓN MANUAL " + "="*30)
    print("ADVERTENCIA: El bot sigue procesando ticks en segundo plano.")

    # Bucle del menú de intervención
    while True:
        # Obtener el resumen actualizado en cada iteración del menú
        summary = position_manager_module.get_position_summary()
        if summary.get('error'):
            print(f"ERROR [Manual Menu]: No se pudo obtener resumen PM: {summary['error']}")
            break # Salir del menú si no se puede obtener el estado
        
        # Añadir el estado específico de este runner para que el menú lo muestre
        summary['bot_state'] = "LIVE_INTERACTIVE"
        
        # Llamar al nuevo menú mejorado
        choice = menu_module.get_automatic_mode_intervention_menu(
            pm_summary=summary,
            tick_visualization_status=_tick_visualization_status
        )

        # Manejar las nuevas opciones del menú
        if choice == '1': # Ver Estadísticas
            menu_module.display_live_stats(summary) # Asume que esta función existe en el módulo de menú
            input("Presione Enter para continuar...")
        
        elif choice == '2': # Alternar visualización de Ticks (Bajo Nivel)
            _tick_visualization_status['low_level'] = not _tick_visualization_status['low_level']
            setattr(config_module, 'PRINT_TICK_LIVE_STATUS', _tick_visualization_status['low_level'])
            print(f"INFO: Visualización de Ticks de Bajo Nivel {'ACTIVADA' if _tick_visualization_status['low_level'] else 'DESACTIVADA'}.")
            time.sleep(1.5)

        elif choice == '3': # Alternar visualización de Ticks (UT Bot)
            print("INFO: La visualización de Ticks del UT Bot solo está disponible en Modo Automático.")
            time.sleep(2)

        elif choice == '4': # Aumentar Slots
            success, message = position_manager_module.add_max_logical_position_slot()
            print(f"Resultado: {message}"); time.sleep(2)
        
        elif choice == '5': # Disminuir Slots
            success, message = position_manager_module.remove_max_logical_position_slot()
            print(f"Resultado: {message}"); time.sleep(2)
        
        elif choice == '6': # Cambiar Tamaño Base de Posición
            try:
                current_size = summary.get('initial_base_position_size_usdt', 0.0)
                new_size_str = input(f"Ingrese nuevo tamaño base por posición (USDT) [Actual: {current_size:.2f}], 0 para cancelar: ").strip()
                if new_size_str:
                    new_size = float(new_size_str)
                    if new_size > 0:
                        success, message = position_manager_module.set_base_position_size(new_size)
                        print(f"Resultado: {message}")
                    else: print("Cambio de tamaño cancelado.")
                else: print("Entrada vacía, cambio cancelado.")
            except (ValueError, TypeError): print("Error: Entrada inválida.")
            except Exception as e_set_size: print(f"Error cambiando tamaño base: {e_set_size}")
            time.sleep(2)
        
        elif choice == '0': # Salir del menú de intervención
            print("Volviendo a la operación del bot...")
            break
        
        else:
            print("Opción inválida."); time.sleep(1)

        # Limpiar la pantalla para la siguiente iteración del menú
        os.system('cls' if os.name == 'nt' else 'clear')

    print("="*30 + " FIN INTERVENCIÓN MANUAL " + "="*30 + "\n")


# --- Lógica Modo Live con Menú Pre-Inicio ---
def run_live_pre_start(
    final_summary: Dict[str, Any],
    operation_mode: str,
    config_module: Any, 
    utils_module: Any,  
    menu_module: Any,   
    live_operations_module: Optional[Any],
    position_manager_module: Optional[Any],
    balance_manager_module: Optional[Any],
    position_state_module: Optional[Any],
    open_snapshot_logger_module: Optional[Any],
    event_processor_module: Optional[Any],
    ta_manager_module: Optional[Any]
) -> Optional[Any]:
    global _session_base_position_size_usdt, _session_initial_max_logical_positions, _tick_visualization_status

    connection_ticker_module: Optional[Any] = None
    key_listener_hilo: Optional[threading.Thread] = None

    if not all([config_module, utils_module, menu_module, event_processor_module, ta_manager_module]):
        missing_core = [name for name, mod_val in [('config', config_module), ('utils', utils_module), ('menu', menu_module), ('EP', event_processor_module), ('TA', ta_manager_module)] if not mod_val]
        print(f"ERROR CRITICO [Live Runner]: Faltan módulos core: {missing_core}. Abortando."); return None
    if not live_operations_module:
        print("ERROR CRITICO [Live Runner]: Módulo live_operations no disponible. Abortando."); return None

    management_enabled = getattr(config_module, 'POSITION_MANAGEMENT_ENABLED', False)
    if management_enabled and not all([position_manager_module, balance_manager_module, position_state_module]):
        missing_pm_deps = [name for name, mod_val in [('PM', position_manager_module), ('BM', balance_manager_module), ('PS', position_state_module)] if not mod_val]
        print(f"ERROR CRITICO [Live Runner]: Gestión habilitada pero faltan {missing_pm_deps}. Abortando."); return None

    initialized_accs: List[str] = []
    real_account_states: Dict[str, Dict[str, Any]] = {}
    operative_accounts: List[str] = []
    bot_started: bool = False
    core_initialized: bool = False
    
    try:
        print("\nInicializando Conexiones y Verificando Configuración Bybit...")
        try: from live.connection import manager as live_manager
        except ImportError: raise RuntimeError("Módulo live.connection.manager no disponible.")
        live_manager.initialize_all_clients() 
        initialized_accs = live_manager.get_initialized_accounts()
        if not initialized_accs: raise RuntimeError("No se inicializaron clientes API válidos.")
        print(f"Cuentas API Inicializadas: {initialized_accs}")

        required_live_accounts = set([getattr(config_module, 'TICKER_SOURCE_ACCOUNT', 'profit')])
        if management_enabled:
            req_pm_accs = {getattr(config_module,'ACCOUNT_MAIN','main'), getattr(config_module,'ACCOUNT_PROFIT','profit')}
            trading_mode_check = getattr(config_module, 'POSITION_TRADING_MODE', 'LONG_SHORT')
            long_acc_cfg = getattr(config_module, 'ACCOUNT_LONGS', None); short_acc_cfg = getattr(config_module, 'ACCOUNT_SHORTS', None)
            if trading_mode_check != 'SHORT_ONLY' and long_acc_cfg: req_pm_accs.add(long_acc_cfg)
            if trading_mode_check != 'LONG_ONLY' and short_acc_cfg: req_pm_accs.add(short_acc_cfg)
            req_pm_accs = {acc for acc in req_pm_accs if acc is not None}; required_live_accounts.update(req_pm_accs)
        missing_accounts = required_live_accounts - set(initialized_accs)
        if missing_accounts:
             is_critical = False; profit_acc_name = getattr(config_module,'ACCOUNT_PROFIT', None)
             if profit_acc_name and profit_acc_name in missing_accounts: is_critical = True
             if getattr(config_module,'TICKER_SOURCE_ACCOUNT', None) in missing_accounts: is_critical = True
             if management_enabled:
                 main_acc_name = getattr(config_module,'ACCOUNT_MAIN', None)
                 if main_acc_name and main_acc_name in missing_accounts: is_critical = True
                 long_acc = getattr(config_module, 'ACCOUNT_LONGS', None); short_acc = getattr(config_module, 'ACCOUNT_SHORTS', None)
                 if trading_mode_check != 'SHORT_ONLY' and long_acc and long_acc in missing_accounts: is_critical = True
                 if trading_mode_check != 'LONG_ONLY' and short_acc and short_acc in missing_accounts: is_critical = True
             msg_type = "ERROR CRÍTICO" if is_critical else "ADVERTENCIA"; print(f"\n{msg_type}: Faltan conexiones API: {missing_accounts}");
             if is_critical: raise RuntimeError("Faltan conexiones API críticas.")
             else: print("  -> Funcionalidad limitada.")

        symbol = getattr(config_module, 'TICKER_SYMBOL', None)
        if not symbol: print("\nADVERTENCIA: TICKER_SYMBOL no definido.");
        if live_operations_module and symbol: 
            print("\nObteniendo estado real de las cuentas desde Bybit API...")
            operative_accounts = [] 
            if management_enabled:
                trading_mode_ops = getattr(config_module, 'POSITION_TRADING_MODE', 'LONG_SHORT')
                long_acc = getattr(config_module, 'ACCOUNT_LONGS', None); short_acc = getattr(config_module, 'ACCOUNT_SHORTS', None); main_acc = getattr(config_module, 'ACCOUNT_MAIN', 'main')
                long_acc_op = long_acc if long_acc and long_acc in initialized_accs else main_acc
                short_acc_op = short_acc if short_acc and short_acc in initialized_accs else main_acc
                if trading_mode_ops != 'SHORT_ONLY' and long_acc_op in initialized_accs: operative_accounts.append(long_acc_op)
                if trading_mode_ops != 'LONG_ONLY' and short_acc_op in initialized_accs: operative_accounts.append(short_acc_op)
                operative_accounts = list(set(operative_accounts)); print(f"  Cuentas operativas: {operative_accounts}")
            else:
                 main_acc_chk = getattr(config_module, 'ACCOUNT_MAIN', None)
                 if main_acc_chk and main_acc_chk in initialized_accs: operative_accounts.append(main_acc_chk); print(f"  Gestión desactivada. Chequeando principal: {operative_accounts}")
                 else: print(f"  Gestión desactivada. Principal no config/init.")
            for acc_name in initialized_accs: 
                print(f"  Consultando cuenta: '{acc_name}'..."); acc_state = {'unified_balance': None, 'funding_balance': None, 'positions': []}
                try:
                    acc_state['unified_balance'] = live_operations_module.get_unified_account_balance_info(acc_name)
                    acc_state['funding_balance'] = live_operations_module.get_funding_account_balance_info(acc_name)
                    if acc_name in operative_accounts:
                        positions_raw = live_operations_module.get_active_position_details_api(symbol, acc_name)
                        acc_state['positions'] = [p for p in positions_raw if p.get('symbol') == symbol and utils_module.safe_float_convert(p.get('size'), 0.0) > 1e-12] if positions_raw else []
                    real_account_states[acc_name] = acc_state
                except Exception as api_err: print(f"    ERROR obteniendo datos API para '{acc_name}': {api_err}"); real_account_states[acc_name] = acc_state
            print("Estado real obtenido.")
            if menu_module: menu_module.display_live_pre_start_overview(real_account_states, symbol) 
            else: print("WARN: Módulo Menu no disponible.")
        elif not live_operations_module: print("\nADVERTENCIA: Live Operations no disponible.")
        elif not symbol: print("\nADVERTENCIA: TICKER_SYMBOL no definido.")

        while True:
            live_choice = menu_module.get_live_main_menu_choice() if menu_module else input("...")

            if live_choice == '1':
                 if not menu_module: print("ERROR: Menu no disponible."); continue
                 while True: 
                    acc_choice_tuple: Tuple[Optional[str], Optional[str]] = menu_module.get_account_selection_menu_choice(initialized_accs)
                    acc_choice, selected_account = acc_choice_tuple
                    if acc_choice == '0': break
                    elif selected_account:
                        while True:
                            unified_balance_detail=None; funding_balance_detail=None; account_positions_detail=[]
                            symbol_detail=getattr(config_module, 'TICKER_SYMBOL', 'N/A')
                            if live_operations_module:
                                print(f"\nRefrescando datos para '{selected_account}'...")
                                try:
                                    unified_balance_detail = live_operations_module.get_unified_account_balance_info(selected_account)
                                    funding_balance_detail = live_operations_module.get_funding_account_balance_info(selected_account)
                                    is_operative_now = selected_account in operative_accounts
                                    if symbol_detail != 'N/A' and is_operative_now:
                                         pos_raw = live_operations_module.get_active_position_details_api(symbol_detail, selected_account)
                                         account_positions_detail = [p for p in pos_raw if p.get('symbol') == symbol_detail and utils_module.safe_float_convert(p.get('size'), 0.0) > 1e-12] if pos_raw else []
                                    print("Datos refrescados.")
                                except Exception as refresh_err: print(f"  ERROR refrescando: {refresh_err}"); time.sleep(2)
                            else: print("ERROR: Live Operations no disponible."); time.sleep(2)
                            has_long_detail = any(p.get('side') == 'Buy' and utils_module.safe_float_convert(p.get('size'), 0.0) > 1e-12 for p in account_positions_detail)
                            has_short_detail = any(p.get('side') == 'Sell' and utils_module.safe_float_convert(p.get('size'), 0.0) > 1e-12 for p in account_positions_detail)
                            menu_module.display_account_management_status(selected_account, unified_balance_detail, funding_balance_detail, account_positions_detail)
                            manage_choice = menu_module.get_account_management_menu_choice(selected_account, has_long_detail, has_short_detail)
                            if manage_choice == '1': continue
                            elif manage_choice == '2': 
                                if not live_operations_module: print("ERROR: Live Ops no disp."); continue
                                if not account_positions_detail: print(f"\nNo pos activas."); time.sleep(1.5); continue
                                confirm = input(f"Cerrar TODAS ({len(account_positions_detail)}) pos para {symbol_detail} en '{selected_account}'? (s/N): ").lower()
                                if confirm == 's': success = live_operations_module.close_all_symbol_positions(symbol_detail, account_name=selected_account); print("Envío Cierre Todas OK." if success else "Fallo envío."); input("Enter...");
                                else: print("Cierre cancelado.")
                            elif manage_choice == '3': 
                                if not live_operations_module: print("ERROR: Live Ops no disp."); continue
                                if not has_long_detail: print(f"\nNo pos LONG activa."); time.sleep(1.5); continue
                                confirm = input(f"Cerrar LONG para {symbol_detail} en '{selected_account}'? (s/N): ").lower()
                                if confirm == 's': success = live_operations_module.close_position_by_side(symbol_detail, side_to_close="Buy", account_name=selected_account); print("Envío Cierre Long OK." if success else "Fallo envío."); input("Enter...");
                                else: print("Cierre cancelado.")
                            elif manage_choice == '4':
                                if not live_operations_module: print("ERROR: Live Ops no disp."); continue
                                if not has_short_detail: print(f"\nNo pos SHORT activa."); time.sleep(1.5); continue
                                confirm = input(f"Cerrar SHORT para {symbol_detail} en '{selected_account}'? (s/N): ").lower()
                                if confirm == 's': success = live_operations_module.close_position_by_side(symbol_detail, side_to_close="Sell", account_name=selected_account); print("Envío Cierre Short OK." if success else "Fallo envío."); input("Enter...");
                                else: print("Cierre cancelado.")
                            elif manage_choice == '0': break
                            else: print("Opción inválida."); time.sleep(1)
                    elif acc_choice is None: print("Opción de cuenta inválida."); time.sleep(1)
                 continue
           
            elif live_choice == '2': 
                print("\n--- Configuración para esta Sesión de Trading ---")
                if not menu_module: print("ERROR CRITICO: Menu no disponible. Abortando."); continue
                
                selected_trading_mode_session = menu_module.get_trading_mode_interactively()
                if selected_trading_mode_session == "CANCEL": print("Inicio del bot cancelado (Modo)."); continue
                
                base_size_input, initial_slots_input = menu_module.get_position_setup_interactively()
                if base_size_input is None or initial_slots_input is None:
                    print("Inicio del bot cancelado (Configuración de Posiciones)."); continue
                
                _session_base_position_size_usdt = base_size_input
                _session_initial_max_logical_positions = initial_slots_input
                
                print("-" * 62);
                print(f"  Modo Trading Sesión      : {selected_trading_mode_session}")
                print(f"  Tamaño Base por Posición : {base_size_input:.4f} USDT")
                print(f"  Nº Inicial Slots por Lado: {initial_slots_input}")
                print("-" * 62);
                print("Confirmando configuración..."); time.sleep(1)

                if not core_initialized:
                    print("\nInicializando Componentes Core (TA, EP, PM, BM, PS)...")
                    try:
                        _tick_visualization_status['low_level'] = True # Reset a default
                        setattr(config_module, 'PRINT_TICK_LIVE_STATUS', _tick_visualization_status['low_level'])
                        original_trading_mode_cfg = getattr(config_module, 'POSITION_TRADING_MODE', 'LONG_SHORT')
                        setattr(config_module, 'POSITION_TRADING_MODE', selected_trading_mode_session)
                        print(f"  -> Modo Trading Sesión: {selected_trading_mode_session} (Original Config: {original_trading_mode_cfg})")
                        
                        if not ta_manager_module or not hasattr(ta_manager_module, 'initialize'): raise RuntimeError("TA Manager no disponible.")
                        ta_manager_module.initialize()
                        
                        if open_snapshot_logger_module and hasattr(open_snapshot_logger_module, 'initialize_logger') and getattr(config_module, 'POSITION_LOG_OPEN_SNAPSHOT', False):
                            try: open_snapshot_logger_module.initialize_logger()
                            except Exception as e_log_init: print(f"WARN: Error inicializando OSL: {e_log_init}")
                        
                        if not event_processor_module or not hasattr(event_processor_module, 'initialize'): raise RuntimeError("Event Processor no disponible.")
                        ep_real_state = real_account_states if management_enabled else None
                        print(f"  Inicializando Event Processor...")
                        event_processor_module.initialize(
                            operation_mode=operation_mode,
                            initial_real_state=ep_real_state,
                            base_position_size_usdt=base_size_input, 
                            initial_max_logical_positions=initial_slots_input,
                            ut_bot_controller_instance=None, # No se usa en live interactivo
                            stop_loss_event=None # No se usa en live interactivo
                        )
                        pm_init_success = getattr(position_manager_module, '_initialized', False) if management_enabled and position_manager_module else (not management_enabled)
                        if management_enabled and not pm_init_success: raise RuntimeError("PM no se inicializó correctamente vía EP.")
                        core_initialized = True
                        print("Componentes Core inicializados.")
                    except RuntimeError as e_init_core: print(f"ERROR CRITICO init core: {e_init_core}"); traceback.print_exc(); print("Abortando inicio."); continue
                    except Exception as e_init_gen: print(f"ERROR CRITICO inesperado init: {e_init_gen}"); traceback.print_exc(); print("Abortando inicio."); continue
                else: print("INFO: Componentes Core ya inicializados.")

                pm_init_status = getattr(position_manager_module, '_initialized', False) if position_manager_module else False
                if management_enabled and position_manager_module and position_state_module and utils_module and pm_init_status: 
                    print("\nVerificando discrepancias Lógico vs Físico...");
                    current_bot_summary = position_manager_module.get_position_summary()
                    if not current_bot_summary or 'error' in current_bot_summary: print(f"WARN: No se pudo obtener resumen PM: {current_bot_summary.get('error', 'N/A') if current_bot_summary else 'N/A'}")
                    else:
                        bot_long_count = current_bot_summary.get('open_long_positions_count', 0); bot_short_count = current_bot_summary.get('open_short_positions_count', 0)
                        try:
                            phys_state_long = position_state_module.get_physical_position_state('long'); phys_state_short = position_state_module.get_physical_position_state('short')
                            phys_size_long = utils_module.safe_float_convert(phys_state_long.get('total_size_contracts'), 0.0); phys_size_short = utils_module.safe_float_convert(phys_state_short.get('total_size_contracts'), 0.0)
                            has_physical_long = phys_size_long > 1e-12; has_physical_short = phys_size_short > 1e-12
                            if (bot_long_count > 0 and not has_physical_long) or (bot_long_count == 0 and has_physical_long) or \
                               (bot_short_count > 0 and not has_physical_short) or (bot_short_count == 0 and has_physical_short):
                                 print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!! ADVERTENCIA !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"); print("!! DISCREPANCIA DETECTADA ENTRE ESTADO LÓGICO Y FÍSICO !!"); print(f"!!  - Lógicas (L/S): {bot_long_count} / {bot_short_count}"); print(f"!!  - Físicas (L/S): {'Sí' if has_physical_long else 'No'} / {'Sí' if has_physical_short else 'No'}"); print("!! RECOMENDACIÓN: CERRAR MANUALMENTE TODAS LAS POSICIONES FÍSICAS !!"); print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
                                 confirm_start = input("¿Iniciar de todas formas? (s/N): ").lower();
                                 if confirm_start != 's': print("Inicio cancelado por discrepancia."); continue
                        except Exception as e_disc: print(f"ERROR verificando discrepancia: {e_disc}. Saltando chequeo.")
                
                print("\nConfirmado. Iniciando Bot..."); bot_started = True
                if management_enabled and live_operations_module and config_module: 
                    symbol_lev = getattr(config_module, 'TICKER_SYMBOL', None); leverage_val = getattr(config_module, 'POSITION_LEVERAGE', 1.0)
                    if symbol_lev:
                        print(f"INFO [Live Runner]: Estableciendo Apalancamiento para {symbol_lev} a {leverage_val:.1f}x...")
                        acc_longs=getattr(config_module,'ACCOUNT_LONGS',None); acc_shorts=getattr(config_module,'ACCOUNT_SHORTS',None); acc_main=getattr(config_module,'ACCOUNT_MAIN','main')
                        account_to_call_from = next((acc for acc in [acc_main, acc_longs, acc_shorts] if acc and acc in initialized_accs), None)
                        if account_to_call_from:
                            live_operations_module.set_leverage(symbol=symbol_lev, buy_leverage=leverage_val, sell_leverage=leverage_val, account_name=account_to_call_from)
                        else: print(f"ERROR [Live Runner]: Ninguna cuenta operativa para config. apalancamiento.")
                
                try:
                    from live.connection import ticker as connection_ticker_module_local
                    connection_ticker_module = connection_ticker_module_local
                    print("Iniciando Ticker Live...");
                    if not event_processor_module or not hasattr(event_processor_module, 'process_event'): 
                        raise RuntimeError("EP sin método process_event.")
                    connection_ticker_module.start_ticker_thread(raw_event_callback=event_processor_module.process_event)
                    print("Ticker iniciado. El bot está operativo.")
                    
                    key_listener_active = False
                    if getattr(config_module, 'INTERACTIVE_MANUAL_MODE', False):
                        _stop_key_listener_thread.clear(); _key_pressed_event.clear()
                        key_listener_hilo = threading.Thread(target=key_listener_thread_func, daemon=True)
                        key_listener_hilo.start()
                        key_listener_active = True
                    else: 
                        print(f"Modo intervención manual ('{_manual_intervention_char}') DESACTIVADO.")

                    while True:
                        if key_listener_active and _key_pressed_event.is_set():
                            print("[Main Loop] Evento de tecla manual detectado. Preparando menú...")
                            _stop_key_listener_thread.set()
                            if key_listener_hilo and key_listener_hilo.is_alive():
                                key_listener_hilo.join(timeout=1.5)
                             
                            handle_manual_intervention_menu(
                                config_module=config_module, 
                                menu_module=menu_module,     
                                position_manager_module=position_manager_module
                            )
                            
                            _key_pressed_event.clear()
                            if getattr(config_module, 'INTERACTIVE_MANUAL_MODE', False):
                                _stop_key_listener_thread.clear()
                                key_listener_hilo = threading.Thread(target=key_listener_thread_func, daemon=True)
                                key_listener_hilo.start()
                            else: key_listener_active = False

                        if connection_ticker_module and hasattr(connection_ticker_module, 'is_ticker_alive') and not connection_ticker_module.is_ticker_alive():
                            raise RuntimeError("Ticker thread died.")
                            
                        time.sleep(0.2)
                        
                except KeyboardInterrupt: raise
                except Exception as ticker_err: print(f"ERROR CRITICO en bucle ticker/listener: {ticker_err}"); raise

            elif live_choice == '3':
                 if not management_enabled: print("\nERROR: Prueba de ciclo requiere Gestión activa."); time.sleep(2); continue
                 if not core_initialized:
                     print("\nADVERTENCIA: Componentes Core no inicializados. Iniciando con defaults de config para prueba...")
                     test_trading_mode = getattr(config_module, 'POSITION_TRADING_MODE', 'LONG_SHORT')
                     test_base_size = getattr(config_module, 'POSITION_BASE_SIZE_USDT', 10.0)
                     test_initial_slots = getattr(config_module, 'POSITION_MAX_LOGICAL_POSITIONS', 1)
                     _session_base_position_size_usdt = test_base_size 

                     try:
                         setattr(config_module, 'PRINT_TICK_LIVE_STATUS', False)
                         ta_manager_module.initialize()
                         ep_real_state_test = real_account_states
                         event_processor_module.initialize(
                             operation_mode=operation_mode, 
                             initial_real_state=ep_real_state_test, 
                             base_position_size_usdt=test_base_size,
                             initial_max_logical_positions=test_initial_slots 
                         )
                         pm_init_success_test = getattr(position_manager_module, '_initialized', False) if management_enabled and position_manager_module else (not management_enabled)
                         if management_enabled and not pm_init_success_test: raise RuntimeError("PM no se inicializó correctamente vía EP para prueba.")
                         core_initialized = True
                     except Exception as e_init_test: print(f"ERROR CRITICO init prueba: {e_init_test}"); continue
                 
                 pm_init_status_test = getattr(position_manager_module, '_initialized', False) if position_manager_module else False
                 if not pm_init_status_test: print("ERROR: PM no inicializado para prueba."); continue
                 run_full_test_cycle(config_module, utils_module, live_operations_module, position_manager_module, balance_manager_module, position_state_module, menu_module)
                 continue

            elif live_choice == '4':
                 pm_init_status_display = getattr(position_manager_module, '_initialized', False) if position_manager_module else False
                 if position_manager_module and pm_init_status_display and hasattr(position_manager_module, 'display_logical_positions'):
                     print("\n--- Posiciones Lógicas Internas ---"); position_manager_module.display_logical_positions()
                     print("-----------------------------------"); input("Enter...");
                 elif position_manager_module and not pm_init_status_display: print("INFO: PM no inicializado aún."); time.sleep(2.5)
                 else: print("ERROR: PM no disponible."); time.sleep(2)
                 continue
                 
            elif live_choice == '0': 
                print("Saliendo del Modo Live..."); 
                return connection_ticker_module
            else: 
                print("Opción no válida."); 
                time.sleep(1)

    except KeyboardInterrupt: 
        print("\nDeteniendo Proceso Live (Ctrl+C en runner)...")
    except ImportError as e: 
        print(f"Error Fatal Importación Live Runner: {e.name}."); traceback.print_exc()
    except RuntimeError as e: 
        print(f"Error Fatal Config/Ejecución Live Runner: {e}"); traceback.print_exc()
    except Exception as live_err: 
        print(f"Error inesperado Live Runner: {live_err}"); traceback.print_exc()
    finally:
         _stop_key_listener_thread.set()
         if key_listener_hilo and key_listener_hilo.is_alive():
             print("[Finally] Esperando que el hilo listener de teclas termine..."); 
             key_listener_hilo.join(timeout=1.0)
             if key_listener_hilo.is_alive(): 
                print("ADVERTENCIA: El hilo listener de teclas no terminó limpiamente.")
                
         if bot_started and connection_ticker_module and hasattr(connection_ticker_module, 'stop_ticker_thread'):
              print("\nAsegurando detención Ticker en finally...");
              try: connection_ticker_module.stop_ticker_thread(); print("Ticker detenido.")
              except Exception as stop_err: print(f"Error deteniendo ticker: {stop_err}")
         pm_initialized_finally = getattr(position_manager_module, '_initialized', False) if position_manager_module else False
         if management_enabled and position_manager_module and bot_started and pm_initialized_finally:
              try: 
                  print("Obteniendo resumen final PM...")
                  final_summary_local = position_manager_module.get_position_summary()
                  if final_summary_local and 'error' not in final_summary_local:
                      final_summary.clear(); final_summary.update(final_summary_local)
                      print("\n--- Resumen Final (Fin Live Runner) ---"); print(json.dumps(final_summary_local, indent=2)); print("-" * 30)
                      if open_snapshot_logger_module and hasattr(open_snapshot_logger_module, 'log_open_positions_snapshot') and getattr(config_module, 'POSITION_LOG_OPEN_SNAPSHOT', False): 
                          try: print("Guardando snapshot final..."); open_snapshot_logger_module.log_open_positions_snapshot(final_summary_local)
                          except Exception as log_err: print(f"Error guardando snapshot: {log_err}")
                  elif final_summary_local: print(f"Error resumen PM: {final_summary_local.get('error', 'N/A')}"); final_summary.clear(); final_summary['error'] = final_summary_local.get('error', 'Error resumen final')
                  else: print("WARN: No se pudo obtener resumen PM (vacío)."); final_summary.clear(); final_summary['error'] = 'No se pudo obtener resumen final (vacío)'
              except Exception as e_sum_fin: print(f"Error crítico resumen final: {e_sum_fin}"); final_summary.clear(); final_summary['error'] = f'Excepción resumen final: {e_sum_fin}'
         elif management_enabled and bot_started and not pm_initialized_finally: print("WARN: No se pudo obtener resumen final (PM no init)."); final_summary.clear(); final_summary['error'] = 'PM no init al finalizar'
         return connection_ticker_module


# --- FUNCIÓN DE PRUEBA DE CICLO COMPLETO ---
def run_full_test_cycle(
    config_param: Any, 
    utils_param: Any,  
    live_operations_param: Optional[Any],
    position_manager_param: Optional[Any],
    balance_manager_param: Optional[Any],
    position_state_param: Optional[Any],
    menu_param: Optional[Any] 
    ):
    global _session_base_position_size_usdt 

    print(f"\n--- Iniciando Prueba de Ciclo Forzado Dinámica (LONG & SHORT) ---")
    if not all([config_param, utils_param, position_manager_param, position_state_param, balance_manager_param, live_operations_param]):
        print("ERROR CRITICO [Test Cycle]: Faltan módulos esenciales. Abortando prueba."); input("Enter..."); return
    if not getattr(config_param, 'POSITION_MANAGEMENT_ENABLED', False):
        print("ERROR [Test Cycle]: Gestión de posiciones debe estar habilitada."); input("Enter..."); return
    pm_initialized_test = getattr(position_manager_param, '_initialized', False)
    if not pm_initialized_test:
        print("ERROR CRITICO [Test Cycle]: Position Manager no inicializado. Abortando."); input("Enter..."); return
    if not hasattr(position_manager_param, 'force_open_test_position') or not hasattr(position_manager_param, 'force_close_test_position'):
        print("ERROR CRITICO [Test Cycle]: Funciones 'force_open/close' no en PM. Abortando."); input("Enter..."); return
    if not hasattr(position_manager_param, 'sync_physical_state'): print("WARN [Test Cycle]: 'sync_physical_state' no en PM.")
    if not position_state_param or not hasattr(position_state_param, 'get_open_logical_positions'):
        print("ERROR CRITICO [Test Cycle]: Position State no disponible/inválido. Abortando."); input("Enter..."); return

    symbol = getattr(config_param, 'TICKER_SYMBOL', None); leverage = getattr(config_param, 'POSITION_LEVERAGE', 1.0)
    if not symbol: print("ERROR: TICKER_SYMBOL no definido."); input("Enter..."); return
    
    try: 
        from live.connection import manager as live_manager 
        assert live_manager.get_initialized_accounts()
    except Exception as e_lm: print(f"ERROR [Test Cycle]: Obteniendo live_manager: {e_lm}"); input("Enter..."); return
    
    amount_usdt_base_to_use: Optional[float] = _session_base_position_size_usdt
    if amount_usdt_base_to_use is None: 
        default_test_size = getattr(config_param, 'POSITION_BASE_SIZE_USDT', 10.0)
        amount_usdt_str = input(f"Ingrese cantidad BASE USDT por posición para prueba (ej: 5, 10) [Default: {default_test_size:.2f}]: ").strip()
        if not amount_usdt_str: amount_usdt_base_to_use = default_test_size
        else:
            try: amount_usdt_base_to_use = float(amount_usdt_str); assert amount_usdt_base_to_use > 0
            except (ValueError, AssertionError): print(f"ERROR: Cantidad USDT inválida. Usando default {default_test_size:.2f}."); amount_usdt_base_to_use = default_test_size
    else:
        print(f"INFO [Test Cycle]: Usando tamaño base de sesión: {amount_usdt_base_to_use:.2f} USDT para la prueba.")

    num_positions_str = input("Ingrese número de posiciones a probar por lado (1, 2 o 3) [Default: 1]: ").strip()
    if not num_positions_str: num_positions = 1
    else:
        try: num_positions = int(num_positions_str); assert num_positions in [1, 2, 3]
        except (ValueError, AssertionError): print(f"ERROR: Número de posiciones inválido (1, 2 o 3). Usando 1."); num_positions = 1
    
    print("\n--- Plan de Prueba Dinámico ---"); print(f"Se probarán {num_positions} posiciones por lado.")

    def get_current_price_helper() -> Optional[float]:
        session_ticker: Optional[Any] = None
        ticker_source_acc = getattr(config_param, 'TICKER_SOURCE_ACCOUNT', 'profit'); main_account = getattr(config_param, 'ACCOUNT_MAIN', 'main')
        if not live_manager: print("WARN [Test Price Helper]: live_manager no disponible."); return None
        session_ticker = live_manager.get_client(ticker_source_acc) or live_manager.get_client(main_account)
        if not session_ticker: print("WARN [Test Cycle]: No se pudo obtener sesión API para precio."); return None
        try:
            ticker_info = live_manager.get_tickers(session_ticker, category=getattr(config_param, 'CATEGORY_LINEAR', 'linear'), symbol=symbol)
            if not ticker_info or not ticker_info.get('result', {}).get('list'): print("WARN [Test Cycle]: No se pudo obtener ticker."); return None
            if not utils_param: print("WARN [Test Price Helper]: utils_param no disponible."); return None
            price = utils_param.safe_float_convert(ticker_info['result']['list'][0].get('lastPrice'))
            return price if price and price > 0 else None
        except Exception as price_err: print(f"ERROR [Test Cycle]: obteniendo precio: {price_err}"); return None

    def calculate_qty_str_helper(price: float, amount: float, lev: float) -> Optional[str]:
        if not utils_param or not config_param or price <= 0: return None
        size_raw = utils_param.safe_division(amount * lev, price, default=0.0);
        if size_raw <= 0: return None
        instr_info = live_operations_param.get_instrument_info(symbol) if live_operations_param else None
        qty_prec = getattr(config_param, 'DEFAULT_QTY_PRECISION', 3); min_qty_cfg = getattr(config_param, 'DEFAULT_MIN_ORDER_QTY', 0.001)
        if instr_info:
            qty_step = instr_info.get('qtyStep'); min_qty_str = instr_info.get('minOrderQty')
            if qty_step and live_operations_param and hasattr(live_operations_param, '_get_qty_precision_from_step'):
                 try: qty_prec = live_operations_param._get_qty_precision_from_step(qty_step)
                 except Exception: pass
            if min_qty_str: min_qty_cfg = utils_param.safe_float_convert(min_qty_str, min_qty_cfg)
        try:
             size_dec = Decimal(str(size_raw)); rounding_factor = Decimal('1e-' + str(qty_prec))
             size_rounded = size_dec.quantize(rounding_factor, rounding=ROUND_DOWN); qty_str_val = str(size_rounded)
             if float(qty_str_val) < min_qty_cfg:
                 print(f"WARN [Test Qty]: Cantidad calculada {qty_str_val} < mínima {min_qty_cfg}.")
             return qty_str_val
        except (InvalidOperation, Exception) as round_err: print(f"ERROR [Test Qty] redondeando {size_raw}: {round_err}."); return None

    def print_detailed_status_helper(step_description: str):
        print(f"\n========== ESTADO DETALLADO: {step_description} ==========")
        if position_manager_param and hasattr(position_manager_param, 'display_logical_positions'): position_manager_param.display_logical_positions()
        else: print("  Estado Lógico: PM no disponible para mostrar.")
        if position_state_param:
            print("\n  --- Estado Físico Agregado ---")
            phys_long = position_state_param.get_physical_position_state('long'); phys_short = position_state_param.get_physical_position_state('short')
            def dt_converter(o): 
                if isinstance(o, datetime.datetime): return utils_param.format_datetime(o) if utils_param else str(o)
                try: json.dumps(o); return o
                except TypeError: return str(o)
            print(f"  LONG : {json.dumps(phys_long, indent=2, default=dt_converter)}")
            print(f"  SHORT: {json.dumps(phys_short, indent=2, default=dt_converter)}")
        else: print("  Estado Físico: PS no disponible.")
        if balance_manager_param:
             print("\n  --- Balances ---"); balances = balance_manager_param.get_balances()
             print(json.dumps(balances, indent=2, default=dt_converter))
        else: print("  Balances: BM no disponible.")
        print("=======================================================\n")

    def wait_and_sync_helper(side: Optional[str] = None, seconds: int = TEST_CYCLE_WAIT_SECONDS):
         step_desc = f"Post-Espera ({seconds}s)"; print(f"\n... Esperando {seconds} segundos ..."); time.sleep(seconds)
         if side and position_manager_param and hasattr(position_manager_param, 'sync_physical_state'):
             print(f"... Sincronizando estado físico {side.upper()} ...");
             try: position_manager_param.sync_physical_state(side)
             except Exception as e_sync: print(f"ERROR [Test Cycle Sync]: {e_sync}"); traceback.print_exc()
             step_desc = f"Post-Sync {side.upper()}"
         elif side: print(f"... WARN [Test Cycle]: sync_physical_state no disponible lado {side} ...")
         else: print("... Espera completada (sin sync solicitada) ...")
         print_detailed_status_helper(step_desc)

    test_successful = True; initial_price = None; qty_str_test = None
    try:
        print(f"  Obteniendo precio inicial y calculando cantidad (Base USDT: {amount_usdt_base_to_use:.2f})...");
        initial_price = get_current_price_helper()
        if initial_price is None: raise RuntimeError("No se pudo obtener precio inicial.")
        qty_str_test = calculate_qty_str_helper(initial_price, amount_usdt_base_to_use, leverage)
        if qty_str_test is None: raise RuntimeError("No se pudo calcular la cantidad de prueba.")
        price_prec_print = getattr(config_param, 'PRICE_PRECISION', 2)
        print(f"  -> Precio Inicial: {initial_price:.{price_prec_print}f}, Cantidad Prueba (API): {qty_str_test}")
        print("\n--- INICIO PRUEBA LONG ---"); opened_long_ids = []
        for i in range(num_positions):
            print(f"\n1.{i+1} Abrir LONG #{i+1} (Test)..."); now_ts = datetime.datetime.now()
            open_ok, api_oid = position_manager_param.force_open_test_position('long', initial_price, now_ts, qty_str_test)
            if not open_ok: raise RuntimeError(f"Falló apertura forzada LONG #{i+1}")
            if api_oid: opened_long_ids.append(api_oid); wait_and_sync_helper('long')
        if num_positions >= 1 and len(position_manager_param.get_position_summary().get('open_long_positions',[])) > 0 :
            print(f"\n2. Cerrar LONG #1 (Test)..."); exit_price_l1 = initial_price * 1.005 
            close_ok_l1 = position_manager_param.force_close_test_position('long', 0, exit_price_l1, datetime.datetime.now())
            if not close_ok_l1: raise RuntimeError(f"Falló cierre forzado LONG #1"); wait_and_sync_helper('long')
        if num_positions >= 2 and len(position_manager_param.get_position_summary().get('open_long_positions',[])) > 0 :
            print(f"\n3. Cerrar LONG #2 (Test)..."); exit_price_l2 = initial_price * 1.007
            close_ok_l2 = position_manager_param.force_close_test_position('long', 0, exit_price_l2, datetime.datetime.now())
            if not close_ok_l2: raise RuntimeError(f"Falló cierre forzado LONG #2"); wait_and_sync_helper('long')
        print("--- FIN PRUEBA LONG ---"); print("\n8. Espera intermedia..."); wait_and_sync_helper(side=None)
        print("\n--- INICIO PRUEBA SHORT ---"); print(f"  Obteniendo precio actual y calculando cantidad para SHORT (Base USDT: {amount_usdt_base_to_use:.2f})...")
        current_price_short = get_current_price_helper()
        if current_price_short is None: raise RuntimeError("No se pudo obtener precio para SHORT.")
        qty_str_test_short = calculate_qty_str_helper(current_price_short, amount_usdt_base_to_use, leverage)
        if qty_str_test_short is None: raise RuntimeError("No se pudo calcular cantidad para SHORT.")
        print(f"  -> Precio Actual Short: {current_price_short:.{price_prec_print}f}, Cantidad Prueba (API): {qty_str_test_short}"); opened_short_ids = []
        for i in range(num_positions):
            print(f"\n9.{i+1} Abrir SHORT #{i+1} (Test)..."); now_ts_s = datetime.datetime.now()
            open_ok_s, api_oid_s = position_manager_param.force_open_test_position('short', current_price_short, now_ts_s, qty_str_test_short)
            if not open_ok_s: raise RuntimeError(f"Falló apertura forzada SHORT #{i+1}")
            if api_oid_s: opened_short_ids.append(api_oid_s); wait_and_sync_helper('short')
        if num_positions >= 1 and len(position_manager_param.get_position_summary().get('open_short_positions',[])) > 0 :
            print(f"\n10. Cerrar SHORT #1 (Test)..."); exit_price_s1 = current_price_short * 0.995 
            close_ok_s1 = position_manager_param.force_close_test_position('short', 0, exit_price_s1, datetime.datetime.now())
            if not close_ok_s1: raise RuntimeError(f"Falló cierre forzado SHORT #1"); wait_and_sync_helper('short')
        if num_positions >= 2 and len(position_manager_param.get_position_summary().get('open_short_positions',[])) > 0 :
            print(f"\n11. Cerrar SHORT #2 (Test)..."); exit_price_s2 = current_price_short * 0.993
            close_ok_s2 = position_manager_param.force_close_test_position('short', 0, exit_price_s2, datetime.datetime.now())
            if not close_ok_s2: raise RuntimeError(f"Falló cierre forzado SHORT #2"); wait_and_sync_helper('short')
        print("--- FIN PRUEBA SHORT ---")
        if num_positions == 3:
             final_price_for_third = get_current_price_helper();
             if final_price_for_third is None:
                 print("WARN [Test Cycle]: No se pudo obtener precio para cierre de terceras posiciones, usando precios base.")
                 final_price_for_third = initial_price 
             if len(position_manager_param.get_position_summary().get('open_long_positions',[])) > 0:
                 print("\n--- CIERRE FINAL LONG #3 (Caso num=3) ---");
                 price_l3 = final_price_for_third * 1.006 if final_price_for_third else initial_price * 1.01
                 print(f"\n12. Cerrar LONG #3 (Test)...")
                 close_l3_ok = position_manager_param.force_close_test_position('long', 0, price_l3, datetime.datetime.now())
                 if not close_l3_ok: print("WARN: Falló cierre forzado LONG #3"); wait_and_sync_helper('long')
                 else: wait_and_sync_helper('long') 
             if len(position_manager_param.get_position_summary().get('open_short_positions',[])) > 0:
                 print("\n--- CIERRE FINAL SHORT #3 (Caso num=3) ---");
                 price_s3 = final_price_for_third * 0.994 if final_price_for_third else (current_price_short * 0.99 if current_price_short else initial_price * 0.99)
                 print(f"\n13. Cerrar SHORT #3 (Test)...")
                 close_s3_ok = position_manager_param.force_close_test_position('short', 0, price_s3, datetime.datetime.now())
                 if not close_s3_ok: print("WARN: Falló cierre forzado SHORT #3"); wait_and_sync_helper('short')
                 else: wait_and_sync_helper('short') 
    except RuntimeError as rt_err: print(f"\nERROR DE EJECUCIÓN [Test Cycle]: {rt_err}"); test_successful = False; traceback.print_exc()
    except Exception as e: print(f"\nERROR INESPERADO [Test Cycle]: {e}"); traceback.print_exc(); test_successful = False
    finally:
        print("\n--- Resumen Final de la Prueba de Ciclo ---")
        print("... Sincronizando estado físico final LONG ..."); wait_and_sync_helper(side='long', seconds=FINAL_SYNC_WAIT_SECONDS)
        print("... Sincronizando estado físico final SHORT ..."); wait_and_sync_helper(side='short', seconds=FINAL_SYNC_WAIT_SECONDS)
        if position_manager_param and hasattr(position_manager_param, 'display_logical_positions'): position_manager_param.display_logical_positions()
        else: print("WARN: No se pudo mostrar tabla lógica final (PM no disponible).")
        print(f"\n--- RESULTADO PRUEBA CICLO: {'EXITOSA' if test_successful else 'FALLIDA'} ---")
        print("IMPORTANTE: Revisa logs y estado FÍSICO en Bybit."); print("-----------------------------------------")
        input("Presiona Enter para volver al menú Live...")

# =============== FIN ARCHIVO: live_runner.py (v13 - Menú Intervención Mejorado) ===============