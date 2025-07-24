# Bybit Futures Bot - Versión 30+ (Modelo de Hitos y Tendencias)

Este es un bot de trading algorítmico avanzado para futuros de Bybit, diseñado con una arquitectura modular y una potente interfaz de usuario en la terminal (TUI) para un control total en tiempo real.

El bot opera bajo un modelo estratégico jerárquico:
-   **Sesión:** El ciclo de vida completo de una ejecución, con disyuntores de seguridad globales.
-   **Hitos (Milestones):** Reglas condicionales ("SI el precio cruza X...") que activan modos operativos.
-   **Tendencias (Trends):** Modos operativos con reglas específicas de riesgo y finalización que se ejecutan cuando un hito se activa.

---

## !! Advertencia de Seguridad y Riesgo !!

**EL TRADING DE FUTUROS CON APALANCAMIENTO ES EXTREMADAMENTE RIESGOSO Y PUEDE RESULTAR EN LA PÉRDIDA TOTAL DE SU CAPITAL.**

-   Este software se proporciona "tal cual", sin ninguna garantía.
-   El autor no se hace responsable de ninguna pérdida financiera.
-   **NUNCA** ejecute este bot en una cuenta real sin haberlo probado extensivamente en **TESTNET** (`UNIVERSAL_TESTNET_MODE = True` en `config.py`).
-   Comprenda completamente el código y los riesgos antes de depositar fondos reales.

---

## !!! IMPORTANTE: Checklist Antes de Cada Ejecución !!!

**SIEMPRE VERIFICA QUE TU CONFIGURACIÓN LOCAL COINCIDA CON LA DE LA PLATAFORMA DE BYBIT.**

-   **HEDGE MODE:** El bot está diseñado para operar exclusivamente en **Modo Hedge**. Asegúrate de que esta opción esté activada en Bybit para el par que vas a operar.
    -   *Cómo verificar:* En la interfaz de trading de Bybit, busca el icono de configuración (engranaje) y en "Preferencias de Trading" -> "Modo de Posición", selecciona "Modo Hedge".

-   **APALANCAMIENTO:** El valor de `POSITION_LEVERAGE` en tu archivo `config.py` debe ser **exactamente el mismo** que tienes configurado en la interfaz de Bybit para los lados Long y Short de ese símbolo.

-   **SÍMBOLO:** Confirma que el `TICKER_SYMBOL` en `config.py` (o el que selecciones en la TUI) es el par correcto que deseas operar.

-   **CAPITAL:** Asegúrate de que haya suficiente balance (USDT) en las subcuentas de `longs` y `shorts` para cubrir las operaciones que el bot pueda abrir.

---

## 1. Configuración Inicial (Solo una vez)

