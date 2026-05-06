# SmartX HCG — AI Agent Guidelines

## Quick Start

**SmartX HCG** is an intelligent medical triage system for Hospital Civil de Guadalajara (HCG). It classifies patient urgency into three levels (RED/YELLOW/GREEN) using XGBoost, SHAP explanations, and an 8-step deterministic inference pipeline.

### Setup
```bash
cd 04_Codigo
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -r requirements.txt
```

### Key Commands
- **API**: `python smartx_api.py` → http://localhost:8000 (FastAPI with Swagger docs at `/docs`)
- **Dashboard**: `cd frontend && streamlit run streamlit_app.py` → http://localhost:8501
- **HTML Dashboard**: Open `frontend/smartx_dashboard.html` directly (no server needed)
- **Train ML models**: `cd models && python clasificacion.py` (XGBoost) or `python smartx_entrenamiento_rf.py` (Random Forest)

---

## Architecture & Code Conventions

### Stack
- **Backend**: FastAPI 0.109.0 + Uvicorn ASGI + Pydantic v2 validation
- **ML**: XGBoost 3.2.0, scikit-learn 1.4.1, SHAP 0.44.1 for explainability
- **Frontend**: Streamlit 1.31.1 (dev) + React 18 (production) + Tailwind CSS
- **Data**: pandas 2.1.4, NumPy 1.26.4, joblib 1.3.2 for model serialization
- **Database**: SQLAlchemy 2.0.25 (defined but not heavily used in pilot)

### Directory Layout
```
04_Codigo/
├── smartx_api.py                    # Main FastAPI entry point (465 lines)
├── smartx_motor_inferencia.py        # Inference engine (v1, unmodified from scripts/)
├── requirements.txt                 # 47 dependencies
├── .env.example                     # Config template
│
├── backend/
│   ├── app/routers/triaje.py        # API endpoints
│   └── motor_inferencia/
│       └── smartx_motor.py          # Re-exports from root smartx_motor_inferencia
│
├── frontend/
│   ├── streamlit_app.py             # Dev dashboard
│   ├── smartx_dashboard.html        # Prod standalone HTML
│   ├── smartx_dashboard.jsx         # React root
│   ├── api/smartx.js                # JS HTTP client
│   └── components/
│       ├── Dashboard.jsx            # Main view
│       ├── PatientCard.jsx
│       └── TriageForm.jsx           # 20-field patient intake form
│
├── models/
│   ├── clasificacion.py             # XGBoost training → smartx_model_v2.pkl
│   └── smartx_entrenamiento_rf.py   # Random Forest training
│
├── scripts/
│   ├── smartx_motor_inferencia.py   # Original motor (v1)
│   └── smartx_motor_inferencia_v2.py # Motor v2 variant
│
├── data/
│   └── dataset_SmartX_2200_casos_con_ruido.xlsx  # Training dataset (2200 synthetic cases)
│
├── assets/models/                   # .pkl files (generated locally, NOT versioned)
│   ├── smartx_model_v2.pkl
│   └── encoder_motivo.pkl
│
└── docs/
    ├── SmartX_Dataset_Integration_Resumen.md
    ├── SmartX_Frontend_Integration_Guide.md
    └── SmartX_Mermaid_Diagramas.md
```

### Code Style & Language Mix
- **Primary language**: Spanish (variable/function names, comments, docs)
- **Documentation**: ASCII art boxes in module headers (e.g., `╔═══╗` headers)
- **Imports**: Grouped by standard → FastAPI → domain-specific
- **Validation**: Strict Pydantic v2 models with custom ranges (age 0–120, temp 35–42.5°C, EVA pain 0–10)
- **Naming**: Snake_case for functions/variables, PascalCase for classes (e.g., `SintomasInput`, `SemaforoOutput`)

---

## Key Domain Knowledge

### The 8-Step Inference Pipeline
Every inference follows this exact sequence (file: `smartx_motor_inferencia.py`):

1. **Clinical Validation** — Range checks per NOM-004 (age, temp, EVA, BMI)
2. **Critical Alerts** — Immediate bypass to RED if: `disnea_presente` OR `perdida_conciencia` OR `sangrado_activo`
3. **BMI Calculation** — `weight_kg / (height_cm / 100)²`
4. **XGBoost Inference** — Probabilities `(p_rojo, p_amarillo, p_verde)`
5. **Medical Conservatism** — Safety rule: elevate level if `p_rojo > threshold`
6. **ICD-10 Scenarios** — 3 differential diagnoses + specialty
7. **SHAP Explanation** — Top-3 influencing variables + natural language text
8. **Output JSON** — HL7-FHIR DiagnosticReport + SHA-256 hash (NOM-024 compliance)

**Deterministic**: same inputs always produce the same output.

### API Endpoints
- `POST /api/v1/inferencia` — Main triage endpoint (accepts `SintomasInput` JSON)
- `GET /api/v1/paciente/{id_paciente}/historial` — Patient visit history
- `GET /api/v1/catalogo/escenarios` — Full ICD-10 catalog
- `GET /health` — Engine health check
- `GET /docs` — Swagger interactive documentation

