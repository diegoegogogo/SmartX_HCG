---
name: smartx-model-training
description: "Use when: training XGBoost or Random Forest models, deploying new model versions, managing model artifacts, or verifying model integrity for SmartX HCG"
trigger: "/smartx-model"
---

# SmartX Model Training & Deployment Skill

Automates training, versioning, and deployment of ML models (XGBoost/Random Forest) for the medical triage system.

## Quick Commands

```
/smartx-model train xgboost    # Train XGBoost → smartx_model_v2.pkl
/smartx-model train rf         # Train Random Forest → smartx_rf_modelo.pkl
/smartx-model deploy <version> # Mark and verify model for deployment
/smartx-model verify           # Check model integrity & API compatibility
/smartx-model list             # Show all trained models with metadata
```

---

## Workflow

### 1. Train XGBoost (Recommended)

**Command:**
```bash
/smartx-model train xgboost
```

**What it does:**
- Runs `python 04_Codigo/models/clasificacion.py`
- Reads training data from `04_Codigo/data/dataset_SmartX_2200_casos_con_ruido.xlsx`
- Saves outputs:
  - `04_Codigo/assets/models/smartx_model_v2.pkl` — XGBoost classifier
  - `04_Codigo/assets/models/encoder_motivo.pkl` — Label encoder for motivo_consulta
- Captures accuracy metrics and class distribution
- **Expected output**: "Training complete. Accuracy: ~87.6%"

**When to use:**
- Dataset has been updated with new cases
- Model performance needs improvement
- After feature engineering (new clinical variables)

---

### 2. Train Random Forest (Alternative)

**Command:**
```bash
/smartx-model train rf
```

**What it does:**
- Runs `python 04_Codigo/models/smartx_entrenamiento_rf.py`
- 200 trees, max_depth=10, class weights favor RED cases
- Saves to `04_Codigo/smartx_rf_modelo.pkl`
- Outputs accuracy and feature importance

**When to use:**
- Experimenting with ensemble alternatives
- Model comparison or A/B testing
- Random Forest currently not deployed (XGBoost is active)

---

### 3. Deploy Model Version

**Command:**
```bash
/smartx-model deploy v1.1.0
```

**What it does:**
1. Verifies `.pkl` files exist and load without error
2. Runs test inference with sample data (validates schema compatibility)
3. Updates version string in `smartx_api.py` (`modelo_version = "xgb_v1.1.0-piloto-hcg"`)
4. Restarts FastAPI server on port 8000
5. Smoke test: calls `/health` endpoint to confirm motor is running
6. Returns deployment checklist (git commit, push, monitoring links)

**Prechecks:**
- ✅ `.pkl` files exist and are loadable
- ✅ `SintomasInput` schema unchanged (Pydantic validates)
- ✅ Inference latency < 100ms
- ✅ Output hash (SHA-256) generates without error

---

### 4. Verify Model Integrity

**Command:**
```bash
/smartx-model verify
```

**What it does:**
- Loads all `.pkl` files and checks for corruption
- Runs test cases through inference engine (8-step pipeline)
- Validates output schema against `SemaforoOutput` Pydantic model
- Checks API endpoint `/health` response
- Compares inference output with ground truth if available
- Reports: model size, load time, inference latency, file checksums (SHA-256)

**Output:**
```
✅ Motor loads successfully
✅ Test inference passes (43ms latency)
✅ Output schema valid (HL7-FHIR compliant)
✅ Model checksum: sha256:abc123...
✅ API health: OK
```

---

### 5. List All Models

**Command:**
```bash
/smartx-model list
```

**Output:**
```
Trained Models in assets/models/:
  smartx_model_v2.pkl         — 2.3 MB | XGBoost | Created 2026-05-06 14:32 | Accuracy 87.6%
  smartx_rf_modelo.pkl        — 1.8 MB | RF      | Created 2026-05-05 09:15 | Accuracy 85.2%
  encoder_motivo.pkl          — 45 KB  | LabelEnc| Created 2026-05-06 14:32

Active Model (in smartx_api.py): xgb_v1.0.0-piloto-hcg
```

---

## Model Artifacts Structure

```
04_Codigo/assets/models/
├── smartx_model_v2.pkl        # Active XGBoost classifier
├── smartx_rf_modelo.pkl       # Alternative Random Forest
└── encoder_motivo.pkl         # Feature encoder (required for inference)
```

