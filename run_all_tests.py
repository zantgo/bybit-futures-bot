# run_all_tests.py
# Este script está diseñado para probar exhaustivamente las funcionalidades del bot.

import time
import sys
import traceback
import datetime

# --- Configuración Inicial ---
sys.path.insert(0, '.')

try:
    from runner import assemble_dependencies
    from core import logging as logging_package
    from core.strategy.sm import api as sm_api
    from core.strategy.om import api as om_api
    from core.strategy.pm import api as pm_api
    import config
except ImportError as e:
    print(f"Error fatal al importar dependencias: {e}")
    traceback.print_exc()
    sys.exit(1)

# --- Funciones de Ayuda para las Pruebas ---

LATEST_SIMULATED_PRICE = 0.0

def setup_bot():
    """Inicializa el bot y devuelve las instancias necesarias."""
    print("--- 1. Configurando el Bot ---")
    logging_package.initialize_loggers()
    dependencies = assemble_dependencies()
    if not dependencies:
        raise RuntimeError("Fallo al ensamblar dependencias.")
    
    config.BOT_CONFIG["PAPER_TRADING_MODE"] = True
    print("Modo Paper Trading: ACTIVADO")

    BotController = dependencies['BotController']
    bot_controller = BotController(dependencies)
    
    print("Inicializando conexiones...")
    success, msg = bot_controller.initialize_connections()
    if not success:
        raise RuntimeError(f"Fallo al inicializar conexiones: {msg}")

    print("Creando sesión de trading...")
    session_manager = bot_controller.create_session()
    if not session_manager:
        raise RuntimeError("Fallo al crear la sesión de trading.")

    sm_api.init_sm_api(session_manager)
    ticker_instance = session_manager._ticker 

    print("Configuración completada.\n")
    return session_manager, ticker_instance

def run_ticks(ticker, price_sequence, delay=0.05):
    """Ejecuta una secuencia de ticks de precios simulados y guarda el último precio."""
    global LATEST_SIMULATED_PRICE
    for price in price_sequence:
        print(f"-> Tick: Precio simulado = {price}")
        LATEST_SIMULATED_PRICE = price
        ticker.run_simulation_tick(price)
        time.sleep(delay)

def print_summary():
    """Imprime un resumen del estado actual usando el último precio simulado."""
    global LATEST_SIMULATED_PRICE
    # --- CORRECCIÓN CLAVE: Inyectamos el precio simulado en la llamada al resumen ---
    summary = sm_api.get_session_summary(current_price=LATEST_SIMULATED_PRICE)
    
    if not summary or summary.get("error"):
        print("  Error obteniendo resumen.")
        return

    long_op = summary.get("operations_info", {}).get("long", {})
    short_op = summary.get("operations_info", {}).get("short", {})
    
    print("\n--- RESUMEN DE ESTADO ---")
    print(f"  Precio Mercado (Simulado): {summary.get('current_market_price', 'N/A'):.4f}")
    print(f"  PNL Sesión: {summary.get('total_session_pnl', 0):.4f} | ROI Sesión: {summary.get('total_session_roi', 0):.2f}%")
    print(f"  Op LONG: {long_op.get('estado')} | Pos: {summary.get('open_long_positions_count', 0)} | PNL: {summary.get('operation_long_pnl', 0):.4f}")
    print(f"  Op SHORT: {short_op.get('estado')} | Pos: {summary.get('open_short_positions_count', 0)} | PNL: {summary.get('operation_short_pnl', 0):.4f}")
    print("-------------------------\n")

def force_open_position(ticker, side: str, entry_price: float):
    """Forza la apertura de una posición bypaseando la lógica de la señal."""
    global LATEST_SIMULATED_PRICE
    LATEST_SIMULATED_PRICE = entry_price
    
    print(f"--- Forzando apertura {side.upper()} @ {entry_price} ---")
    ticker.run_simulation_tick(entry_price)
    
    pm_instance = sm_api._sm_instance._pm 
    pm_instance._open_logical_position(
        side=side,
        entry_price=entry_price,
        timestamp=datetime.datetime.now(datetime.timezone.utc)
    )
    time.sleep(0.1)
    print_summary()

