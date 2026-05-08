# SmartX HCG — Sistema de Triaje Médico Inteligente

Sistema de triaje automatizado basado en IA para el **Hospital Civil de Guadalajara (HCG)**. Clasifica en tiempo real la urgencia de cada paciente en tres niveles (**ROJO / AMARILLO / VERDE**) usando un pipeline de inferencia de 8 pasos con XGBoost, explicabilidad SHAP y catálogo CIE-10. Los resultados se persisten en **Supabase** (PostgreSQL en la nube).

**Versión:** v1.0-piloto — Mayo 2026  
**Unidades de atención:** `HCG_URGENCIAS` · `HCG_MED_INTERNA`  
**Normativas:** NOM-004-SSA3-2012 · NOM-024-SSA3-2012 · LFPDPPP

---

## Tabla de contenidos

1. [Arquitectura y stack tecnológico](#arquitectura-y-stack-tecnológico)
2. [Estructura del proyecto](#estructura-del-proyecto)
3. [Instalación](#instalación)
4. [Configuración](#configuración)
5. [Base de datos — Supabase](#base-de-datos--supabase)
6. [Uso](#uso)
7. [API — Endpoints y contratos](#api--endpoints-y-contratos)
8. [Pipeline de inferencia](#pipeline-de-inferencia)
9. [Dataset y modelos ML](#dataset-y-modelos-ml)
10. [Frontend](#frontend)
11. [Seguridad](#seguridad)
12. [Variables clínicas](#variables-clínicas)
13. [Normativas implementadas](#normativas-implementadas)
14. [Registro de cambios](#registro-de-cambios)

---

## Arquitectura y stack tecnológico

```
┌──────────────────────────────────────────────────────────┐
│                      FRONTEND                            │
│   Dashboard HTML + Tailwind (standalone, producción)     │
│   Streamlit (desarrollo)                                 │
└───────────────────┬──────────────────────────────────────┘
                    │ HTTP / REST
┌───────────────────▼──────────────────────────────────────┐
│                  BACKEND — FastAPI                        │
│   Uvicorn ASGI  │  Pydantic v2 (validación estricta)     │
│   CORS: lista blanca de orígenes permitidos              │
└───────────────────┬──────────────────────────────────────┘
                    │
        ┌───────────┴───────────┐
        ▼                       ▼
┌───────────────┐     ┌─────────────────────┐
│ MOTOR XGBoost │     │  SUPABASE (nube)     │
│ 8-step pipeline│     │  · tabla inferencias │
│ SHAP · CIE-10  │     │  · tabla auditoria   │
└───────────────┘     └─────────────────────┘
```

| Capa | Tecnología | Versión |
|------|-----------|---------|
| Lenguaje | Python | 3.14 |
| API REST | FastAPI | ≥ 0.115.0 |
| Servidor ASGI | Uvicorn | ≥ 0.30.0 |
| Validación | Pydantic | ≥ 2.10.0 |
| Clasificación ML | XGBoost | 3.2.0 |
| Modelos ensemble | scikit-learn | 1.4.1 |
| Explicabilidad | SHAP | 0.44.1 |
| Datos tabulares | pandas | 2.1.4 |
| Álgebra lineal | NumPy | 1.26.4 |
| Serialización | joblib | 1.3.2 |
| Base de datos | Supabase (PostgreSQL) | ≥ 2.9.0 SDK |
| Dashboard web | Streamlit | 1.31.1 |
| Lectura Excel | openpyxl | 3.1.0 |
| Variables entorno | python-dotenv | 1.0.0 |

---

## Estructura del proyecto

```
SmartX_HCG/
│
├── README.md                          ← Este archivo
├── AGENTS.md
│
├── 01_Arquitectura_Sistema/           ← Diagramas y documentos de arquitectura
├── 02_Base_de_Datos/                  ← Esquema BD, diagrama ER, variables
└── 03_Prototipo__MVP/                 ← Documentos del prototipo MVP
│
└── 04_Codigo/                         ← Todo el código fuente
    │
    ├── smartx_api.py                  ← API FastAPI — PUNTO DE ENTRADA
    ├── smartx_motor_inferencia.py     ← Motor de inferencia (pipeline 8 pasos)
    ├── smartx_excel_a_csv.py          ← Utilidad de exportación Excel → CSV
    ├── requirements.txt               ← Dependencias Python
    ├── supabase_schema.sql            ← Schema SQL — ejecutar en Supabase
    ├── .env.example                   ← Plantilla de variables (sin secretos)
    ├── .gitignore                     ← Protege .env de ser versionado
    │
    ├── assets/
    │   └── models/
    │       ├── smartx_model_v2.pkl    ← Modelo XGBoost entrenado (408 KB)
    │       └── encoder_motivo.pkl     ← LabelEncoder motivo_consulta (722 B)
    │
    ├── datasets/                      ← Dataset CANÓNICO de entrenamiento
    │   ├── dataset_SmartX_2200_casos_con_ruido.xlsx  ← Fuente del modelo actual
    │   ├── entrenamiento.csv          (1,540 filas × 20 cols)
    │   ├── validacion.csv             (330 filas)
    │   ├── prueba.csv                 (330 filas)
    │   ├── etiquetas_*.csv            ← Labels por split
    │   └── *.csv                      ← Metadatos y catálogos
    │
    ├── models/
    │   └── clasificacion.py           ← Script de entrenamiento XGBoost
    │
    ├── docs/
    │   ├── SmartX_Dataset_Integration_Resumen.md
    │   ├── SmartX_Frontend_Integration_Guide.md
    │   └── SmartX_Mermaid_Diagramas.md
    │
    ├── frontend/
    │   ├── smartx_dashboard.html      ← Dashboard de producción (standalone)
    │   └── streamlit_app.py           ← UI de desarrollo (http://localhost:8501)
    │
    ├── scripts/                       ← Versiones históricas (vacía — limpiada en auditoría)
    │
    └── _archivo/                      ← Código archivado — no usar en producción
        └── backend/
            ├── app/routers/triaje.py  ← Router modular (referencia futura)
            └── motor_inferencia/smartx_motor.py
```

> **Dataset canónico:** `datasets/dataset_SmartX_2200_casos_con_ruido.xlsx` (MD5: `0a70639125e3a512d4474507b8eeee2b`).
> Es el archivo usado para entrenar `smartx_model_v2.pkl`. Verificado en auditoría Mayo 2026.
> La copia alternativa en `data/` fue eliminada tras confirmación de divergencia (7 KB diferente).

---

## Instalación

```powershell
# 1. Crear y activar entorno virtual
python -m venv .venv
.venv\Scripts\Activate.ps1      # PowerShell (Windows)
# source .venv/bin/activate     # macOS/Linux

# 2. Instalar dependencias (desde 04_Codigo/)
cd 04_Codigo
pip install -r requirements.txt
```

---

## Configuración

```powershell
# Copiar plantilla y rellenar con valores reales
cp .env.example .env
```

Variables requeridas en `.env`:

```env
# Backend
SMARTX_API_URL=http://127.0.0.1:8000
FASTAPI_PORT=8000
FASTAPI_ENV=development

# Supabase (obtener en: Supabase → Settings → API)
SUPABASE_URL=https://TU_PROJECT_ID.supabase.co
SUPABASE_PUBLISHABLE_KEY=sb_publishable_XXXX   # Para el dashboard (browser)
SUPABASE_SECRET_KEY=sb_secret_XXXX             # Para FastAPI (servidor — nunca exponer)
```

> ⚠️ **Seguridad:** El archivo `.env` está en `.gitignore` y **nunca debe subirse a git**.
> La `SUPABASE_SECRET_KEY` tiene acceso completo a la base de datos.

---

## Base de datos — Supabase

### Setup inicial (una sola vez)

1. Abre tu proyecto en [supabase.com](https://supabase.com)
2. Ve a **SQL Editor**
3. Pega el contenido de `04_Codigo/supabase_schema.sql` y ejecuta con **Run**

Esto crea:
- **`inferencias`** — almacena cada clasificación (inputs + resultado IA)
- **`auditoria_api`** — registro de todas las peticiones HTTP (NOM-024)

### Tablas principales

```sql
-- inferencias: una fila por cada triaje procesado
id_consulta       UUID  -- identificador único de la consulta
id_paciente       TEXT  -- UUID seudonimizado del paciente
nivel_ia          TEXT  -- 'rojo' | 'amarillo' | 'verde'
fuente_nivel      TEXT  -- origen de la clasificación
probabilidad_rojo FLOAT
probabilidad_amarillo FLOAT
probabilidad_verde FLOAT
alerta_critica    BOOL
created_at        TIMESTAMPTZ
-- ... + 20 features clínicas
```

---

## Uso

### 1. Ejecutar la API

```powershell
cd 04_Codigo
uvicorn smartx_api:app --reload --port 8000
```

Disponible en `http://localhost:8000`  
Documentación Swagger: `http://localhost:8000/docs`

### 2. Dashboard HTML (producción)

Abrir en el navegador:
```
04_Codigo/frontend/smartx_dashboard.html
```

Al abrirse, carga automáticamente los últimos 50 triajes desde Supabase. Requiere que la API esté corriendo en `localhost:8000`.

### 3. Interfaz Streamlit (desarrollo)

```powershell
cd 04_Codigo/frontend
streamlit run streamlit_app.py
```

Disponible en `http://localhost:8501`.

### 4. Reentrenar el modelo XGBoost

```powershell
cd 04_Codigo/models
python clasificacion.py
```

Genera `../assets/models/smartx_model_v2.pkl` y `../assets/models/encoder_motivo.pkl`.  
Dataset de entrada: `../datasets/dataset_SmartX_2200_casos_con_ruido.xlsx`

---

## API — Endpoints y contratos

### Sistema

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET` | `/` | Health check — incluye estado de Supabase |
| `GET` | `/health` | Estado del motor de inferencia |

### Triaje

| Método | Ruta | Descripción |
|--------|------|-------------|
| `POST` | `/api/v1/inferencia` | **Endpoint principal** — clasificar urgencia |
| `GET` | `/api/v1/inferencias/recientes?limite=50` | Últimas N inferencias (para el dashboard) |
| `GET` | `/api/v1/paciente/{id}/historial` | Historial de visitas del paciente |

### Catálogos

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET` | `/api/v1/catalogo/escenarios` | Catálogo CIE-10 por nivel |
| `GET` | `/api/v1/catalogo/motivos` | Lista de motivos de consulta válidos |

---

### Modelo de entrada — `SintomasInput`

Solo `edad` es requerido. Todos los demás tienen valores por defecto seguros.

```json
{
  "edad": 45,
  "sexo_biologico": "M",
  "embarazo": false,
  "motivo_consulta": "Fiebre sin foco claro",
  "tiempo_evolucion_horas": 12,
  "intensidad_sintoma": 6,

  "fiebre_reportada": true,
  "tos": false,
  "dificultad_respiratoria": false,
  "dolor_toracico": false,
  "dolor_al_orinar": false,
  "sangrado_activo": false,
  "confusion": false,
  "disminucion_movimientos_fetales": false,

  "redflag_disnea_severa": false,
  "redflag_sangrado_abundante": false,
  "redflag_deficit_neurologico_subito": false,
  "redflag_dolor_toracico_opresivo_con_sudoracion": false,

  "peso_kg": 75.0,
  "talla_cm": 170.0,
  "antecedentes_riesgo": "Hipertensión",
  "sintomas_digestivos": "Ninguno",
  "sintomas_texto": "Fiebre de 38.5 °C desde hace 12 horas con malestar general"
}
```

**Validaciones:**
- `edad`: 0–120
- `sexo_biologico`: `"M"` | `"F"`
- `motivo_consulta`: uno de los 10 valores del catálogo
- `intensidad_sintoma`: 0–10 (escala EVA)
- `peso_kg`: 1.0–300.0 (opcional)
- `talla_cm`: 30.0–250.0 (opcional)
- `sintomas_texto`: mínimo 10 caracteres si se envía (opcional)

**Catálogo de motivos válidos:**
`Dificultad respiratoria` · `Dolor abdominal` · `Dolor de cabeza` · `Dolor torácico` ·
`Embarazo o síntoma relacionado con embarazo` · `Fiebre sin foco claro` · `Mareo o desmayo` ·
`Problema gastrointestinal` · `Problema urinario` · `Tos o síntomas respiratorios`

---

### Modelo de salida

```json
{
  "nivel_ia": "amarillo",
  "fuente_nivel": "XGBoost",
  "probabilidades": {
    "rojo": 0.12,
    "amarillo": 0.71,
    "verde": 0.17
  },
  "escenarios": [
    {
      "cie10": "R07",
      "descripcion": "Dolor torácico no especificado",
      "probabilidad_relativa": "alta"
    }
  ],
  "explicacion_shap": "La intensidad del síntoma (EVA 6) y la fiebre reportada...",
  "alerta_critica": false,
  "alertas_detalle": [],
  "imc_calculado": 25.95,
  "modelo_version": "xgboost-v2.0-hcg-piloto",
  "tiempo_procesamiento_ms": 43
}
```

**Valores de `fuente_nivel`:**
- `regla_critica` — bypass por redflag (sin ML)
- `XGBoost` — clasificación por modelo ML
- `XGBoost+conservadurismo` — regla de seguridad aplicada tras el modelo

---

## Pipeline de inferencia

```
Entrada (SintomasInput)
        │
        ▼
1. ALERTAS CRÍTICAS ─── Revisa 4 redflags → ROJO inmediato si cualquiera = true
        │                (redflag_disnea_severa, redflag_sangrado_abundante,
        │                 redflag_deficit_neurologico_subito,
        │                 redflag_dolor_toracico_opresivo_con_sudoracion)
        ▼
2. VECTOR DE FEATURES ── Codifica 17 variables al formato XGBoost
        │                (incluye LabelEncoding de motivo_consulta)
        ▼
3. INFERENCIA XGBoost ── Produce p(rojo), p(amarillo), p(verde)
        │
        ▼
4. CONSERVADURISMO ────── Si p(rojo) ≥ 30% con nivel amarillo → escala a rojo
        │                Si p(amarillo) ≥ 30% con nivel verde → escala a amarillo
        ▼
5. SHAP (mock) ─────────── Top-3 variables por importancia del modelo
        │
        ▼
6. ESCENARIOS CIE-10 ───── 3 diagnósticos diferenciales por nivel
        │
        ▼
7. EXPLICACIÓN NL ──────── Texto en español explicando la decisión
        │
        ▼
8. OUTPUT + HASH ───────── JSON + SHA-256 de trazabilidad (NOM-024)
                            → INSERT en tabla Supabase `inferencias`
```

El motor es **determinístico**: mismas entradas → misma salida siempre.

---

## Dataset y modelos ML

| Atributo | Valor |
|----------|-------|
| Archivo canónico | `datasets/dataset_SmartX_2200_casos_con_ruido.xlsx` |
| Total de casos | 2,200 pacientes sintéticos con ruido controlado |
| Verde (estable) | 655 casos — 35% |
| Amarillo (prioritario) | 748 casos — 40% |
| Rojo (crítico) | 467 casos — 25% |
| Features del modelo | 17 (datos demográficos + síntomas binarios) |
| Accuracy reportada | 87.6% |
| Modelo en producción | `assets/models/smartx_model_v2.pkl` (XGBoost) |

> **Nota:** El dataset en `datasets/` es la versión canónica usada para el entrenamiento actual.
> La carpeta `data/` contiene una copia alternativa — **no usar para reentrenamiento**
> sin verificar que coincide byte a byte con el canónico.

---

## Frontend

### Dashboard HTML (`frontend/smartx_dashboard.html`) — Producción

- Carga los últimos 50 triajes desde Supabase al iniciar
- Grid de pacientes en tiempo real ordenado por severidad
- Estadísticas: CRÍTICOS · URGENTES · ESTABLES · TOTAL
- Formulario de nuevo triaje con 4 banderas rojas (bypass automático)
- Animación pulsante para nivel ROJO
- Panel de detalle con escenarios CIE-10 y explicación SHAP
- Notificaciones emergentes con sonido de alerta

**Tecnología:** HTML5 · Tailwind CSS · Font Awesome · JavaScript vanilla

**Conexión:** `http://localhost:8000` (API local) + Supabase REST (clave publishable)

### Streamlit (`frontend/streamlit_app.py`) — Desarrollo

Interfaz rápida de desarrollo. Requiere la API corriendo en `localhost:8000`.

---

## Seguridad

### Medidas implementadas

| Área | Medida |
|------|--------|
| **Secretos** | `.env` en `.gitignore`; `.env.example` sin valores reales |
| **CORS** | Lista blanca: `localhost:8000`, `localhost:8501` (no `*`) |
| **Validación** | Pydantic v2 con rangos clínicos en todos los campos |
| **Auditoría** | Middleware registra cada petición en `auditoria_api` (Supabase) |
| **Trazabilidad** | SHA-256 por resultado + UUID seudonimizado por paciente |
| **RLS** | Row Level Security habilitado en tablas Supabase |

### Pendiente de atención

| Severidad | Issue |
|-----------|-------|
| 🔴 CRÍTICO | Rotar `SUPABASE_SECRET_KEY` — estuvo expuesta en historial git |
| 🟡 MEDIO | Verificar integridad de `.pkl` con hash SHA-256 al cargar |
| 🟡 MEDIO | Agregar autenticación JWT en endpoints de escritura |
| 🟡 BAJO | El fallback de `motivo_consulta` no se registra en auditoría |

### Rotar la clave de Supabase (acción requerida)

```
Supabase → Settings → API → Secret keys → Revoke → New secret key
```

Luego actualiza `.env` con la nueva clave.

---

## Variables clínicas

### Las 4 banderas rojas — bypass inmediato a ROJO

| Campo | Condición clínica |
|-------|------------------|
| `redflag_disnea_severa` | Disnea severa con SpO₂ < 90% |
| `redflag_sangrado_abundante` | Sangrado activo abundante |
| `redflag_deficit_neurologico_subito` | Déficit neurológico súbito (AVC probable) |
| `redflag_dolor_toracico_opresivo_con_sudoracion` | IAM probable |

Cuando cualquiera es `true`, el modelo ML **no se ejecuta** y el nivel queda en `rojo` con `fuente_nivel = regla_critica`.

### Variables demográficas y clínicas (17 features del modelo)

| Variable | Tipo | Rango / Valores |
|----------|------|----------------|
| `edad` | int | 0 – 120 |
| `embarazo` | bool | — |
| `motivo_consulta` | enum | 10 valores del catálogo |
| `tiempo_evolucion_horas` | int | ≥ 0 |
| `intensidad_sintoma` | int | 0 – 10 (EVA) |
| `fiebre_reportada` | bool | — |
| `tos` | bool | — |
| `dificultad_respiratoria` | bool | — |
| `dolor_toracico` | bool | — |
| `dolor_al_orinar` | bool | — |
| `sangrado_activo` | bool | — |
| `confusion` | bool | Alteración de consciencia |
| `disminucion_movimientos_fetales` | bool | — |
| `redflag_disnea_severa` | bool | Bandera roja |
| `redflag_sangrado_abundante` | bool | Bandera roja |
| `redflag_deficit_neurologico_subito` | bool | Bandera roja |
| `redflag_dolor_toracico_opresivo_con_sudoracion` | bool | Bandera roja |

---

## Normativas implementadas

| Norma | Aplicación en SmartX |
|-------|---------------------|
| **NOM-004-SSA3-2012** | Integridad del dato clínico; UUID seudonimizado; validación de rangos clínicos |
| **NOM-024-SSA3-2012** | Hash SHA-256 por resultado; middleware de auditoría en `auditoria_api`; trazabilidad completa |
| **LFPDPPP** | Sin nombre, NSS ni datos identificadores en el pipeline; seudonimización completa |

---

## Registro de cambios

### v1.0-piloto — Mayo 2026

**Integración Supabase:**
- Persistencia de triajes en tabla `inferencias`
- Auditoría de peticiones en tabla `auditoria_api`
- Dashboard carga historial desde Supabase al iniciar
- Nuevo endpoint `GET /api/v1/inferencias/recientes`

**Seguridad (hardening):**
- CORS cambiado de `["*"]` a lista blanca de orígenes (`localhost:8000`, `localhost:8501`)
- Excepción silenciada en middleware de auditoría reemplazada por `logger.warning`
- Validación de `sintomas_texto`: mínimo 10 caracteres, máximo 2000
- Validación de `antecedentes_riesgo` y `sintomas_digestivos`: máximo 500 caracteres
- Creado `.gitignore` — `.env` ya no se versiona
- Creado `.env.example` sin secretos para uso seguro en equipos

**Corrección de bug (dashboard):**
- `buildPayload()` enviaba campos incorrectos (`disnea_presente`, `fiebre_presente`, etc.)
  que no coincidían con el contrato de `SintomasInput`. Corregido a nombres exactos del dataset.

**API (expansión de respuesta):**
- `POST /api/v1/inferencia` ahora devuelve `escenarios`, `explicacion_shap`,
  `alerta_critica`, `alertas_detalle`, `imc_calculado` además del nivel y probabilidades

---

## Documentación adicional

| Documento | Ubicación | Contenido |
|-----------|-----------|-----------|
| Schema SQL | `04_Codigo/supabase_schema.sql` | Tablas, índices y políticas RLS |
| Integración dataset | `04_Codigo/docs/SmartX_Dataset_Integration_Resumen.md` | Performance 87.6% |
| Guía frontend | `04_Codigo/docs/SmartX_Frontend_Integration_Guide.md` | Conexión dashboard-API |
| Diagramas Mermaid | `04_Codigo/docs/SmartX_Mermaid_Diagramas.md` | Flujos y ER |
| Arquitectura IA | `01_Arquitectura_Sistema/SmartX_Arquitectura_IA.docx` | Diseño del sistema |
| Esquema BD | `02_Base_de_Datos/SmartX_2_Esquema_BD.docx` | Tablas y relaciones |
| Diagrama ER | `02_Base_de_Datos/SmartX_3_ER_Diagrama.html` | Entidad-relación interactivo |
