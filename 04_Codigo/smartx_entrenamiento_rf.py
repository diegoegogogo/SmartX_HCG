"""
╔══════════════════════════════════════════════════════════════════════════════╗
║      SMART X — Script de Entrenamiento Random Forest                         ║
║      smartx_entrenamiento_rf.py                                              ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  Uso:                                                                        ║
║    1. Coloca tu dataset en: dataset_hcg.csv                                  ║
║    2. Ejecuta: python smartx_entrenamiento_rf.py                             ║
║    3. El modelo se guarda en: smartx_rf_modelo.pkl                           ║
║    4. Coloca el .pkl junto a smartx_motor_inferencia_v2.py                   ║
║                                                                              ║
║  Instalación:                                                                ║
║    pip install scikit-learn pandas joblib shap matplotlib seaborn            ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import pandas as pd
import numpy as np
import json
import warnings
warnings.filterwarnings('ignore')

try:
    import joblib
except ImportError:
    raise ImportError(
        "joblib no está instalado. Instala con: pip install joblib"
    )

from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split, StratifiedKFold, cross_val_score
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import (
    classification_report, confusion_matrix,
    roc_auc_score, f1_score
)
from sklearn.inspection import permutation_importance

# ── Intentar importar SHAP (opcional pero recomendado) ───────────────────────
try:
    import shap
    SHAP_DISPONIBLE = True
except ImportError:
    SHAP_DISPONIBLE = False
    print("ℹ️  SHAP no instalado. Instala con: pip install shap")


# ══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 1 — CONFIGURACIÓN
# ══════════════════════════════════════════════════════════════════════════════

RUTA_DATASET   = "dataset_hcg.csv"      # Tu dataset del HCG
RUTA_MODELO    = "smartx_rf_modelo.pkl" # Donde se guarda el modelo
VARIABLE_OBJETIVO = "semaforo_medico"   # rojo / amarillo / verde
SEMILLA        = 42                     # Reproducibilidad

# Columnas de entrada — deben coincidir con _paciente_a_vector() en el motor
COLUMNAS_X = [
    "edad",
    "sexo_f",                 # 1=Femenino, 0=Masculino
    "intensidad_eva",
    "duracion_horas",
    "temperatura_celsius",
    "fiebre_presente",
    "diabetes_mellitus",
    "hipertension",
    "cardiopatia_isquemica",
    "epoc_asma",
    "embarazo_posible",
    "imc",
    "semanas_gestacion",
]

# Hiperparámetros del Random Forest
# Ajustar según el tamaño del dataset del HCG
RF_PARAMS = {
    "n_estimators"  : 200,    # Número de árboles — más = mejor pero más lento
    "max_depth"     : 10,     # Profundidad máxima — evita sobreajuste
    "min_samples_split": 5,   # Mínimo de muestras para dividir un nodo
    "min_samples_leaf" : 2,   # Mínimo de muestras en hoja
    "class_weight"  : "balanced", # Compensa si hay pocos casos ROJO
    "random_state"  : SEMILLA,
    "n_jobs"        : -1,     # Usa todos los núcleos disponibles
}


# ══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 2 — CARGA Y PREPARACIÓN DEL DATASET
# ══════════════════════════════════════════════════════════════════════════════

def cargar_dataset(ruta: str) -> pd.DataFrame:
    """
    Carga el dataset y verifica que tenga las columnas necesarias.

    Formato esperado del CSV:
    edad,sexo_biologico,intensidad_eva,duracion_horas,temperatura_celsius,
    fiebre_presente,diabetes_mellitus,hipertension,cardiopatia_isquemica,
    epoc_asma,embarazo_posible,peso_kg,talla_cm,semanas_gestacion,semaforo_medico

    La columna semaforo_medico debe tener valores: rojo, amarillo, verde
    """
    print(f"\n{'='*60}")
    print(f"  Cargando dataset: {ruta}")
    print(f"{'='*60}")

    df = pd.read_csv(ruta)
    print(f"  Registros totales: {len(df):,}")
    print(f"  Columnas: {list(df.columns)}")
    return df


def preparar_features(df: pd.DataFrame) -> tuple:
    """
    Transforma el DataFrame al formato de entrada del modelo.
    Genera las mismas columnas que _paciente_a_vector() en el motor.
    """
    # Calcular IMC si no existe
    if "imc" not in df.columns:
        df["imc"] = df["peso_kg"] / (df["talla_cm"] / 100) ** 2
        df["imc"] = df["imc"].fillna(0)

    # Convertir sexo a binario
    if "sexo_f" not in df.columns:
        df["sexo_f"] = (df["sexo_biologico"].str.upper() == "F").astype(int)

    # Rellenar nulos con 0 (equivalente a "no aplica")
    for col in COLUMNAS_X:
        if col in df.columns:
            df[col] = df[col].fillna(0)
        else:
            df[col] = 0  # Columna ausente → agregar con 0

    X = df[COLUMNAS_X].values.astype(float)
    y = df[VARIABLE_OBJETIVO].values
    y = np.asarray(y, dtype=object)  # Ensure compatibility with np.unique()

    print(f"\n  Variables de entrada (X): {X.shape}")
    print(f"  Variable objetivo (y): {np.unique(y, return_counts=True)}")
    print(f"\n  Distribución del semáforo:")
    for clase, count in zip(*np.unique(y, return_counts=True)):
        pct = count / len(y) * 100
        barra = "█" * int(pct / 2)
        print(f"    {clase:10s}: {count:4d} casos ({pct:.1f}%) {barra}")

    return X, y


# ══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 3 — ENTRENAMIENTO Y EVALUACIÓN
# ══════════════════════════════════════════════════════════════════════════════

def entrenar_modelo(X, y) -> tuple:
    """
    Entrena el Random Forest con validación cruzada estratificada.
    Retorna el modelo entrenado y los splits de evaluación.
    """
    print(f"\n{'='*60}")
    print(f"  Entrenando Random Forest")
    print(f"  Parámetros: {RF_PARAMS}")
    print(f"{'='*60}")

    # División entrenamiento / prueba (80/20)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y,
        test_size    = 0.2,
        random_state = SEMILLA,
        stratify     = y  # mantiene proporción de clases en ambos sets
    )
    print(f"\n  Train: {len(X_train)} casos | Test: {len(X_test)} casos")

    # Validación cruzada (5-fold) para estimar rendimiento real
    modelo = RandomForestClassifier(**RF_PARAMS)
    cv_scores = cross_val_score(
        modelo, X_train, y_train,
        cv      = StratifiedKFold(n_splits=5, shuffle=True, random_state=SEMILLA),
        scoring = "f1_macro",
        n_jobs  = -1,
    )
    print(f"\n  Validación cruzada (5-fold F1 macro):")
    print(f"    {cv_scores.round(3)}")
    print(f"    Media: {cv_scores.mean():.3f} ± {cv_scores.std():.3f}")

    # Entrenamiento final con todo el set de train
    modelo.fit(X_train, y_train)

    return modelo, X_train, X_test, y_train, y_test


def evaluar_modelo(modelo, X_test, y_test) -> dict:
    """
    Evalúa el modelo en el set de prueba.
    Métricas clínicas clave: sensibilidad ROJO, especificidad VERDE, F1 macro.
    """
    print(f"\n{'='*60}")
    print(f"  Evaluación en set de prueba")
    print(f"{'='*60}")

    y_pred = modelo.predict(X_test)
    y_prob = modelo.predict_proba(X_test)

    # Reporte completo
    print(f"\n{classification_report(y_test, y_pred, digits=3)}")

    # Métricas específicas para Smart X
    clases = modelo.classes_
    idx_rojo = list(clases).index("rojo") if "rojo" in clases else None
    idx_verde = list(clases).index("verde") if "verde" in clases else None

    metricas = {}

    if idx_rojo is not None:
        from sklearn.metrics import recall_score, precision_score
        y_bin_rojo = (y_test == "rojo").astype(int)
        y_pred_rojo = (y_pred == "rojo").astype(int)
        metricas["sensibilidad_rojo"] = recall_score(y_bin_rojo, y_pred_rojo)
        metricas["precision_rojo"]    = precision_score(y_bin_rojo, y_pred_rojo, zero_division=0)
        print(f"\n  ⚕️  Métricas clínicas clave:")
        print(f"    Sensibilidad ROJO (recall):  {metricas['sensibilidad_rojo']:.3f}  ← debe ser > 0.90")
        print(f"    Precisión ROJO:              {metricas['precision_rojo']:.3f}")
        if metricas["sensibilidad_rojo"] < 0.90:
            print(f"    ⚠️  ADVERTENCIA: Sensibilidad ROJO < 0.90. Considera ajustar class_weight.")

    metricas["f1_macro"] = f1_score(y_test, y_pred, average="macro")
    print(f"    F1 Macro global:             {metricas['f1_macro']:.3f}")

    # Matriz de confusión
    print(f"\n  Matriz de confusión:")
    mc = confusion_matrix(y_test, y_pred, labels=clases)
    print(f"  Clases: {list(clases)}")
    print(mc)

    return metricas


def analizar_importancia(modelo, X_train, y_train) -> None:
    """Muestra las variables más importantes del modelo."""
    print(f"\n{'='*60}")
    print(f"  Importancia de variables")
    print(f"{'='*60}")

    importancias = modelo.feature_importances_
    pares = sorted(
        zip(COLUMNAS_X, importancias),
        key=lambda x: x[1], reverse=True
    )
    for nombre, imp in pares:
        barra = "█" * int(imp * 50)
        print(f"  {nombre:25s}: {imp:.4f}  {barra}")


# ══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 4 — ANÁLISIS SHAP (si está disponible)
# ══════════════════════════════════════════════════════════════════════════════

def analizar_shap(modelo, X_train) -> None:
    """
    Calcula SHAP values reales para el modelo Random Forest.
    En producción estos valores reemplazan los pesos heurísticos del motor.
    """
    if not SHAP_DISPONIBLE:
        print("\n  ℹ️  SHAP no disponible. Instala con: pip install shap")
        return

    print(f"\n{'='*60}")
    print(f"  Análisis SHAP (valores reales de explicabilidad)")
    print(f"{'='*60}")

    # Usar muestra para eficiencia
    muestra = X_train[:min(100, len(X_train))]
    explainer    = shap.TreeExplainer(modelo)
    shap_values  = explainer.shap_values(muestra)

    # Importancia SHAP media por variable
    if isinstance(shap_values, list):
        # Multi-clase: promediar entre clases
        shap_abs = np.mean([np.abs(sv) for sv in shap_values], axis=0)
    else:
        shap_abs = np.abs(shap_values)

    importancia_shap = shap_abs.mean(axis=0)
    pares_shap = sorted(
        zip(COLUMNAS_X, importancia_shap),
        key=lambda x: x[1], reverse=True
    )

    print(f"\n  SHAP values medios (mayor = más importante para el modelo):")
    for nombre, val in pares_shap:
        barra = "█" * int(val * 100)
        print(f"  {nombre:25s}: {val:.4f}  {barra}")

    # Guardar SHAP weights para actualizar el motor
    shap_weights = {nombre: round(float(val), 4) for nombre, val in pares_shap}
    with open("smartx_shap_weights.json", "w") as f:
        json.dump(shap_weights, f, indent=2, ensure_ascii=False)
    print(f"\n  ✅ SHAP weights guardados en: smartx_shap_weights.json")
    print(f"     Actualiza PESOS_SHAP en smartx_motor_inferencia_v2.py con estos valores.")


# ══════════════════════════════════════════════════════════════════════════════
# SECCIÓN 5 — DATASET SINTÉTICO (para pruebas sin datos reales)
# ══════════════════════════════════════════════════════════════════════════════

def generar_dataset_sintetico(n_casos: int = 500) -> pd.DataFrame:
    """
    Genera un dataset sintético para pruebas cuando no hay datos del HCG.
    NO usar en producción — solo para validar el pipeline de entrenamiento.

    La distribución de casos refleja la realidad clínica estimada:
    - 15% ROJO (casos urgentes)
    - 35% AMARILLO (casos prioritarios)
    - 50% VERDE (casos no urgentes)
    """
    print(f"\n  ⚠️  Generando dataset SINTÉTICO ({n_casos} casos).")
    print(f"      Este dataset es solo para pruebas — NO para producción.")
    print(f"      Para el piloto real, usa datos reales del HCG.")

    rng = np.random.default_rng(42)
    filas = []

    niveles = rng.choice(
        ["rojo", "amarillo", "verde"],
        size=n_casos,
        p=[0.15, 0.35, 0.50]
    )

    for nivel in niveles:
        if nivel == "rojo":
            fila = {
                "edad"               : int(rng.integers(50, 90)),
                "sexo_biologico"     : rng.choice(["M", "F"]),
                "intensidad_eva"     : int(rng.integers(7, 11)),
                "duracion_horas"     : int(rng.integers(0, 4)),
                "temperatura_celsius": round(rng.uniform(38.5, 42.0), 1),
                "fiebre_presente"    : 1,
                "diabetes_mellitus"  : int(rng.choice([0, 1], p=[0.4, 0.6])),
                "hipertension"       : int(rng.choice([0, 1], p=[0.3, 0.7])),
                "cardiopatia_isquemica": int(rng.choice([0, 1], p=[0.3, 0.7])),
                "epoc_asma"          : int(rng.choice([0, 1], p=[0.5, 0.5])),
                "embarazo_posible"   : 0,
                "peso_kg"            : round(rng.uniform(60, 110), 1),
                "talla_cm"           : round(rng.uniform(150, 185), 1),
                "semanas_gestacion"  : 0,
                "semaforo_medico"    : "rojo",
            }
        elif nivel == "amarillo":
            fila = {
                "edad"               : int(rng.integers(30, 70)),
                "sexo_biologico"     : rng.choice(["M", "F"]),
                "intensidad_eva"     : int(rng.integers(4, 8)),
                "duracion_horas"     : int(rng.integers(2, 48)),
                "temperatura_celsius": round(rng.uniform(37.5, 39.5), 1),
                "fiebre_presente"    : int(rng.choice([0, 1], p=[0.3, 0.7])),
                "diabetes_mellitus"  : int(rng.choice([0, 1], p=[0.6, 0.4])),
                "hipertension"       : int(rng.choice([0, 1], p=[0.5, 0.5])),
                "cardiopatia_isquemica": int(rng.choice([0, 1], p=[0.7, 0.3])),
                "epoc_asma"          : int(rng.choice([0, 1], p=[0.7, 0.3])),
                "embarazo_posible"   : int(rng.choice([0, 1], p=[0.8, 0.2])),
                "peso_kg"            : round(rng.uniform(50, 100), 1),
                "talla_cm"           : round(rng.uniform(150, 185), 1),
                "semanas_gestacion"  : int(rng.integers(0, 42)) if rng.random() < 0.2 else 0,
                "semaforo_medico"    : "amarillo",
            }
        else:  # verde
            fila = {
                "edad"               : int(rng.integers(18, 65)),
                "sexo_biologico"     : rng.choice(["M", "F"]),
                "intensidad_eva"     : int(rng.integers(0, 5)),
                "duracion_horas"     : int(rng.integers(24, 720)),
                "temperatura_celsius": round(rng.uniform(36.0, 37.9), 1),
                "fiebre_presente"    : 0,
                "diabetes_mellitus"  : int(rng.choice([0, 1], p=[0.7, 0.3])),
                "hipertension"       : int(rng.choice([0, 1], p=[0.7, 0.3])),
                "cardiopatia_isquemica": 0,
                "epoc_asma"          : int(rng.choice([0, 1], p=[0.8, 0.2])),
                "embarazo_posible"   : 0,
                "peso_kg"            : round(rng.uniform(50, 90), 1),
                "talla_cm"           : round(rng.uniform(150, 180), 1),
                "semanas_gestacion"  : 0,
                "semaforo_medico"    : "verde",
            }
        filas.append(fila)

    df = pd.DataFrame(filas)
    df.to_csv(RUTA_DATASET, index=False)
    print(f"  Dataset sintético guardado en: {RUTA_DATASET}")
    return df


# ══════════════════════════════════════════════════════════════════════════════
# PUNTO DE ENTRADA
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import os

    print("\n╔══════════════════════════════════════════════════════════════╗")
    print("║  SMART X — Entrenamiento Random Forest  |  HCG Piloto 2026  ║")
    print("╚══════════════════════════════════════════════════════════════╝")

    # ── Paso 1: Cargar o generar dataset ─────────────────────────────────────
    if os.path.exists(RUTA_DATASET):
        df = cargar_dataset(RUTA_DATASET)
    else:
        print(f"\n  ⚠️  No se encontró '{RUTA_DATASET}'.")
        respuesta = input("  ¿Generar dataset SINTÉTICO para pruebas? (s/n): ").strip().lower()
        if respuesta == "s":
            df = generar_dataset_sintetico(n_casos=500)
            df = cargar_dataset(RUTA_DATASET)
        else:
            print("  Coloca tu dataset en dataset_hcg.csv y vuelve a ejecutar.")
            exit(0)

    # ── Paso 2: Preparar features ─────────────────────────────────────────────
    X, y = preparar_features(df)

    # ── Paso 3: Entrenar ──────────────────────────────────────────────────────
    modelo, X_train, X_test, y_train, y_test = entrenar_modelo(X, y)

    # ── Paso 4: Evaluar ───────────────────────────────────────────────────────
    metricas = evaluar_modelo(modelo, X_test, y_test)

    # ── Paso 5: Importancia de variables ─────────────────────────────────────
    analizar_importancia(modelo, X_train, y_train)

    # ── Paso 6: SHAP (opcional) ───────────────────────────────────────────────
    analizar_shap(modelo, X_train)

    # ── Paso 7: Guardar modelo ───────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  Guardando modelo en: {RUTA_MODELO}")
    joblib.dump(modelo, RUTA_MODELO)
    print(f"  ✅ Modelo guardado correctamente.")
    print(f"\n  Próximo paso:")
    print(f"  Coloca '{RUTA_MODELO}' junto a smartx_motor_inferencia_v2.py")
    print(f"  El motor lo detectará automáticamente al iniciar.")
    print(f"\n  Métricas finales:")
    for k, v in metricas.items():
        print(f"    {k}: {v:.4f}")
    print(f"{'='*60}\n")