### 1.1. Prerrequisitos
-   Python 3.10 o superior.
-   Una cuenta en [Bybit](https://www.bybit.com/).

### 1.2. Pasos de Instalación
1.  **Clona el repositorio:**
    ```bash
    git clone <URL_DEL_REPOSITORIO>
    cd <NOMBRE_DEL_DIRECTORIO>
    ```
2.  **Crea y activa un entorno virtual:**
    ```bash
    python -m venv venv
    source venv/bin/activate  # En macOS/Linux
    # .\venv\Scripts\Activate.ps1 # En Windows PowerShell
    ```
3.  **Instala las dependencias:**
    ```bash
    pip install -r requirements.txt
    ```

### 1.3. Configuración de Cuentas y API en Bybit
El bot está diseñado para operar con subcuentas para un aislamiento de riesgo superior.

1.  **Crea Subcuentas en Bybit:** En tu panel de Bybit, ve a "Subcuentas" y crea tres subcuentas de tipo "Cuenta de Trading Unificado". Dales nombres descriptivos como:
    *   `longs`
    *   `shorts`
    *   `profit` (para acumular ganancias)
2.  **Genera Claves API:**
    *   **Cuenta Principal:** Crea una clave API con permisos de **"Leer/Escribir"** para **Activos -> Transferencia**. Esta clave es **esencial** para mover las ganancias a la subcuenta de `profit`.
    *   **Subcuentas (`longs`, `shorts`, `profit`):** Para cada una, crea una clave API con permisos de **"Leer/Escribir"** para **Contrato -> Trading Unificado**.
3.  **Obtén los UIDs:** En la sección de "Gestión de Subcuentas", anota el UID de cada una de tus subcuentas.

### 1.4. Configuración del Archivo `.env`
1.  En la raíz del proyecto, crea un archivo llamado `.env`.
2.  Copia, pega y rellena el siguiente contenido con tus claves y UIDs:

    ```dotenv
    # --- UIDs (Encuéntralos en la sección de Subcuentas de Bybit) ---
    BYBIT_LONGS_UID=1234567
    BYBIT_SHORTS_UID=2345678
    BYBIT_PROFIT_UID=3456789

    # --- Claves Cuenta Principal (SOLO para transferencias) ---
    BYBIT_MAIN_API_KEY="YOUR_MAIN_API_KEY"
    BYBIT_MAIN_API_SECRET="YOUR_MAIN_API_SECRET"

    # --- Claves Subcuenta Futuros Long ---
    BYBIT_LONGS_API_KEY="YOUR_LONGS_API_KEY"
    BYBIT_LONGS_API_SECRET="YOUR_LONGS_API_SECRET"

    # --- Claves Subcuenta Futuros Short ---
    BYBIT_SHORTS_API_KEY="YOUR_SHORTS_API_KEY"
    BYBIT_SHORTS_API_SECRET="YOUR_SHORTS_API_SECRET"

    # --- Claves Subcuenta Ganancias (para obtener el ticker) ---
    BYBIT_PROFIT_API_KEY="YOUR_PROFIT_API_KEY"
    BYBIT_PROFIT_API_SECRET="YOUR_PROFIT_API_SECRET"
    ```

### 1.5. Deposita Fondos
Desde tu Cuenta Principal en Bybit, transfiere los fondos (USDT) que deseas operar a tus subcuentas `longs` y `shorts`.

---

## 2. Ejecución y Uso del Bot

El bot se opera a través de una única interfaz interactiva.

### 2.1. Iniciar el Bot
Abre una terminal, activa tu entorno virtual (`source venv/bin/activate`) y ejecuta:
```bash
python main.py
```

### 2.2. Pantalla de Bienvenida
-   Verás una pantalla de bienvenida con un resumen de la configuración actual cargada desde `config.py`.
-   **[1] Iniciar Bot:** Comienza la sesión de trading.
-   **[2] Modificar configuración:** Te permite cambiar parámetros clave para la sesión actual **sin modificar permanentemente tu `config.py`**.
-   **[3] Salir:** Cierra el programa.

### 2.3. El Dashboard Principal
Una vez iniciado, el Dashboard es tu centro de control en tiempo real.
-   **Cabecera:** Muestra el ticker, el precio actual y el estado de la **Tendencia** activa (`LONG_ONLY`, `SHORT_ONLY` o `NEUTRAL`).
-   **Estado General:** PNL, ROI, capital inicial y duración de la sesión.
-   **Configuración:** Parámetros de riesgo y capital con los que está operando el bot.
-   **Cuentas Reales:** Balances actualizados de tus subcuentas.
-   **Posiciones:** Tablas detalladas de las posiciones lógicas abiertas.

### 2.4. Menú de Acciones
Desde el Dashboard, puedes acceder a las siguientes pantallas:

-   **[2] Gestionar Posiciones:** Visualiza en detalle las posiciones abiertas y ciérralas manualmente si es necesario (individualmente o todas a la vez).
-   **[3] Gestionar Hitos (Árbol de Decisiones):** El corazón de tu estrategia.
    -   **Crear Hito:** Define una condición de precio (`SI precio > X...`) y la **Tendencia** que se activará.
    -   **Configurar Tendencia:** Para cada hito, defines el modo (`LONG_ONLY`, etc.), el riesgo (SL/TS individual) y las condiciones de finalización (límite de trades, duración, TP/SL por ROI de la tendencia).
    -   **Anidar Hitos:** Puedes crear hitos que solo se activen después de que su "padre" se haya cumplido, creando árboles de decisión complejos.
-   **[4] Editar Configuración de Sesión:** Abre un editor para modificar los parámetros globales del bot en tiempo real (ej. cambiar el ticker, ajustar el apalancamiento, modificar los disyuntores de seguridad de la sesión).
-   **[5] Ver Logs en Tiempo Real:** Muestra los últimos 1000 mensajes de eventos del bot.

---

## 3. Parámetros Clave en `config.py`

Aunque muchos parámetros se pueden ajustar en la TUI, estos son los valores iniciales que el bot carga.

-   `UNIVERSAL_TESTNET_MODE`: `True` para operar en la Testnet de Bybit, `False` para dinero real. **¡EMPIEZA SIEMPRE CON `True`!**
-   `TICKER_SYMBOL`: El par de trading por defecto (ej. `"BTCUSDT"`).
-   `POSITION_LEVERAGE`: Apalancamiento. **Debe coincidir con tu configuración en la web de Bybit.**
-   `POSITION_BASE_SIZE_USDT`: El margen en USDT que se usará para cada nueva posición lógica.
-   `POSITION_MAX_LOGICAL_POSITIONS`: El número de "slots" u operaciones simultáneas por lado.
-   `SESSION_STOP_LOSS_ROI_PCT` / `SESSION_TAKE_PROFIT_ROI_PCT`: Disyuntores de seguridad. Si el ROI total de la sesión alcanza `+5.0%` o `-10.0%`, el bot detiene las operaciones.

## 4. Archivos de Log

El bot genera varios archivos en la carpeta `logs/` para auditoría y análisis:
-   `signals_log.jsonl`: Un registro de cada señal de trading generada.
-   `closed_positions.jsonl`: Un registro detallado de cada posición que se ha cerrado, incluyendo PNL.
-   `open_positions_snapshot.jsonl`: Una instantánea de las posiciones que quedaron abiertas al cerrar el bot.

Estos archivos están limitados a las últimas 1000 entradas para evitar consumir espacio en disco excesivo.