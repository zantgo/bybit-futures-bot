# =============== INICIO ARCHIVO: runners/live_interactive_menus.py (COMPLETO) ===============
"""
Contiene la lógica de los menús previos al inicio del modo Live Interactivo,
incluyendo la verificación del estado de las cuentas y la prueba de ciclo completo.
"""
import time
import datetime
import traceback
import json
import click
from decimal import Decimal, ROUND_DOWN, InvalidOperation
from typing import Optional, Dict, Any, List, Tuple

def run_pre_start_menu(
    initialized_accs: List[str],
    # Módulos de dependencia
    config_module: Any,
    utils_module: Any,
    menu_module: Any,
    live_operations_module: Any,
    position_manager_module: Any,
    balance_manager_module: Any,
    position_state_module: Any
) -> Tuple[Optional[float], Optional[int], Optional[str]]:
    """
    Ejecuta el bucle del menú pre-inicio. Devuelve la configuración de la sesión
    o la señal para salir.
    """
    symbol = getattr(config_module, 'TICKER_SYMBOL', None)
    
    # Obtener y mostrar el estado de las cuentas una vez al entrar
    if menu_module and hasattr(menu_module, 'display_live_pre_start_overview'):
        print("\nObteniendo estado real de las cuentas desde la API...")
        real_account_states = {}
        for acc_name in initialized_accs:
            try:
                acc_state = {
                    'unified_balance': live_operations_module.get_unified_account_balance_info(acc_name),
                    'funding_balance': live_operations_module.get_funding_account_balance_info(acc_name),
                    'positions': live_operations_module.get_active_position_details_api(symbol, acc_name) or []
                }
                real_account_states[acc_name] = acc_state
            except Exception as e:
                print(f"WARN: No se pudo obtener estado completo de '{acc_name}': {e}")
        menu_module.display_live_pre_start_overview(real_account_states, symbol)
    
    while True:
        choice = menu_module.get_live_main_menu_choice() if menu_module else '2'

        if choice == '1': # Ver/Gestionar Estado Detallado
            print("\nINFO: La gestión detallada de posiciones está disponible en el menú de intervención una vez iniciado el bot.")
            input("Presione Enter para continuar...")
            continue
            
        elif choice == '2': # Iniciar el Bot
            print("\n--- Configuración para esta Sesión de Trading ---")
            
            base_size, initial_slots = menu_module.get_position_setup_interactively()
            if base_size is None or initial_slots is None:
                print("Inicio del bot cancelado.")
                continue
            
            return base_size, initial_slots, "START_BOT"

        elif choice == '3': # Probar Ciclo Completo
            run_full_test_cycle(
                config_param=config_module,
                utils_param=utils_module,
                live_operations_param=live_operations_module,
                position_manager_param=position_manager_module,
                balance_manager_param=balance_manager_module,
                position_state_param=position_state_module
            )
            continue
            
        elif choice == '4': # Ver Tabla de Posiciones Lógicas
            print("\nINFO: Las posiciones lógicas estarán disponibles una vez iniciado el bot (opción 'status' en el menú de intervención).")
            input("Presione Enter para continuar...")
            continue

        elif choice == '0': # Salir
            return None, None, "EXIT"
        
        else:
            print("Opción no válida.")
            time.sleep(1)