**Note**: These files are **generated locally** by `models/clasificacion.py` and `.gitignore`'d. Never commit `.pkl` files.

---

## Training Data Contract

**File**: `04_Codigo/data/dataset_SmartX_2200_casos_con_ruido.xlsx`

**Required columns** (20 clinical + 1 target):
```
id_paciente, unidad_atencion, edad, sexo_biologico,
disnea_presente, perdida_conciencia, sangrado_activo,
fiebre_presente, temperatura_celsius, intensidad_dolor_eva,
duracion_sintoma_horas, peso_kg, talla_cm,
diabetes_mellitus, hipertension, cardiopatia_isquemica, epoc_asma,
embarazo_posible, semanas_gestacion, sintomas_texto,
motivo_consulta, nivel_urgencia  ← target (RED/YELLOW/GREEN)
```

**Class distribution target** (from current dataset):
- GREEN: 35% (655 cases)
- YELLOW: 40% (748 cases)
- RED: 25% (467 cases)

---

## Common Tasks

### Task: "Accuracy dropped after adding a new variable"

1. Check dataset: are there missing values in the new column?
2. Run `/smartx-model train xgboost` to retrain with updated feature
3. Compare accuracy output vs. previous run
4. If accuracy worsens, consider feature scaling or removing the variable
5. Run `/smartx-model verify` to confirm inference still works end-to-end

### Task: "Deploy a trained model to production"

1. Run `/smartx-model verify` to pass all prechecks
2. Run `/smartx-model deploy v1.1.0` with new version tag
3. Copy deployment checklist and commit changes:
   ```bash
   git add 04_Codigo/smartx_api.py
   git commit -m "Deploy model xgb_v1.1.0 (accuracy: 87.6%)"
   git push
   ```
4. Monitor `/health` endpoint to confirm API is healthy

### Task: "A/B test Random Forest vs. XGBoost"

1. Run `/smartx-model train rf` to generate `smartx_rf_modelo.pkl`
2. Manually edit `smartx_api.py` to load RF instead: `motor = MotorInferenciaSmartX(model_type="random_forest")`
3. Restart API, test via Swagger at `http://localhost:8000/docs`
4. Compare inference times and accuracy on 20–30 test cases
5. Revert to XGBoost if RF underperforms

---

## Compliance & Versioning

All models must satisfy:
- **NOM-024-SSA3-2012**: Output includes SHA-256 hash for audit trail
- **Determinism**: Same input always produces same output (no randomness in inference)
- **Latency**: Typical inference ~43ms (goal: < 100ms)

**Version string format** (in `SemaforoOutput.modelo_version`):
```
xgb_v1.0.0-piloto-hcg
├─ xgb      = algorithm (xgb | rf)
├─ v1.0.0   = semantic version
└─ piloto-hcg = environment/hospital
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `ModuleNotFoundError: No module named 'xgboost'` | Run `pip install -r requirements.txt` in venv |
| `.pkl` file corrupted | Delete `.pkl` files, retrain with `/smartx-model train xgboost` |
| Accuracy drops 5%+ | Check dataset for new missing values, recheck feature scaling |
| API won't restart after deploy | Check FastAPI logs, ensure port 8000 is free, run `/smartx-model verify` |
| Inference latency > 200ms | Profile with `cProfile`, check for disk I/O, reduce feature count |

---

## Files Modified by This Skill

- `04_Codigo/assets/models/smartx_model_v2.pkl` — created by XGBoost training
- `04_Codigo/assets/models/encoder_motivo.pkl` — created by XGBoost training
- `04_Codigo/smartx_api.py` — `modelo_version` string updated on deploy
- (Optional) git commit message with version tag

---

## Cross-References

- Full dataset docs: [SmartX_Dataset_Integration_Resumen.md](04_Codigo/docs/SmartX_Dataset_Integration_Resumen.md)
- Training scripts: `04_Codigo/models/clasificacion.py`, `smartx_entrenamiento_rf.py`
- Inference engine: `04_Codigo/smartx_motor_inferencia.py` (8-step pipeline)
- API: `04_Codigo/smartx_api.py` (output contract in `SemaforoOutput`)