# --- Escenarios de Prueba ---
def test_individual_sl_y_tsl(ticker):
    print("\n\n" + "="*80)
    print("--- INICIO PRUEBA: SL y TSL Individual por Posición ---".center(80))
    print("="*80)
    
    params = {
        'tendencia': 'LONG_ONLY', 'tamaño_posicion_base_usdt': 10.0, 'max_posiciones_logicas': 1,
        'apalancamiento': 10.0, 'sl_posicion_individual_pct': 5.0, 'tsl_activacion_pct': 2.0,
        'tsl_distancia_pct': 1.0, 'operational_margin': 10.0 * 1
    }
    om_api.create_or_update_operation('long', params)
    print("Operación LONG configurada con SL=5%, TSL_Act=2%, TSL_Dist=1%")
    force_open_position(ticker, 'long', 100)
    print("\n  ESCENARIO 1: Probando SL...")
    run_ticks(ticker, [98, 96, 94.9])
    print_summary()
    
    om_api.detener_operacion('long', forzar_cierre_posiciones=False)
    om_api.create_or_update_operation('long', params)
    
    print("\n  ESCENARIO 2: Probando TSL...")
    force_open_position(ticker, 'long', 100)
    run_ticks(ticker, [101, 102.1, 103, 105, 104, 103.9])
    print_summary()
    om_api.detener_operacion('long', forzar_cierre_posiciones=False)
    print("--- FIN PRUEBA: SL y TSL Individual ---")
    
def test_operation_roi_limits(ticker):
    print("\n\n" + "="*80)
    print("--- INICIO PRUEBA: Límites de ROI de Operación ---".center(80))
    print("="*80)
    
    params = {
        'tendencia': 'SHORT_ONLY', 'tamaño_posicion_base_usdt': 100.0, 'max_posiciones_logicas': 1,
        'apalancamiento': 10.0, 'sl_roi_pct': -15.0, 'tsl_roi_activacion_pct': 20.0,
        'tsl_roi_distancia_pct': 5.0, 'accion_al_finalizar': 'DETENER',
        'operational_margin': 100.0 * 1
    }
    om_api.create_or_update_operation('short', params)
    print("Operación SHORT configurada con SL-ROI=-15%, TSL-ROI_Act=20%, TSL-ROI_Dist=5%, Accion=DETENER")
    force_open_position(ticker, 'short', 200)
    print("\n  ESCENARIO 1: Probando SL-ROI...")
    run_ticks(ticker, [201, 202, 203.1])
    print_summary()

    om_api.detener_operacion('short', forzar_cierre_posiciones=False)
    om_api.create_or_update_operation('short', params)

    print("\n  ESCENARIO 2: Probando TSL-ROI...")
    force_open_position(ticker, 'short', 200)
    run_ticks(ticker, [197, 195.9, 194, 194.5, 195.1])
    print_summary()
    om_api.detener_operacion('short', forzar_cierre_posiciones=False)
    print("--- FIN PRUEBA: Límites de ROI de Operación ---")

def test_operation_quantity_limits(ticker):
    print("\n\n" + "="*80)
    print("--- INICIO PRUEBA: Límites de Cantidad de Operación ---".center(80))
    print("="*80)
    
    print("\n  ESCENARIO 1: Probando max_posiciones_logicas")
    params_max_pos = {
        'tendencia': 'LONG_ONLY', 'tamaño_posicion_base_usdt': 10.0, 'max_posiciones_logicas': 3,
        'apalancamiento': 10.0, 'operational_margin': 10.0 * 3
    }
    config.OPERATION_DEFAULTS["RISK"]["AVERAGING_DISTANCE_PCT_LONG"] = 0.5
    om_api.create_or_update_operation('long', params_max_pos)
    print("Op LONG configurada con max_posiciones_logicas = 3")
    force_open_position(ticker, 'long', 100)
    force_open_position(ticker, 'long', 99.4)
    force_open_position(ticker, 'long', 98.8)
    print("Intentando abrir 4ta posición (debería fallar)...")
    force_open_position(ticker, 'long', 98.2)
    
    om_api.detener_operacion('long', forzar_cierre_posiciones=True)
    config.OPERATION_DEFAULTS["RISK"]["AVERAGING_DISTANCE_PCT_LONG"] = 0.5
    press_enter_to_continue()
    
    print("\n  ESCENARIO 2: Probando max_comercios")
    params_max_trades = {
        'tendencia': 'LONG_ONLY', 'tamaño_posicion_base_usdt': 10.0, 'max_posiciones_logicas': 1,
        'apalancamiento': 10.0, 'sl_posicion_individual_pct': 5.0, 'max_comercios': 2,
        'accion_al_finalizar': 'PAUSAR', 'operational_margin': 10.0 * 1
    }
    om_api.create_or_update_operation('long', params_max_trades)
    print("Op LONG configurada con max_comercios = 2")
    
    print("Ejecutando Trade 1..."); force_open_position(ticker, 'long', 100); run_ticks(ticker, [94.9])
    print("Ejecutando Trade 2..."); force_open_position(ticker, 'long', 100); run_ticks(ticker, [94.9])
    print("Intentando abrir 3er trade (debería fallar)..."); force_open_position(ticker, 'long', 100)

    om_api.detener_operacion('long', forzar_cierre_posiciones=False)
    print("--- FIN PRUEBA: Límites de Cantidad ---")