def run_full_test_cycle(
    config_param: Any, 
    utils_param: Any,  
    live_operations_param: Any,
    position_manager_param: Any,
    balance_manager_param: Any,
    position_state_param: Any
):
    """
    Ejecuta una prueba de ciclo completo para abrir y cerrar posiciones
    long y short, permitiendo al usuario configurar los parámetros.
    """
    print(f"\n--- Iniciando Prueba de Ciclo Forzado Dinámica (LONG & SHORT) ---")

    # Re-inicializar PM para la prueba, para no interferir con la sesión principal
    print("Inicializando entorno de prueba para Position Manager...")
    position_manager_param.initialize(
        operation_mode="live_interactive", # Forzar modo live para usar ejecutor real
        base_position_size_usdt_param=getattr(config_param, 'POSITION_BASE_SIZE_USDT', 10.0),
        initial_max_logical_positions_param=getattr(config_param, 'POSITION_MAX_LOGICAL_POSITIONS', 1)
    )
    if not getattr(position_manager_param, '_initialized', False):
        print("ERROR CRITICO [Test Cycle]: Position Manager no se pudo inicializar para la prueba.")
        input("Presione Enter para volver...")
        return

    symbol = getattr(config_param, 'TICKER_SYMBOL', None)
    leverage = getattr(config_param, 'POSITION_LEVERAGE', 1.0)
    if not symbol:
        print("ERROR: TICKER_SYMBOL no definido en config.py."); input("Enter..."); return
    
    try:
        from live.connection import manager as live_manager
    except ImportError:
        print("ERROR [Test Cycle]: No se pudo importar live_manager."); input("Enter..."); return

    # --- Configuración Interactiva para la Prueba ---
    try:
        amount_usdt = click.prompt(
            "Ingrese cantidad BASE USDT por posición para la prueba", 
            type=float, 
            default=getattr(config_param, 'POSITION_BASE_SIZE_USDT', 10.0)
        )
        num_positions = click.prompt(
            "Ingrese número de posiciones a probar por lado (1-3)",
            type=click.IntRange(1, 3),
            default=1
        )
    except click.Abort:
        print("Prueba cancelada.")
        return

    # --- Funciones Helper Internas a la Prueba ---
    def get_current_price_helper() -> Optional[float]:
        session_ticker = live_manager.get_client(getattr(config_param, 'TICKER_SOURCE_ACCOUNT', 'profit')) or \
                         live_manager.get_client(getattr(config_param, 'ACCOUNT_MAIN', 'main'))
        if not session_ticker: return None
        try:
            ticker_info = live_operations_param.get_tickers(session_ticker, 'linear', symbol)
            price_str = ticker_info['result']['list'][0]['lastPrice']
            return utils_param.safe_float_convert(price_str)
        except Exception: return None

    def calculate_qty_str_helper(price: float, amount: float, lev: float) -> Optional[str]:
        # (Esta función helper interna se mantiene completa)
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
        # (Esta función helper interna se mantiene completa)
        print(f"\n========== ESTADO DETALLADO: {step_description} ==========")
        position_manager_param.display_logical_positions()
        print("\n  --- Balances ---")
        balances = balance_manager_param.get_balances()
        print(json.dumps(balances, indent=2))
        print("=======================================================\n")

    # --- Flujo de la Prueba ---
    test_successful = True
    try:
        print(f"Obteniendo precio inicial...")
        initial_price = get_current_price_helper()
        if initial_price is None: raise RuntimeError("No se pudo obtener precio inicial.")
        
        qty_str_test = calculate_qty_str_helper(initial_price, amount_usdt, leverage)
        if qty_str_test is None: raise RuntimeError("No se pudo calcular la cantidad de prueba.")
        
        print(f"Precio Inicial: {initial_price:.4f}, Cantidad a usar: {qty_str_test}")
        click.confirm("¿Continuar con la prueba de ciclo?", abort=True)

        # --- PRUEBA LONG ---
        print("\n--- INICIO PRUEBA LONG ---")
        for i in range(num_positions):
            print(f"\n{i+1}. Abriendo LONG #{i+1}...")
            open_ok, _ = position_manager_param.force_open_test_position('long', initial_price, datetime.datetime.now(), qty_str_test)
            if not open_ok: raise RuntimeError(f"Falló apertura forzada LONG #{i+1}")
            time.sleep(3)
            print_detailed_status_helper(f"Post-Apertura LONG #{i+1}")

        for i in range(num_positions):
            print(f"\n{i + num_positions + 1}. Cerrando LONG #{i+1}...")
            exit_price = initial_price * 1.005 # Simular ganancia
            close_ok = position_manager_param.force_close_test_position('long', 0, exit_price, datetime.datetime.now())
            if not close_ok: raise RuntimeError(f"Falló cierre forzado LONG #{i+1}")
            time.sleep(3)
            print_detailed_status_helper(f"Post-Cierre LONG #{i+1}")
        
        print("--- FIN PRUEBA LONG ---")
        time.sleep(5)

        # --- PRUEBA SHORT ---
        print("\n--- INICIO PRUEBA SHORT ---")
        current_price_short = get_current_price_helper()
        if current_price_short is None: raise RuntimeError("No se pudo obtener precio para SHORT.")
        qty_str_test_short = calculate_qty_str_helper(current_price_short, amount_usdt, leverage)
        if qty_str_test_short is None: raise RuntimeError("No se pudo calcular cantidad para SHORT.")

        for i in range(num_positions):
            print(f"\n{i + 2*num_positions + 1}. Abrir SHORT #{i+1}...")
            open_ok, _ = position_manager_param.force_open_test_position('short', current_price_short, datetime.datetime.now(), qty_str_test_short)
            if not open_ok: raise RuntimeError(f"Falló apertura forzada SHORT #{i+1}")
            time.sleep(3)
            print_detailed_status_helper(f"Post-Apertura SHORT #{i+1}")

        for i in range(num_positions):
            print(f"\n{i + 3*num_positions + 1}. Cerrar SHORT #{i+1}...")
            exit_price = current_price_short * 0.995 # Simular ganancia
            close_ok = position_manager_param.force_close_test_position('short', 0, exit_price, datetime.datetime.now())
            if not close_ok: raise RuntimeError(f"Falló cierre forzado SHORT #{i+1}")
            time.sleep(3)
            print_detailed_status_helper(f"Post-Cierre SHORT #{i+1}")
        print("--- FIN PRUEBA SHORT ---")

    except RuntimeError as rt_err:
        print(f"\nERROR DE EJECUCIÓN [Test Cycle]: {rt_err}")
        test_successful = False
    except click.Abort:
        print("\nPrueba de ciclo cancelada por el usuario.")
        test_successful = False
    except Exception as e:
        print(f"\nERROR INESPERADO [Test Cycle]: {e}")
        traceback.print_exc()
        test_successful = False
    finally:
        print("\n--- Resumen Final de la Prueba de Ciclo ---")
        print("Sincronizando estado final...")
        position_manager_param.sync_physical_state('long')
        position_manager_param.sync_physical_state('short')
        time.sleep(2)
        print_detailed_status_helper("Estado Final Post-Sync")
        
        color = 'green' if test_successful else 'red'
        click.secho(f"--- RESULTADO PRUEBA CICLO: {'EXITOSA' if test_successful else 'FALLIDA'} ---", fg=color, bold=True)
        click.echo("IMPORTANTE: Revisa los logs y el estado FÍSICO en la web de Bybit.")
        input("Presiona Enter para volver al menú principal...")
# =============== FIN ARCHIVO: runners/live_interactive_menus.py (COMPLETO) ===============