# SmartX HCG — Sistema de Triaje Médico Inteligente
## Documentación Técnica del Código | Piloto v1.0

Sistema de triaje automatizado basado en IA para el Hospital Civil de Guadalajara.
Clasifica en tiempo real la urgencia de cada paciente en tres niveles
(**ROJO / AMARILLO / VERDE**) usando XGBoost + reglas clínicas + conservadurismo médico.

---

## Stack tecnológico

| Capa | Tecnología | Versión |
|------|-----------|---------|
| Lenguaje | Python | 3.14 |
| API REST | FastAPI | ≥ 0.115.0 |
| Servidor ASGI | Uvicorn | ≥ 0.30.0 |
| Validación | Pydantic | ≥ 2.10.0 |
| Clasificación ML | XGBoost | 3.2.0 |
| Base de datos | Supabase (PostgreSQL) | ≥ 2.9.0 SDK |
| Conexión BD (directa) | psycopg2-binary | ≥ 2.9.0 |
| Async BD | asyncpg | ≥ 0.29.0 |
| Explicabilidad | SHAP | 0.44.1 |
| Dashboard | HTML + Tailwind CSS | — |
| Frontend dev | Streamlit | 1.31.1 |

---

## Estructura del proyecto

```
04_Codigo/
├── smartx_api.py                  # API FastAPI — punto de entrada principal
├── smartx_motor_inferencia.py     # Motor de inferencia XGBoost (pipeline 4 pasos)
├── requirements.txt               # Dependencias Python
├── .env                           # Variables de entorno (no versionar — en .gitignore)
├── .env.example                   # Plantilla de variables sin secretos
├── .gitignore
│
├── assets/models/
│   ├── smartx_model_v2.pkl        # Modelo XGBoost entrenado (408 KB)
│   └── encoder_motivo.pkl         # LabelEncoder de motivo_consulta (722 B)
│
├── datasets/                      # Dataset canónico de entrenamiento
│   ├── dataset_SmartX_2200_casos_con_ruido.xlsx  # Fuente del modelo actual
│   ├── entrenamiento.csv          (1,540 filas × 20 cols)
│   ├── validacion.csv             (330 filas)
│   ├── prueba.csv                 (330 filas)
│   ├── etiquetas_*.csv            # Labels por split
│   └── *.csv                      # Metadatos y catálogos
│
├── database/
│   ├── smartx_supabase_schema.sql         # Esquema PostgreSQL (tablas, índices, RLS)
│   └── smartx_excel_a_csv.py             # Conversor Excel → CSV (utilidad)
│
├── frontend/
│   ├── smartx_dashboard.html      # Dashboard HTML standalone (producción)
│   └── streamlit_app.py           # Interfaz Streamlit (desarrollo)
│
├── models/
│   └── clasificacion.py           # Entrenamiento XGBoost → genera los .pkl
│
├── docs/
│   ├── SmartX_Dataset_Integration_Resumen.md
│   ├── SmartX_Frontend_Integration_Guide.md
│   └── SmartX_Mermaid_Diagramas.md
│
└── _archivo/                      # Código archivado — no activo en producción
    └── backend/                   # Estructura modular para futura expansión
        ├── app/routers/triaje.py
        └── motor_inferencia/smartx_motor.py
```

---

## Instalación

```powershell
# 1. Activar entorno virtual
.venv\Scripts\Activate.ps1          # PowerShell (Windows)
# source .venv/bin/activate         # macOS/Linux

# 2. Instalar dependencias
cd 04_Codigo
pip install -r requirements.txt

# 3. Configurar variables de entorno
copy .env.example .env
# Editar .env con las credenciales de Supabase
```

### Contenido del archivo `.env`

```env
SMARTX_API_URL=http://127.0.0.1:8000
FASTAPI_PORT=8000
FASTAPI_ENV=development

SUPABASE_URL=https://TU_PROJECT_ID.supabase.co
SUPABASE_PUBLISHABLE_KEY=sb_publishable_XXXX
SUPABASE_SECRET_KEY=sb_secret_XXXX
```

> ⚠️ El archivo `.env` está en `.gitignore` y **nunca debe subirse a git**.

---

## Base de datos (Supabase)

El proyecto usa Supabase (PostgreSQL en la nube) como capa de persistencia.

### Tablas

| Tabla | Descripción |
|-------|-------------|
| `inferencias` | Una fila por cada triaje procesado (inputs + resultado IA) |
| `auditoria_api` | Log de cada petición HTTP (NOM-024-SSA3) |

### Setup inicial (solo una vez)

```
1. Abrir Supabase → SQL Editor
2. Pegar el contenido de database/smartx_supabase_schema.sql
3. Ejecutar con Run
```

---

## Uso

### 1. Entrenar el modelo (si no existen los `.pkl`)

```powershell
cd models
python clasificacion.py
# Genera: ../assets/models/smartx_model_v2.pkl
#         ../assets/models/encoder_motivo.pkl
# Lee desde: ../datasets/dataset_SmartX_2200_casos_con_ruido.xlsx
```

