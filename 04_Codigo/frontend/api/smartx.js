// SmartX API Client — Hospital Civil de Guadalajara
// Endpoint base: http://localhost:8000

const API_BASE_URL = "http://localhost:8000";

/**
 * Mapea los campos del formulario HTML al contrato de SintomasInput (Pydantic).
 * Los nombres del form y de la API son distintos — este es el punto de traducción.
 */
function mapFormToAPI(form) {
  const disnea =
    form.redflag_disnea_severa === "Sí" ||
    form.dificultad_respiratoria === "Sí";

  const perdidaConciencia =
    form.redflag_deficit_neurologico_subito === "Sí" ||
    form.confusion === "Sí";

  const sangrado =
    form.redflag_sangrado_abundante === "Sí" ||
    form.sangrado_activo === "Sí";

  const intensidad =
    form.intensidad_sintoma !== "" && form.intensidad_sintoma !== undefined
      ? parseInt(form.intensidad_sintoma)
      : null;

  const texto =
    form.sintomas_texto && form.sintomas_texto.trim().length >= 10
      ? form.sintomas_texto.trim()
      : null;

  const embarazo =
    form.sexo_biologico === "F" && form.embarazo === "Sí" ? true : null;

  return {
    edad: parseInt(form.edad),
    sexo_biologico: form.sexo_biologico || "M",
    disnea_presente: disnea,
    perdida_conciencia: perdidaConciencia,
    sangrado_activo: sangrado,
    fiebre_presente: form.fiebre_reportada === "Sí",
    temperatura_celsius: null,
    intensidad_dolor_eva: intensidad,
    duracion_sintoma_horas: null,
    sintomas_texto: texto,
    diabetes_mellitus: false,
    hipertension: false,
    cardiopatia_isquemica:
      form.redflag_dolor_toracico_opresivo_con_sudoracion === "Sí",
    epoc_asma: false,
    embarazo_posible: embarazo,
    semanas_gestacion: null,
  };
}

/**
 * POST /api/v1/inferencia — clasificación de triage.
 * Devuelve { nivel_ia, probabilidades, escenarios, explicacion_shap, analisis_llm }
 */
async function procesarTriaje(formData) {
  const payload = mapFormToAPI(formData);

  const response = await fetch(`${API_BASE_URL}/api/v1/inferencia`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(
      err?.error?.detalle || err?.error || `HTTP ${response.status}`
    );
  }

  return response.json();
}

/** GET / — health check básico */
async function verificarEstado() {
  const response = await fetch(`${API_BASE_URL}/`);
  return response.json();
}

/** GET /api/v1/catalogo/escenarios */
async function obtenerCatalogo() {
  const response = await fetch(`${API_BASE_URL}/api/v1/catalogo/escenarios`);
  return response.json();
}

/** GET /api/v1/paciente/{id}/historial */
async function obtenerHistorial(idPaciente) {
  const response = await fetch(
    `${API_BASE_URL}/api/v1/paciente/${idPaciente}/historial`
  );
  return response.json();
}
