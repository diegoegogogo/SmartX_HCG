[README.md](https://github.com/user-attachments/files/27270298/README.md)
# SmartX HCG - Estructura del Proyecto

## 📁 Organización de Carpetas

```
04_Codigo/
├── backend/                    # API FastAPI
│   ├── app/
│   │   └── routers/
│   │       └── triaje.py      # Endpoints de triaje
│   └── motor_inferencia/       # Motor de inferencia médica
│
├── frontend/                   # Dashboard React/Streamlit
│   ├── smartx_dashboard.html   # Vista HTML principal
│   ├── smartx_dashboard.jsx    # Componentes React
│   ├── streamlit_app.py        # App Streamlit
│   ├── api/                    # Cliente API
│   └── components/             # Componentes React
│
├── data/                       # Datasets y datos de entrada
│   └── dataset_SmartX_2200_casos_con_ruido.xlsx
│
├── models/                     # Scripts de entrenamiento
│   ├── clasificacion.py        # Entrenamiento XGBoost
│   └── smartx_entrenamiento_rf.py  # Entrenamiento Random Forest
│
├── scripts/                    # Scripts de utilidad
│   ├── smartx_motor_inferencia.py     # Motor de inferencia v1
│   └── smartx_motor_inferencia_v2.py  # Motor de inferencia v2
│
├── docs/                       # Documentación del proyecto
│   ├── SmartX_Dataset_Integration_Resumen.md
│   ├── SmartX_Frontend_Integration_Guide.md
│   └── SmartX_Mermaid_Diagramas.md
│
├── assets/                     # Recursos generados (modelos, etc)
│   └── models/                 # Modelos entrenados (.pkl)
│
├── cachedir/                   # Cache de joblib
│
├── .venv/                      # Virtual environment
│
├── requirements.txt            # Dependencias Python
├── .env.example               # Variables de entorno (ejemplo)
├── smartx_api.py              # API principal
├── smartx_dashboard.html      # Dashboard HTML
└── smartx_dashboard.jsx       # Dashboard React
```

## 🚀 Uso

### 1. **Entrenar Modelo**
```bash
cd models
python clasificacion.py
```

Esto:
- Lee datos desde `../data/dataset_SmartX_2200_casos_con_ruido.xlsx`
- Entrena modelo XGBoost
- Guarda modelo en `../assets/models/smartx_model_v2.pkl`
- Guarda encoder en `../assets/models/encoder_motivo.pkl`

### 2. **Ejecutar API**
```bash
python smartx_api.py
```

### 3. **Ejecutar Frontend**
```bash
cd frontend
python streamlit_app.py
```

## 📦 Instalación

```bash
# Crear virtual environment
python -m venv .venv

# Activar (Windows)
.venv\Scripts\activate

# Instalar dependencias
pip install -r requirements.txt
```

## 📝 Notas

- Los modelos entrenados se guardan en `assets/models/`
- Los datos de entrada van en `data/`
- Scripts de utilidad y desarrollo van en `scripts/`
- Documentación en `docs/`

