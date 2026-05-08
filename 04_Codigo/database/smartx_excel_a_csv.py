"""
SmartX HCG — Convertir Excel a CSV para importar en Supabase
Ejecutar desde 04_Codigo/:
    python smartx_excel_a_csv.py
Genera: data/smartx_casos_supabase.csv  (2,200 filas, listo para Supabase)
"""

import pandas as pd
from pathlib import Path

EXCEL = Path("data/dataset_SmartX_2200_casos_con_ruido.xlsx")
SALIDA = Path("data/smartx_casos_supabase.csv")

def si_no_a_bool(valor) -> str:
    """Convierte Sí/No a TRUE/FALSE que entiende PostgreSQL. 'No aplica' → vacío (NULL)."""
    if pd.isna(valor):
        return ""
    v = str(valor).strip().lower()
    if v in ("sí", "si"):  return "TRUE"
    if v == "no":           return "FALSE"
    return ""  # No aplica → NULL

def a_int(valor) -> object:
    """Convierte a int; retorna None (NULL en CSV) si el valor es NaN."""
    return int(valor) if pd.notna(valor) else None

def a_str(valor) -> str:
    """Convierte a str limpio; retorna '' si el valor es NaN (no produce 'nan')."""
    return str(valor).strip() if pd.notna(valor) else ""

print("📂 Leyendo Excel...")

hojas = {
    "entrenamiento": (
        pd.read_excel(EXCEL, sheet_name="entrenamiento"),
        pd.read_excel(EXCEL, sheet_name="etiquetas_entrenamiento").set_index("patient_id"),
    ),
    "validacion": (
        pd.read_excel(EXCEL, sheet_name="validacion"),
        pd.read_excel(EXCEL, sheet_name="etiquetas_validacion").set_index("patient_id"),
    ),
    "prueba": (
        pd.read_excel(EXCEL, sheet_name="prueba"),
        pd.read_excel(EXCEL, sheet_name="etiquetas_prueba").set_index("patient_id"),
    ),
}

COLS_BOOL = [
    "fiebre_reportada", "tos", "dificultad_respiratoria",
    "dolor_toracico", "dolor_al_orinar", "sangrado_activo", "confusion",
    "redflag_disnea_severa", "redflag_sangrado_abundante",
    "redflag_deficit_neurologico_subito",
    "redflag_dolor_toracico_opresivo_con_sudoracion",
]

filas = []
for split, (df, etiq) in hojas.items():
    for _, r in df.iterrows():
        pid = r["patient_id"]
        e_row = etiq.loc[[pid]].iloc[0] if pid in etiq.index else None
        filas.append({
            "patient_id":            pid,
            "split":                 split,
            "edad":                  a_int(r["edad"]),
            "embarazo":              si_no_a_bool(r["embarazo"]),
            "motivo_consulta":       a_str(r["motivo_consulta"]),
            "tiempo_evolucion_horas": a_int(r["tiempo_evolucion_horas"]),
            "intensidad_sintoma":    a_int(r["intensidad_sintoma"]),
            "antecedentes_riesgo":   a_str(r["antecedentes_riesgo"]),
            **{col: si_no_a_bool(r[col]) for col in COLS_BOOL},
            "sintomas_digestivos":   a_str(r["sintomas_digestivos"]),
            "disminucion_movimientos_fetales": si_no_a_bool(r["disminucion_movimientos_fetales"]),
            "enfermedad_simulada":   a_str(e_row["enfermedad_simulada"]) if e_row is not None else "",
            "gravedad_esperada_ia":  a_str(e_row["gravedad_esperada_IA"]) if e_row is not None else "",
        })

df_final = pd.DataFrame(filas)
df_final.to_csv(SALIDA, index=False, encoding="utf-8-sig")

print(f"✅ CSV generado: {SALIDA}")
print(f"   Filas: {len(df_final)}")
print(f"   Columnas: {len(df_final.columns)}")
print(f"\nAhora en Supabase:")
print(f"  Table Editor → casos_clinicos → Import data → sube {SALIDA.name}")
