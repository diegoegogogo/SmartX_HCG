import pandas as pd
import numpy as np
from xgboost import XGBClassifier
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
import joblib
import os

# 1. CARGA DE DATOS (Solucionando el problema de las pestañas)
archivo = os.path.join("..", "datasets", "dataset_SmartX_2200_casos_con_ruido.xlsx")

# Verificar que el archivo existe
if not os.path.exists(archivo):
    raise FileNotFoundError(f"❌ El archivo {archivo} no existe en la ruta actual: {os.getcwd()}")

# Obtener nombres de las hojas disponibles
try:
    xls = pd.ExcelFile(archivo)
    print(f"📊 Hojas disponibles en el archivo: {xls.sheet_names}\n")
    
    # Cargamos las características (X) y las etiquetas (y)
    # Usar las hojas específicas del dataset
    if "entrenamiento" in xls.sheet_names and "etiquetas_entrenamiento" in xls.sheet_names:
        df_x = pd.read_excel(archivo, sheet_name="entrenamiento")
        df_y = pd.read_excel(archivo, sheet_name="etiquetas_entrenamiento")
    else:
        # Fallback: usar la primera hoja de datos y segunda hoja
        hojas = [h for h in xls.sheet_names if h not in ['README', 'diccionario_variables', 'catalogos', 'distribucion_objetivo', 'referencias_clinicas', 'QA_revision']]
        print(f"Hojas de datos detectadas: {hojas}\n")
        if len(hojas) >= 2:
            df_x = pd.read_excel(archivo, sheet_name=hojas[0])
            df_y = pd.read_excel(archivo, sheet_name=hojas[1])
        else:
            raise ValueError("❌ No se encontraron suficientes hojas de datos")
    
except PermissionError:
    print("❌ ERROR: El archivo Excel está siendo usado por otro programa.")
    print("   ⚠️  Por favor cierra Excel u otro programa que tenga abierto el archivo.")
    print("   📂 Ruta: dataset_SmartX_2200_casos_con_ruido.xlsx")
    exit(1)
except Exception as e:
    print(f"❌ Error al leer el Excel: {type(e).__name__}: {e}")
    exit(1)

print(f"Columnas en hoja de características: {df_x.columns.tolist()}")
print(f"Columnas en hoja de etiquetas: {df_y.columns.tolist()}\n")

# Unimos por ID de paciente (detectar automáticamente la columna ID)
id_col = 'patient_id' if 'patient_id' in df_x.columns else df_x.columns[0]
df = pd.merge(df_x, df_y, on=id_col, how='inner')

# 2. LIMPIEZA DE DATOS (Data Cleaning)
# Eliminamos columnas que no sirven para la predicción médica
columnas_a_eliminar = [col for col in ['patient_id', 'enfermedad_simulada', 'id'] if col in df.columns]
df = df.drop(columnas_a_eliminar, axis=1)

print(f"Columnas después de limpieza: {df.columns.tolist()}\n")

# 3. TRANSFORMACIÓN (Encoding)
# XGBoost solo entiende números. Convertimos Categorías -> Números
if 'motivo_consulta' in df.columns:
    le_motivo = LabelEncoder()
    df['motivo_consulta'] = le_motivo.fit_transform(df['motivo_consulta'].astype(str))
else:
    le_motivo = None
    print("⚠️  Columna 'motivo_consulta' no encontrada")

# Convertimos booleanos (Sí/No) a (1/0)
columnas_si_no = ['embarazo', 'fiebre_reportada', 'tos', 'dificultad_respiratoria', 
                  'dolor_toracico', 'dolor_al_orinar', 'sangrado_activo', 'confusion',
                  'disminucion_movimientos_fetales',
                  'redflag_disnea_severa', 'redflag_sangrado_abundante', 
                  'redflag_deficit_neurologico_subito', 'redflag_dolor_toracico_opresivo_con_sudoracion']

for col in columnas_si_no:
    if col in df.columns:
        # Convertir a string primero, luego mapear valores
        df[col] = df[col].astype(str).str.strip().str.lower()
        df[col] = df[col].map({
            'sí': 1, 'si': 1, 'true': 1, '1': 1, '1.0': 1,
            'no': 0, 'false': 0, '0': 0, '0.0': 0,
            'no aplica': 0, 'n/a': 0
        }).fillna(0).astype(int)
    else:
        print(f"⚠️  Columna '{col}' no encontrada en los datos")

# Mapeo del Objetivo (Target)
mapa_gravedad = {
    "rojo": 0, "red": 0,
    "amarillo": 1, "yellow": 1, 
    "verde": 2, "green": 2
}
target_col = 'gravedad_esperada_IA' if 'gravedad_esperada_IA' in df.columns else 'gravedad'
if target_col in df.columns:
    df['target'] = df[target_col].astype(str).str.lower().map(mapa_gravedad).fillna(2).astype(int)
    print(f"Distribución de clases:\n{df['target'].value_counts().sort_index()}\n")
else:
    raise ValueError(f"❌ Columna de gravedad no encontrada. Columnas disponibles: {df.columns.tolist()}")

# 4. ENTRENAMIENTO
# Preparar features (X) y target (y)
columnas_a_descartar = [col for col in ['gravedad_esperada_IA', 'target', 'antecedentes_riesgo', 'sintomas_digestivos', 'gravedad'] if col in df.columns]
X = df.drop(columnas_a_descartar, axis=1)
y = df['target']

# Validar que no hay valores nulos críticos
print(f"Valores nulos por columna:\n{X.isnull().sum()}\n")
X = X.fillna(X.mean(numeric_only=True))

# Split datos
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

print(f"Datos de entrenamiento: {X_train.shape}")
print(f"Datos de prueba: {X_test.shape}\n")

# Entrenar modelo
model = XGBClassifier(n_estimators=100, learning_rate=0.1, max_depth=5, random_state=42)
model.fit(X_train, y_train)

# Evaluación
train_score = model.score(X_train, y_train)
test_score = model.score(X_test, y_test)
print(f"Precisión en entrenamiento: {train_score:.4f}")
print(f"Precisión en pruebas: {test_score:.4f}\n")

# 5. GUARDADO DE ASSETS
output_dir = os.path.join("..", "assets", "models")  # Guardar en carpeta de assets
os.makedirs(output_dir, exist_ok=True)

try:
    joblib.dump(model, os.path.join(output_dir, 'smartx_model_v2.pkl'))
    if le_motivo is not None:
        joblib.dump(le_motivo, os.path.join(output_dir, 'encoder_motivo.pkl'))
    print("✅ Modelo entrenado y guardado con éxito.")
    print(f"   - Modelo: {os.path.abspath(os.path.join(output_dir, 'smartx_model_v2.pkl'))}")
    if le_motivo is not None:
        print(f"   - Encoder: {os.path.abspath(os.path.join(output_dir, 'encoder_motivo.pkl'))}")
except Exception as e:
    print(f"❌ Error al guardar los archivos: {e}")