### Input Model (`SintomasInput`)
20 clinical fields + 4 red flags:
- **Flags** (bypass to RED if true): `perdida_conciencia`, `sangrado_activo`, `disnea_presente`
- **Vitals**: `edad`, `sexo_biologico`, `peso_kg`, `talla_cm`, `temperatura_celsius`, `fiebre_presente`
- **Symptoms**: `intensidad_dolor_eva` (0–10), `duracion_sintoma_horas`, `sintomas_texto` (min 10 chars)
- **Comorbidities**: `diabetes_mellitus`, `hipertension`, `cardiopatia_isquemica`, `epoc_asma`
- **Obstetric**: `embarazo_posible`, `semanas_gestacion` (0–42 if pregnant)
- **Admin**: `id_paciente` (UUID, seudonimized), `unidad_atencion` (enum: `HCG_URGENCIAS`, `HCG_MED_INTERNA`)

### Output Model (`SemaforoOutput`)
- `nivel_ia` — RED/YELLOW/GREEN urgency level
- `fuente_nivel` — decision source (`alerta_critica_inmediata` | `modelo_xgboost` | `conservadurismo_medico`)
- `probabilidades` — `{p_rojo, p_amarillo, p_verde}` (floats, sum to 1.0)
- `escenarios_diferenciales` — Top 3 ICD-10 diagnoses with specialty + probability
- `especialidad_sugerida` — Recommended department
- `shap_explicacion` — Natural language SHAP explanation
- `shap_variables_top3` — Top 3 influencing variables
- `imc_calculado` — Computed BMI
- `alerta_critica` — Boolean flag for critical conditions
- `modelo_version`, `tiempo_procesamiento_ms`, `hash_resultado` — Metadata for audit trail

### Dataset & Model Performance
- **Training data**: `data/dataset_SmartX_2200_casos_con_ruido.xlsx`
  - 2,200 synthetic patient cases
  - Class distribution: GREEN 35% (655) | YELLOW 40% (748) | RED 25% (467)
  - Accuracy: **87.6%**
- **Active model**: XGBoost v2 (`assets/models/smartx_model_v2.pkl`)
- **Model files**: `.pkl` files are generated locally via `python models/clasificacion.py` and are NOT versioned

### Compliance & Standards
- **NOM-004-SSA3-2012**: Clinical record integrity; pseudonymized UUIDs (no names, no SSN)
- **NOM-024-SSA3-2012**: Electronic registry; SHA-256 hash per inference for audit trail
- **LFPDPPP**: Privacy law; no PII in JSON payloads anywhere
- **HL7-FHIR**: Output structure aligns with DiagnosticReport standard

---

## Common Tasks

### Adding a New Clinical Variable
1. Add field to `SintomasInput` Pydantic model in `smartx_api.py` with validation range
2. Add to inference logic in `smartx_motor_inferencia.py` (step 1–3)
3. Update dataset column in `data/dataset_SmartX_2200_casos_con_ruido.xlsx`
4. Retrain model: `python models/clasificacion.py` (generates `smartx_model_v2.pkl`)
5. Test via Swagger docs (`/docs`)

### Deploying a New Model Version
1. Train: `python models/clasificacion.py` → saves `.pkl` files to `assets/models/`
2. Restart API: `python smartx_api.py` (motor auto-loads `.pkl` from disk)
3. Version string in response: update `modelo_version` in `SemaforoOutput` (currently `xgb_v1.0.0-piloto-hcg`)

### Testing the Full Pipeline
- **Unit level**: Python repl → import `MotorInferenciaSmartX` → call `procesar_paciente()`
- **Integration**: Swagger UI at `http://localhost:8000/docs` → try example `SintomasInput` JSON
- **E2E**: Streamlit dashboard at `http://localhost:8501` or HTML dashboard in browser

### Frontend Changes
- **Dev**: Edit `frontend/streamlit_app.py`, restart Streamlit (hot reload sometimes works, often requires manual restart)
- **Prod**: Edit `frontend/smartx_dashboard.html` or React components in `frontend/components/`, build and serve

---

## Important Notes for Agents

1. **Multi-language**: Code is Spanish + English. Variables like `disnea_presente`, `sangrado_activo`, `perdida_conciencia` are medical Spanish terms—preserve naming.
2. **Determinism is critical**: The motor must always produce the same output for the same input. Do not add randomness or external state.
3. **Latency matters**: Typical inference time ~43ms. Optimizations should preserve speed.
4. **Model files**: `.pkl` files are generated, never checked in. Always ensure they're built before running tests.
5. **CORS in dev**: Localhost is whitelisted for Streamlit + React frontends. Restrict in production.
6. **Compliance first**: Any change to input/output contracts must maintain NOM-024 audit trail and LFPDPPP privacy guarantees.

---

## Documentation Cross-References
- Full technical overview: [README.md](README.md)
- Dataset analysis: [docs/SmartX_Dataset_Integration_Resumen.md](04_Codigo/docs/SmartX_Dataset_Integration_Resumen.md)
- Frontend guide: [docs/SmartX_Frontend_Integration_Guide.md](04_Codigo/docs/SmartX_Frontend_Integration_Guide.md)
- Architecture diagrams: [docs/SmartX_Mermaid_Diagramas.md](04_Codigo/docs/SmartX_Mermaid_Diagramas.md)
- External docs: `01_Arquitectura_Sistema/`, `02_Base_de_Datos/`, `03_Prototipo__MVP/`
