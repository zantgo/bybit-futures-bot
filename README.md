# Bybit Futures Bot - Versión 13 (Modo Automático y Gestión de Riesgo Mejorada)

!!! IMPORTANTE: LEE ESTO ANTES DE CADA EJECUCIÓN !!!

**SIEMPRE VERIFICA QUE LOS PARÁMETROS EN `config.py` Y `.env` CORRESPONDAN CON LA INFORMACIÓN EN EL NAVEGADOR DE BYBIT.**

-   **SÍMBOLO:** `TICKER_SYMBOL` debe coincidir con el par que operarás (ej. `BTCUSDT`).
-   **APALANCAMIENTO:** `POSITION_LEVERAGE` debe ser el mismo que tienes configurado en la web de Bybit para ese símbolo.
-   **CAPITAL:** Asegúrate de que hay suficiente balance en las subcuentas de `longs` y `shorts` para cubrir las operaciones.
-   **HEDGE MODE:** El bot está diseñado para **Hedge Mode**. Asegúrate de que esté activado en la configuración de futuros de Bybit para el par a operar. El bot intentará verificarlo, pero es mejor confirmarlo manualmente.

**PRUEBA SIEMPRE EL BOT CON LA OPCIÓN DE "PROBAR CICLO COMPLETO" ANTES DE INICIAR UNA SESIÓN DE TRADING REAL.**

---

## MANUAL DE USUARIO (v13)

### 1. Configuración Inicial (Solo una vez)

#### Pasos de Instalación
1.  **Navega a la raíz del proyecto:**
    ```bash
    cd ruta/a/tu/proyecto/DFE-Futures-Bot-B
    ```
2.  **Crea un entorno virtual:**
    ```bash
    python -m venv venv
    ```
3.  **Activa el entorno virtual:**
    *   **Windows (PowerShell):** `.\venv\Scripts\Activate.ps1`
    *   **macOS / Linux:** `source venv/bin/activate`
4.  **Instala las dependencias:**
    ```bash
    pip install -r requirements.txt
    ```

#### Configuración de Cuentas y API
1.  **Crea Subcuentas en Bybit:** Para un aislamiento de riesgo óptimo, se recomienda crear tres subcuentas además de tu cuenta principal:
    *   Una para posiciones `LONG`.
    *   Una para posiciones `SHORT`.
    *   Una para acumular las `GANANCIAS` (profit).
2.  **Genera Claves API:**
    *   **Cuenta Principal:** Genera una clave API con permisos de "Leer/Escribir" para **Transferencia entre Subcuentas**.
    *   **Subcuentas (Long, Short, Profit):** Genera una clave API para cada una con permisos de "Leer/Escribir" para **Contrato -> Trading Unificado** y **Activos**.
3.  **Configura el archivo `.env`:**
    *   Crea un archivo llamado `.env` en la raíz del proyecto.
    *   Copia y pega el siguiente contenido y rellénalo con tus UIDs y claves API.

    ```dotenv
    # IN .env FILE:

    # --- UIDs (Encuéntralos en la sección de Subcuentas de Bybit) ---
    BYBIT_LONGS_UID=
    BYBIT_SHORTS_UID=
    BYBIT_PROFIT_UID=

    # --- Claves Cuenta Principal (NECESARIAS PARA TRANSFERENCIAS) ---
    BYBIT_MAIN_API_KEY=""
    BYBIT_MAIN_API_SECRET=""

    # --- Claves Subcuenta Futuros Long ---
    BYBIT_LONGS_API_KEY=""
    BYBIT_LONGS_API_SECRET=""

    # --- Claves Subcuenta Futuros Short ---
    BYBIT_SHORTS_API_KEY=""
    BYBIT_SHORTS_API_SECRET=""

    # --- Claves Subcuenta Ganancias ---
    BYBIT_PROFIT_API_KEY=""
    BYBIT_PROFIT_API_SECRET=""
    ```
4.  **Deposita Fondos:** Transfiere USDT a tus subcuentas `longs` y `shorts` desde tu cuenta principal.

### 2. Configuración del Bot (`config.py`)

Abre el archivo `config.py` y ajusta los parámetros según tu estrategia. Los más importantes son:

-   `UNIVERSAL_TESTNET_MODE`: Ponlo en `True` para usar la testnet de Bybit.
-   `TICKER_SYMBOL`: El par a operar (ej. `"BTCUSDT"`).
-   `POSITION_LEVERAGE`: Tu apalancamiento.
-   `POSITION_BASE_SIZE_USDT`: El margen en USDT para cada posición lógica individual.
-   `POSITION_MAX_LOGICAL_POSITIONS`: El número de "slots" o posiciones lógicas que puede abrir por lado.
-   **`POSITION_PHYSICAL_STOP_LOSS_PCT`**: **¡MUY IMPORTANTE!** El porcentaje de pérdida sobre la posición física total que activará el cierre de emergencia de todas las posiciones de ese lado. **Ej: `5.0` para un 5% de Stop Loss.**

### 3. Modos de Operación

Puedes ejecutar el bot de tres maneras.

#### A. Modo Automático (Recomendado)

Este modo utiliza una estrategia de alto nivel (UT Bot Alerts) para decidir la dirección general del mercado (alcista o bajista) y una estrategia de bajo nivel para ejecutar las entradas.

1.  **En `config.py`, establece:**
    ```python
    AUTOMATIC_MODE_ENABLED = True
    ```
2.  **Ajusta los parámetros del UT Bot:**
    *   `UT_BOT_SIGNAL_INTERVAL_SECONDS`: Frecuencia de la señal de alto nivel (ej. `3600` para 1 hora).
    *   `UT_BOT_KEY_VALUE`, `UT_BOT_ATR_PERIOD`: Parámetros del indicador.
    *   `AUTOMATIC_FLIP_OPENS_NEW_POSITIONS`: `True` para reabrir posiciones al cambiar de dirección.
    *   `AUTOMATIC_SL_COOLDOWN_SECONDS`: Tiempo de espera después de un Stop Loss.
3.  **Ejecuta el bot:**
    ```bash
    python main.py
    ```

#### B. Modo Live Interactivo

Este modo ejecuta solo la estrategia de bajo nivel. Tú decides si operar en `LONG_ONLY`, `SHORT_ONLY` o `BOTH`.

1.  **En `config.py`, establece:**
    ```python
    AUTOMATIC_MODE_ENABLED = False
    ```
2.  **Ejecuta el bot y sigue los menús:**
    ```bash
    python main.py
    ```
    *   Selecciona "Modo Live Interactivo".
    *   Selecciona el modo de trading para la sesión (LONG_ONLY, etc.).
    *   Define el tamaño base y los slots.

#### C. Modo Backtesting

Simula la estrategia de bajo nivel usando datos históricos.

1.  **Prepara tus datos:** Asegúrate de tener un archivo CSV en la carpeta `data/` con columnas de `timestamp` y `close`.
2.  **Ejecuta el bot y sigue los menús:**
    ```bash
    python main.py
    ```
    *   Selecciona "Modo Backtesting".

### 4. Intervención Manual (Durante la ejecución Live o Automática)

Mientras el bot está corriendo, puedes presionar la tecla `m` y luego `Enter` para acceder al menú de intervención.

-   **Ver Estadísticas en Vivo:** Muestra un resumen del rendimiento actual (PNL, ROI, etc.).
-   **Cambiar Visualización de Ticks:** Activa o desactiva la impresión de información en la consola para cada tick.
-   **Ajustar Slots Máximos:** Aumenta o disminuye el número de posiciones lógicas que el bot puede abrir.
-   **Cambiar Tamaño Base:** Modifica el margen que se usará para las *próximas* posiciones que se abran. No afecta a las que ya están abiertas.

---

### Mantenimiento y Buenas Prácticas

-   **Revisión Periódica:** Aunque el bot es automático, revisa su estado y el de tus cuentas en Bybit periódicamente.
-   **Logs:** La carpeta `logs/` contiene un registro detallado de todas las señales y posiciones cerradas. Revísala para analizar el rendimiento y depurar problemas.
-   **Reportes:** La carpeta `result/` contendrá un archivo de texto con el resumen final de cada ejecución y un gráfico si se ejecutó en modo backtest.