### 2. Levantar la API

```powershell
cd 04_Codigo
uvicorn smartx_api:app --reload --port 8000
```

| Recurso | URL |
|---------|-----|
| API | `http://localhost:8000` |
| Swagger UI | `http://localhost:8000/docs` |
| Health check | `http://localhost:8000/health` |

### 3. Abrir el dashboard

Abrir directamente en el navegador (no requiere servidor Node):
```
04_Codigo/frontend/smartx_dashboard.html
```

Carga automáticamente los últimos 50 triajes desde Supabase al iniciar.

### 4. Frontend Streamlit (desarrollo)

```powershell
cd 04_Codigo/frontend
streamlit run streamlit_app.py
# http://localhost:8501
```

---

## API — Endpoints

| Método | Ruta | Descripción |
|--------|------|-------------|
| `GET` | `/` | Health check — incluye estado de Supabase |
| `GET` | `/health` | Estado del motor de inferencia |
| `POST` | `/api/v1/inferencia` | **Clasificar urgencia del paciente** |
| `GET` | `/api/v1/inferencias/recientes?limite=50` | Últimas N inferencias |
| `GET` | `/api/v1/paciente/{id}/historial` | Historial de visitas del paciente |
| `GET` | `/api/v1/catalogo/escenarios` | Catálogo CIE-10 por nivel |
| `GET` | `/api/v1/catalogo/motivos` | Motivos de consulta válidos |

### Ejemplo de request

```json
POST /api/v1/inferencia
{
  "edad": 62,
  "sexo_biologico": "M",
  "motivo_consulta": "Dolor torácico",
  "intensidad_sintoma": 9,
  "tiempo_evolucion_horas": 1,
  "dolor_toracico": true,
  "redflag_dolor_toracico_opresivo_con_sudoracion": true,
  "antecedentes_riesgo": "Hipertensión, tabaquismo"
}
```

### Ejemplo de respuesta

```json
{
  "nivel_ia": "rojo",
  "fuente_nivel": "regla_critica",
  "probabilidades": {"rojo": 1.0, "amarillo": 0.0, "verde": 0.0},
  "escenarios": [
    {"cie10": "I21", "descripcion": "Infarto agudo de miocardio", "probabilidad_relativa": "alta"}
  ],
  "explicacion_shap": "Dolor torácico opresivo con sudoración — bandera roja activa.",
  "alerta_critica": true,
  "alertas_detalle": ["Dolor torácico opresivo con sudoración — posible IAM"],
  "modelo_version": "xgboost-v2.0-hcg-piloto",
  "tiempo_procesamiento_ms": 12
}
```

---

## Pipeline de inferencia (4 pasos activos)

```
1. ALERTAS CRÍTICAS   → ROJO inmediato si hay redflag activo (bypasa ML)
                        (redflag_disnea_severa | redflag_sangrado_abundante |
                         redflag_deficit_neurologico_subito |
                         redflag_dolor_toracico_opresivo_con_sudoracion)

2. INFERENCIA XGBoost → Probabilidades sobre 17 features del dataset

3. CONSERVADURISMO    → Eleva nivel si p(rojo) ≥ 30% o p(amarillo) ≥ 30%
                        (seguridad clínica — prefiere el nivel más grave en duda)

4. SHAP + CIE-10      → Explicabilidad top-3 variables + escenarios diferenciales
                        → INSERT en tabla Supabase `inferencias`
```

---

## Dataset

| Atributo | Valor |
|----------|-------|
| Archivo canónico | `datasets/dataset_SmartX_2200_casos_con_ruido.xlsx` |
| MD5 verificado | `0a70639125e3a512d4474507b8eeee2b` |
| Total de casos | 2,200 pacientes sintéticos con ruido controlado |
| Entrenamiento | 1,540 casos (70%) |
| Validación | 330 casos (15%) |
| Prueba | 330 casos (15%) |
| Features activas | 17 columnas clínicas |
| Accuracy reportada | 87.6% |

---

## Seguridad

| Medida | Detalle |
|--------|---------|
| `.gitignore` | `.env` excluido del versionado |
| CORS | Lista blanca: `localhost:8000`, `localhost:8501` |
| Validación | Pydantic v2 con rangos clínicos en todos los campos |
| Auditoría | Middleware registra cada petición en `auditoria_api` |
| Trazabilidad | SHA-256 por resultado + UUID seudonimizado por paciente |
| RLS | Row Level Security habilitado en tablas Supabase |

> ⚠️ **Acción pendiente:** Rotar `SUPABASE_SECRET_KEY` en Supabase → Settings → API → Secret keys.

---

## Normativas

| Norma | Implementación |
|-------|---------------|
| **NOM-004-SSA3-2012** | Validación clínica con Pydantic; integridad del dato; UUID seudonimizado |
| **NOM-024-SSA3-2012** | Hash SHA-256 por resultado; tabla `auditoria_api` en Supabase |
| **LFPDPPP** | Sin nombre, NSS ni datos identificadores en el pipeline |