def test_session_global_limits(ticker):
    print("\n\n" + "="*80)
    print("--- INICIO PRUEBA: Disyuntores Globales de Sesión ---".center(80))
    print("="*80)
    
    original_sl_enabled = config.SESSION_CONFIG["SESSION_LIMITS"]["ROI_SL"]["ENABLED"]
    original_sl_pct = config.SESSION_CONFIG["SESSION_LIMITS"]["ROI_SL"]["PERCENTAGE"]
    original_tp_enabled = config.SESSION_CONFIG["SESSION_LIMITS"]["ROI_TP"]["ENABLED"]
    original_tp_pct = config.SESSION_CONFIG["SESSION_LIMITS"]["ROI_TP"]["PERCENTAGE"]

    try:
        print("\n  ESCENARIO 1: Probando SL Global de Sesión")
        config.SESSION_CONFIG["SESSION_LIMITS"]["ROI_SL"]["ENABLED"] = True
        config.SESSION_CONFIG["SESSION_LIMITS"]["ROI_SL"]["PERCENTAGE"] = 5.0
        pm_api.set_global_stop_loss_pct(5.0)
        print("SL Global de Sesión activado en -5.0%")
        params_long = {'tendencia':'LONG_ONLY', 'tamaño_posicion_base_usdt': 100, 'max_posiciones_logicas': 1, 'apalancamiento': 1.0, 'operational_margin': 100}
        om_api.create_or_update_operation('long', params_long)
        force_open_position(ticker, 'long', 100)
        run_ticks(ticker, [94.9])
        print_summary()
        
        press_enter_to_continue()
        
        print("\n  ESCENARIO 2: Probando TP Global de Sesión")
        config.SESSION_CONFIG["SESSION_LIMITS"]["ROI_TP"]["ENABLED"] = True
        config.SESSION_CONFIG["SESSION_LIMITS"]["ROI_TP"]["PERCENTAGE"] = 10.0
        pm_api.set_global_take_profit_pct(10.0)
        print("TP Global de Sesión activado en +10.0%")
        
        om_api.detener_operacion('long', forzar_cierre_posiciones=True)
        om_api.create_or_update_operation('long', params_long)
        
        force_open_position(ticker, 'long', 100)
        run_ticks(ticker, [110.1])
        print("TP Global alcanzado. Intentando abrir una nueva posición (debería fallar)...")
        force_open_position(ticker, 'long', 105) 
        print_summary()

    finally:
        print("\nRestaurando configuración original de la sesión...")
        config.SESSION_CONFIG["SESSION_LIMITS"]["ROI_SL"]["ENABLED"] = original_sl_enabled
        config.SESSION_CONFIG["SESSION_LIMITS"]["ROI_SL"]["PERCENTAGE"] = original_sl_pct
        config.SESSION_CONFIG["SESSION_LIMITS"]["ROI_TP"]["ENABLED"] = original_tp_enabled
        config.SESSION_CONFIG["SESSION_LIMITS"]["ROI_TP"]["PERCENTAGE"] = original_tp_pct
        pm_api.set_global_stop_loss_pct(original_sl_pct if original_sl_enabled else 0.0)
        pm_api.set_global_take_profit_pct(original_tp_pct if original_tp_enabled else 0.0)
        om_api.detener_operacion('long', forzar_cierre_posiciones=True)
        om_api.detener_operacion('short', forzar_cierre_posiciones=True)
        print("--- FIN PRUEBA: Disyuntores Globales ---")

def main():
    session, ticker = setup_bot()
    try:
        test_individual_sl_y_tsl(ticker)
        press_enter_to_continue()
        test_operation_roi_limits(ticker)
        press_enter_to_continue()
        test_operation_quantity_limits(ticker)
        press_enter_to_continue()
        test_session_global_limits(ticker)
        press_enter_to_continue()
        print("\n\n" + "="*80)
        print("¡TODAS LAS PRUEBAS HAN FINALIZADO!".center(80))
        print("="*80)
    except Exception as e:
        print(f"\n\n!!! ERROR CRÍTICO DURANTE LA EJECUCIÓN DE PRUEBAS: {e} !!!")
        traceback.print_exc()
    finally:
        print("\n--- Finalizando Sesión de Prueba ---")
        if session:
            session.stop()
        logging_package.shutdown_loggers()

def press_enter_to_continue():
    input("\nPresiona Enter para la siguiente prueba...")

if __name__ == "__main__":
    main()