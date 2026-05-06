# SmartX HCG — Sistema de Triaje Médico Inteligente

Sistema de triaje automatizado basado en IA para el Hospital Civil de Guadalajara (HCG). Clasifica en tiempo real la urgencia de cada paciente en tres niveles (ROJO / AMARILLO / VERDE) utilizando un pipeline de inferencia de 8 pasos con XGBoost, explicabilidad SHAP y catálogo CIE-10.

---

## Tabla de contenidos

1. [Descripción del sistema](#descripción-del-sistema)
2. [Arquitectura y stack tecnológico](#arquitectura-y-stack-tecnológico)
3. [Estructura del proyecto](#estructura-del-proyecto)
4. [Instalación](#instalación)
5. [Configuración](#configuración)
6. [Uso](#uso)
7. [API — Endpoints y contratos](#api--endpoints-y-contratos)
8. [Pipeline de inferencia](#pipeline-de-inferencia)
9. [Dataset y modelos ML](#dataset-y-modelos-ml)
10. [Frontend](#frontend)
11. [Variables clínicas](#variables-clínicas)
12. [Catálogo de escenarios CIE-10](#catálogo-de-escenarios-cie-10)
13. [Normativas implementadas](#normativas-implementadas)
14. [Documentación adicional](#documentación-adicional)

---

## Descripción del sistema

SmartX HCG recibe un JSON con los síntomas y datos clínicos de un paciente, ejecuta un motor de inferencia determinístico y devuelve:

- **Nivel de urgencia:** `rojo` (crítico) · `amarillo` (prioritario) · `verde` (estable)
- **Probabilidades:** puntuación continua por cada nivel
- **Diagnósticos diferenciales:** 3 escenarios CIE-10 con especialidad sugerida
- **Explicabilidad SHAP:** top-3 variables que influyeron en la decisión
- **Metadatos de trazabilidad:** versión del modelo, latencia, hash de integridad (NOM-024)

**Versión piloto:** v1.0 — Febrero 2026  
**Unidades de atención:** `HCG_URGENCIAS` · `HCG_MED_INTERNA`

---

## Arquitectura y stack tecnológico

```
┌─────────────────────────────────────────────────────────┐
│                        FRONTEND                         │
│   Streamlit (desarrollo)  │  HTML + Tailwind (standalone)│
│   React JSX (componentes) │  Font Awesome (iconografía)  │
└───────────────────┬─────────────────────────────────────┘
                    │ HTTP / REST
┌───────────────────▼─────────────────────────────────────┐
│                   BACKEND — FastAPI                     │
│   Uvicorn ASGI  │  Pydantic v2 (validación)             │
│   CORS habilitado (desarrollo: localhost)               │
└───────────────────┬─────────────────────────────────────┘
                    │
┌───────────────────▼─────────────────────────────────────┐
│             MOTOR DE INFERENCIA (8 pasos)               │
│   XGBoost  │  Random Forest  │  SHAP  │  Catálogo CIE-10│
│   joblib (serialización .pkl)                           │
└─────────────────────────────────────────────────────────┘
```

| Capa | Tecnología | Versión |
|------|-----------|---------|
| Lenguaje | Python | 3.14 |
| API REST | FastAPI | ≥ 0.115.0 (instalada 0.136.1) |
| Servidor ASGI | Uvicorn | ≥ 0.30.0 (instalada 0.46.0) |
| Validación | Pydantic | ≥ 2.10.0 (instalada 2.12.5) |
| Clasificación ML | XGBoost | 3.2.0 |
| Modelos ensemble | scikit-learn | 1.4.1 |
| Explicabilidad | SHAP | 0.44.1 |
| Datos tabulares | pandas | 2.1.4 |
| Álgebra lineal | NumPy | 1.26.4 |
| Serialización | joblib | 1.3.2 |
| Dashboard web | Streamlit | 1.31.1 |
| ORM SQL | SQLAlchemy | 2.0.25 |
| Lectura Excel | openpyxl | 3.1.0 |
| Variables entorno | python-dotenv | 1.0.0 |
| Cliente HTTP | requests | 2.31.0 |

---

## Estructura del proyecto

```
SmartX_HCG/
│
├── README.md
├── AGENTS.md
│
├── 01_Arquitectura_Sistema/
│   ├── SmartX_Arquitectura_IA.docx
│   ├── SmartX_Flujo_Logico (1).drawio
│   └── SmartX_Flujo_Logico_Diagrama.docx
│
├── 02_Base_de_Datos/
│   ├── SmartX_1_Flujo_Variables.docx
│   ├── SmartX_1b_Diccionario_Abreviaturas.docx
│   ├── SmartX_2_Esquema_BD.docx
│   ├── SmartX_3_ER_Diagrama.html
│   └── SmartX_4_Almacenamiento_Historial_Clinico.docx
│
├── 03_Prototipo__MVP/
│   ├── SmartX_P1_Prototipo_IA.docx
│   ├── SmartX_P2_Diagrama_Flujo.docx
│   ├── SmartX_P3_Dataset_Modelo.docx
│   └── SmartX_P4_Funcionamiento.docx
│
└── 04_Codigo/
    │
    ├── smartx_api.py                  # API FastAPI principal — punto de entrada
    ├── smartx_motor_inferencia.py     # Motor de inferencia activo (pipeline 8 pasos)
    ├── smartx_dashboard.html          # Dashboard HTML standalone (raíz)
    ├── smartx_dashboard.jsx           # Componentes React raíz
    ├── requirements.txt               # Dependencias Python
    ├── README.md                      # Documentación técnica del código
    ├── .env.example                   # Plantilla de variables de entorno
    │
    ├── assets/
    │   └── models/
    │       ├── smartx_model_v2.pkl    # Modelo XGBoost entrenado
    │       └── encoder_motivo.pkl     # Encoder de motivo de consulta
    │
    ├── backend/
    │   ├── app/
    │   │   └── routers/
    │   │       └── triaje.py          # Endpoints de triaje (módulo alternativo)
    │   └── motor_inferencia/
    │       └── smartx_motor.py        # Motor de inferencia modular
    │
    ├── data/
    │   └── dataset_SmartX_2200_casos_con_ruido.xlsx
    │
    ├── datasets/
    │   └── dataset_SmartX_2200_casos_con_ruido.xlsx  # Copia de trabajo del dataset
    │
    ├── docs/
    │   ├── SmartX_Dataset_Integration_Resumen.md
    │   ├── SmartX_Frontend_Integration_Guide.md
    │   └── SmartX_Mermaid_Diagramas.md
    │
    ├── frontend/
    │   ├── streamlit_app.py           # Interfaz Streamlit (http://localhost:8501)
    │   ├── smartx_dashboard.html      # Dashboard HTML (copia frontend)
    │   ├── smartx_dashboard.jsx       # Componentes React
    │   ├── api/
    │   │   └── smartx.js              # Cliente API JavaScript
    │   └── components/
    │       ├── Dashboard.jsx          # Vista principal del dashboard
    │       ├── PatientCard.jsx        # Tarjeta por paciente
    │       └── TriageForm.jsx         # Formulario de triaje (20 campos)
    │
    ├── models/
    │   ├── clasificacion.py           # Entrenamiento XGBoost → smartx_model_v2.pkl
    │   └── smartx_entrenamiento_rf.py # Entrenamiento Random Forest
    │
    └── scripts/
        ├── smartx_motor_inferencia.py    # Motor de inferencia v1 (referencia)
        └── smartx_motor_inferencia_v2.py # Motor de inferencia v2 (referencia)
```

---

## Instalación

```bash
# 1. Crear virtual environment
python -m venv .venv

# 2. Activar
# Windows CMD:
.venv\Scripts\activate.bat
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS/Linux:
source .venv/bin/activate

# 3. Instalar dependencias
cd 04_Codigo
pip install -r requirements.txt
```

> **Nota:** Las versiones de FastAPI, Uvicorn y Pydantic en `requirements.txt` usan restricciones mínimas (`>=`) para garantizar compatibilidad con Python 3.14, que no dispone de wheels precompilados para versiones antiguas de pydantic-core.

---

## Configuración

Copia `.env.example` a `.env` y ajusta los valores según el entorno:

```env
SMARTX_API_URL=http://127.0.0.1:8000
FASTAPI_PORT=8000
FASTAPI_ENV=development
STREAMLIT_PORT=8501
LOG_LEVEL=INFO
CACHE_DIR=./cachedir
```

> En producción, restringir los orígenes permitidos en la configuración CORS de `smartx_api.py`.

---

## Uso

### 1. Entrenar modelos

**XGBoost (recomendado):**
```bash
cd models
python clasificacion.py
```
Genera:
- `../assets/models/smartx_model_v2.pkl`
- `../assets/models/encoder_motivo.pkl`

**Random Forest (alternativo):**
```bash
cd models
python smartx_entrenamiento_rf.py
```
Genera: `smartx_rf_modelo.pkl`

Ambos leen el dataset desde `../data/dataset_SmartX_2200_casos_con_ruido.xlsx`.

### 2. Ejecutar la API

```bash
cd 04_Codigo
uvicorn smartx_api:app --reload --port 8000
```

La API queda disponible en `http://localhost:8000`.  
Documentación interactiva: `http://localhost:8000/docs`

### 3. Ejecutar el frontend Streamlit

```bash
cd 04_Codigo/frontend
streamlit run streamlit_app.py
```

Interfaz web disponible en `http://localhost:8501`.

### 4. Dashboard HTML standalone

Abrir directamente en el navegador:
```
04_Codigo/smartx_dashboard.html
```
o la copia en:
```
04_Codigo/frontend/smartx_dashboard.html
```
No requiere servidor adicional; consume la API en `http://localhost:8000`.

---

## API — Endpoints y contratos

### Health

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET` | `/` | Health check básico |
| `GET` | `/health` | Estado del motor de inferencia |

### Triaje

| Método | Ruta | Descripción |
|--------|------|-------------|
| `POST` | `/api/v1/inferencia` | **Endpoint principal de triaje** |
| `GET` | `/api/v1/paciente/{id_paciente}/historial` | Historial de visitas del paciente |
| `GET` | `/api/v1/catalogo/escenarios` | Catálogo completo de escenarios CIE-10 |

### Modelo de entrada — `SintomasInput`

```json
{
  "id_paciente": "uuid-seudonimizado",
  "unidad_atencion": "HCG_URGENCIAS",
  "edad": 45,
  "sexo_biologico": "M",
  "disnea_presente": false,
  "perdida_conciencia": false,
  "sangrado_activo": false,
  "fiebre_presente": true,
  "temperatura_celsius": 38.5,
  "intensidad_dolor_eva": 6,
  "duracion_sintoma_horas": 12,
  "peso_kg": 75.0,
  "talla_cm": 170.0,
  "diabetes_mellitus": false,
  "hipertension": true,
  "cardiopatia_isquemica": false,
  "epoc_asma": false,
  "embarazo_posible": false,
  "semanas_gestacion": 0,
  "sintomas_texto": "Dolor de cabeza intenso con fiebre desde ayer"
}
```

Validaciones Pydantic aplicadas automáticamente:
- `edad`: 0 – 120 años
- `temperatura_celsius`: 35.0 – 42.5 °C (solo válida si `fiebre_presente = true`)
- `intensidad_dolor_eva`: 0 – 10
- `peso_kg`: 1.0 – 300.0 kg
- `talla_cm`: 30.0 – 250.0 cm
- `semanas_gestacion`: 0 – 42 (solo válida si `embarazo_posible = true`)
- `sintomas_texto`: mínimo 10 caracteres

### Modelo de salida — `SemaforoOutput`

```json
{
  "nivel_ia": "amarillo",
  "fuente_nivel": "modelo_xgboost",
  "probabilidades": {
    "p_rojo": 0.12,
    "p_amarillo": 0.71,
    "p_verde": 0.17
  },
  "escenarios_diferenciales": [
    {
      "cie10": "I10",
      "descripcion": "Hipertensión descompensada",
      "especialidad": "Medicina Interna",
      "probabilidad": 0.58
    }
  ],
  "especialidad_sugerida": "Medicina Interna",
  "shap_explicacion": "La presión arterial elevada con cefalea intensa incrementó significativamente el nivel de urgencia.",
  "shap_variables_top3": ["hipertension", "intensidad_dolor_eva", "temperatura_celsius"],
  "imc_calculado": 25.95,
  "alerta_critica": false,
  "alertas_detalle": [],
  "modelo_version": "xgb_v1.0.0-piloto-hcg",
  "tiempo_procesamiento_ms": 43,
  "hash_resultado": "sha256:..."
}
```

Valores posibles de `fuente_nivel`:
- `alerta_critica_inmediata` — bypass por bandera roja (disnea, pérdida de consciencia, sangrado)
- `modelo_xgboost` — clasificación por modelo ML
- `conservadurismo_medico` — regla de seguridad aplicada tras el modelo

---

## Pipeline de inferencia

El motor ejecuta 8 pasos en orden estricto:

```
Entrada JSON (SintomasInput)
        │
        ▼
1. VALIDACIÓN CLÍNICA ──── Rangos NOM-004 (edad, temperatura, EVA, IMC)
        │
        ▼
2. ALERTAS CRÍTICAS ─────── Bypass inmediato a ROJO si:
        │                   disnea_presente | perdida_conciencia | sangrado_activo
        ▼
3. CÁLCULO IMC ──────────── peso_kg / (talla_cm / 100)²
        │
        ▼
4. MODELO XGBoost ───────── Probabilidades (p_rojo, p_amarillo, p_verde)
        │
        ▼
5. CONSERVADURISMO ──────── Eleva nivel si p_rojo > umbral de seguridad
        │
        ▼
6. ESCENARIOS CIE-10 ────── 3 diagnósticos diferenciales + especialidad
        │
        ▼
7. EXPLICABILIDAD SHAP ──── Top-3 variables + texto en lenguaje natural
        │
        ▼
8. OUTPUT JSON ──────────── Conforme HL7-FHIR DiagnosticReport + hash NOM-024
```

El motor es **determinístico**: las mismas entradas producen siempre la misma salida.

---

## Dataset y modelos ML

### Dataset

| Atributo | Valor |
|----------|-------|
| Archivo | `data/dataset_SmartX_2200_casos_con_ruido.xlsx` |
| Total de casos | 2,200 pacientes sintéticos |
| Verde (estable) | 655 casos — 35% |
| Amarillo (prioritario) | 748 casos — 40% |
| Rojo (crítico) | 467 casos — 25% |
| Variables de entrada | 20 clínicas + 4 red flags |
| Accuracy reportada | 87.6% |

### Modelos

**XGBoost v2** (`models/clasificacion.py`):
- Variables: `motivo_consulta` (LabelEncoded), síntomas binarios, datos demográficos
- Salida: `assets/models/smartx_model_v2.pkl` + `assets/models/encoder_motivo.pkl`
- Accuracy objetivo: > 87%

**Random Forest** (`models/smartx_entrenamiento_rf.py`):
- 200 árboles, `max_depth=10`
- Balanceo de clases: los casos ROJO tienen mayor peso
- Salida: `smartx_rf_modelo.pkl`

> Los archivos `.pkl` se generan localmente con `python models/clasificacion.py` y **no** se versiona en el repositorio.

---

## Frontend

### Dashboard HTML standalone (`frontend/smartx_dashboard.html`)

Interfaz de producción ligera, sin dependencias de servidor Node:

- Grid de pacientes en tiempo real con color dominante por nivel de urgencia
- Estadísticas en tiempo real: CRÍTICOS · URGENTES · ESTABLES · TOTAL
- Formulario de nuevo triaje con 20 campos + 4 banderas rojas con bypass automático
- Animaciones de alerta pulsante para nivel ROJO
- Panel de detalle con escenarios CIE-10 y explicación SHAP
- Notificaciones emergentes

Tecnologías: HTML5 · Tailwind CSS · Font Awesome · JavaScript vanilla

### Interfaz Streamlit (`frontend/streamlit_app.py`)

Interfaz de desarrollo rápido:
- URL: `http://localhost:8501`
- Formulario de triaje completo conectado al backend en `http://localhost:8000`
- Manejo de errores y validación visual

### Componentes React (`frontend/components/`)

| Archivo | Descripción |
|---------|-------------|
| `Dashboard.jsx` | Vista principal y estado global |
| `PatientCard.jsx` | Tarjeta individual de paciente |
| `TriageForm.jsx` | Formulario de triaje (20 campos) |
| `api/smartx.js` | Cliente HTTP hacia FastAPI |

---

## Variables clínicas

### Banderas rojas — bypass inmediato a ROJO

| Variable | Condición |
|----------|-----------|
| `perdida_conciencia` | `true` |
| `sangrado_activo` | `true` |
| `disnea_presente` | `true` |

Cuando cualquiera es `true`, el modelo ML no se ejecuta y el nivel queda fijo en `rojo` con `fuente_nivel = alerta_critica_inmediata`.

### Variables demográficas y clínicas

| Variable | Tipo | Rango / Valores |
|----------|------|----------------|
| `id_paciente` | UUID | Seudonimizado (LFPDPPP) |
| `unidad_atencion` | enum | `HCG_URGENCIAS` · `HCG_MED_INTERNA` |
| `edad` | int | 0 – 120 años |
| `sexo_biologico` | enum | `M` · `F` |
| `fiebre_presente` | bool | — |
| `temperatura_celsius` | float | 35.0 – 42.5 °C |
| `intensidad_dolor_eva` | int | 0 – 10 |
| `duracion_sintoma_horas` | int | ≥ 0 |
| `peso_kg` | float | 1.0 – 300.0 kg |
| `talla_cm` | float | 30.0 – 250.0 cm |
| `imc_calculado` | float | Derivada (motor) |
| `diabetes_mellitus` | bool | — |
| `hipertension` | bool | — |
| `cardiopatia_isquemica` | bool | — |
| `epoc_asma` | bool | — |
| `embarazo_posible` | bool | — |
| `semanas_gestacion` | int | 0 – 42 |
| `sintomas_texto` | str | Mín. 10 caracteres |

---

## Catálogo de escenarios CIE-10

### Nivel ROJO — Crítico

| CIE-10 | Descripción | Especialidad |
|--------|-------------|-------------|
| I21.0 | IAM con elevación del segmento ST | Cardiología |
| J96.0 | Insuficiencia respiratoria aguda | Urgencias |
| I64 | EVC aguda | Neurología |
| R57.0 | Choque cardiogénico | Cuidados Intensivos |
| K25.0 | Úlcera gástrica con hemorragia | Cirugía |
| O15.9 | Eclampsia | Ginecología |

### Nivel AMARILLO — Prioritario

| CIE-10 | Descripción | Especialidad |
|--------|-------------|-------------|
| J18.9 | Neumonía | Medicina Interna |
| N10 | Pielonefritis aguda | Urología |
| K35.9 | Apendicitis aguda | Cirugía General |
| I10 | Hipertensión descompensada | Medicina Interna |
| E11.65 | Diabetes tipo 2 con hiperglucemia | Endocrinología |
| R51 | Cefalea intensa | Neurología |

### Nivel VERDE — Estable

| CIE-10 | Descripción | Especialidad |
|--------|-------------|-------------|
| Z00.00 | Examen médico general | Medicina Familiar |
| J00 | Rinofaringitis aguda (resfriado común) | Medicina Familiar |
| M54.5 | Lumbalgia crónica | Rehabilitación |
| K21.0 | Enfermedad por reflujo gastroesofágico | Gastroenterología |
| F41.1 | Trastorno de ansiedad generalizado | Psiquiatría |

---

## Normativas implementadas

| Norma | Aplicación en SmartX |
|-------|---------------------|
| **NOM-004-SSA3-2012** (Expediente Clínico) | Integridad del dato clínico; identificación seudonimizada mediante UUID |
| **NOM-024-SSA3-2012** (Registro Electrónico) | Hash SHA-256 por resultado; trazabilidad de cada inferencia; middleware de auditoría |
| **LFPDPPP** | Sin nombre ni NSS en los objetos JSON; datos seudonimizados en todo el pipeline |

---

## Documentación adicional

| Documento | Ubicación | Contenido |
|-----------|-----------|-----------|
| Resumen de integración del dataset | `docs/SmartX_Dataset_Integration_Resumen.md` | Performance 87.6%, distribución de clases |
| Guía de integración frontend | `docs/SmartX_Frontend_Integration_Guide.md` | Instrucciones para conectar el dashboard a la API |
| Diagramas Mermaid | `docs/SmartX_Mermaid_Diagramas.md` | Diagramas ER y de flujo en Mermaid.js |
| Arquitectura IA | `../01_Arquitectura_Sistema/SmartX_Arquitectura_IA.docx` | Diseño del sistema completo |
| Flujo lógico | `../01_Arquitectura_Sistema/SmartX_Flujo_Logico (1).drawio` | Diagrama interactivo draw.io |
| Esquema de base de datos | `../02_Base_de_Datos/SmartX_2_Esquema_BD.docx` | Tablas y relaciones |
| Diagrama ER | `../02_Base_de_Datos/SmartX_3_ER_Diagrama.html` | Entidad-relación interactivo |
| Especificaciones del prototipo | `../03_Prototipo__MVP/SmartX_P1_Prototipo_IA.docx` | Requisitos y alcance del MVP |
