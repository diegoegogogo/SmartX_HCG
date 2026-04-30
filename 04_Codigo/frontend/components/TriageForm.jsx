import React, { useState } from 'react';
import { X, AlertTriangle, Stethoscope } from 'lucide-react';

const API = 'http://localhost:8000';

const INITIAL_FORM = {
  edad: '',
  sexo_biologico: 'M',
  embarazo: false,
  intensidad_sintoma: '5',
  fiebre_reportada: false,
  tos: false,
  dificultad_respiratoria: false,
  dolor_toracico: false,
  sangrado_activo: false,
  confusion: false,
  redflag_disnea_severa: false,
  redflag_sangrado_abundante: false,
  redflag_deficit_neurologico_subito: false,
  redflag_dolor_toracico_opresivo_con_sudoracion: false,
  sintomas_texto: '',
};

/** Convierte campos del form al contrato SintomasInput de la API Pydantic. */
function buildPayload(f) {
  const disnea   = f.redflag_disnea_severa || f.dificultad_respiratoria;
  const perdida  = f.redflag_deficit_neurologico_subito || f.confusion;
  const sangrado = f.redflag_sangrado_abundante || f.sangrado_activo;
  const texto    = (f.sintomas_texto || '').trim();

  return {
    edad:                  parseInt(f.edad),
    sexo_biologico:        f.sexo_biologico,
    disnea_presente:       disnea,
    perdida_conciencia:    perdida,
    sangrado_activo:       sangrado,
    fiebre_presente:       f.fiebre_reportada,
    temperatura_celsius:   null,
    intensidad_dolor_eva:  parseInt(f.intensidad_sintoma) || null,
    duracion_sintoma_horas: null,
    sintomas_texto:        texto.length >= 10 ? texto : null,
    diabetes_mellitus:     false,
    hipertension:          false,
    cardiopatia_isquemica: f.redflag_dolor_toracico_opresivo_con_sudoracion,
    epoc_asma:             false,
    embarazo_posible:      f.sexo_biologico === 'F' && f.embarazo ? true : null,
    semanas_gestacion:     null,
  };
}

/**
 * Formulario de triaje. Se encarga de la llamada a la API y devuelve
 * el resultado al padre via onResult(apiResponse).
 *
 * Props:
 *   onResult(apiResp) — callback con la respuesta del motor
 *   onClose()         — callback para cerrar el modal
 */
const TriageForm = ({ onResult, onClose }) => {
  const [form,       setForm]       = useState(INITIAL_FORM);
  const [processing, setProcessing] = useState(false);
  const [error,      setError]      = useState(null);

  const anyRedFlag = form.redflag_disnea_severa || form.redflag_sangrado_abundante ||
                     form.redflag_deficit_neurologico_subito ||
                     form.redflag_dolor_toracico_opresivo_con_sudoracion;

  const set = (key, val) => setForm(prev => ({ ...prev, [key]: val }));

  const handleSubmit = async (e) => {
    e.preventDefault();
    setProcessing(true);
    setError(null);

    const payload = buildPayload(form);

    try {
      const res = await fetch(`${API}/api/v1/inferencia`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
        signal: AbortSignal.timeout(15000),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err?.error?.detalle || `HTTP ${res.status}`);
      }

      const data = await res.json();
      onResult({ ...data, _modo: 'api', _form: form });
    } catch (err) {
      // Fallback local si el backend no responde
      const p = payload;
      let nivel = 'verde';
      if (p.disnea_presente || p.sangrado_activo || p.perdida_conciencia || p.cardiopatia_isquemica)
        nivel = 'rojo';
      else if ((p.intensidad_dolor_eva || 0) >= 7)
        nivel = 'amarillo';

      onResult({
        nivel_ia: nivel,
        probabilidades: {},
        escenarios: [{ nombre: 'Clasificación local (sin API)', probabilidad: 0.7 }],
        explicacion_shap: 'Motor no disponible — clasificación local',
        analisis_llm: null,
        _modo: 'simulacion',
        _form: form,
      });
    } finally {
      setProcessing(false);
    }
  };

  return (
    <div className="fixed inset-0 bg-black/80 flex items-center justify-center p-4 z-50">
      <div className="bg-slate-800 rounded-xl p-6 w-full max-w-4xl max-h-screen overflow-y-auto border border-slate-600">

        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-2xl font-bold text-blue-400">NUEVO TRIAJE DE PACIENTE</h2>
          <button onClick={onClose} className="text-slate-400 hover:text-white">
            <X className="w-8 h-8" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-6">

          {/* Datos demográficos */}
          <div className="bg-slate-700 p-4 rounded-lg">
            <h3 className="text-xl font-bold text-slate-200 mb-4">DATOS DEMOGRÁFICOS</h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div>
                <label className="block text-slate-300 font-bold mb-2">EDAD *</label>
                <input type="number" required min="0" max="120"
                  value={form.edad} onChange={e => set('edad', e.target.value)}
                  className="w-full bg-slate-600 border border-slate-500 rounded-lg px-4 py-3 text-white text-lg font-bold"
                  placeholder="0-120" />
              </div>
              <div>
                <label className="block text-slate-300 font-bold mb-2">SEXO *</label>
                <select value={form.sexo_biologico} onChange={e => set('sexo_biologico', e.target.value)}
                  className="w-full bg-slate-600 border border-slate-500 rounded-lg px-4 py-3 text-white text-lg font-bold">
                  <option value="M">Masculino</option>
                  <option value="F">Femenino</option>
                </select>
              </div>
              <div>
                <label className="block text-slate-300 font-bold mb-2">EMBARAZO</label>
                <select value={form.embarazo ? 'Sí' : 'No'}
                  onChange={e => set('embarazo', e.target.value === 'Sí')}
                  className="w-full bg-slate-600 border border-slate-500 rounded-lg px-4 py-3 text-white text-lg font-bold">
                  <option value="No">No</option>
                  <option value="Sí">Sí</option>
                </select>
              </div>
              <div>
                <label className="block text-slate-300 font-bold mb-2">INTENSIDAD (0-10)</label>
                <input type="range" min="0" max="10" value={form.intensidad_sintoma}
                  onChange={e => set('intensidad_sintoma', e.target.value)}
                  className="w-full h-3 bg-slate-600 rounded-lg appearance-none cursor-pointer mt-3" />
                <div className="text-center">
                  <span className="text-2xl font-bold text-yellow-400">{form.intensidad_sintoma}</span>
                </div>
              </div>
            </div>
          </div>

          {/* Banderas rojas */}
          <div className="bg-red-900/30 border border-red-500 p-4 rounded-lg">
            <h3 className="text-xl font-bold text-red-400 mb-4 flex items-center space-x-2">
              <AlertTriangle className="w-6 h-6" />
              <span>BANDERAS ROJAS CRÍTICAS</span>
              <span className="text-sm bg-red-600 px-2 py-0.5 rounded ml-2">BYPASS AUTOMÁTICO</span>
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {[
                { key: 'redflag_disnea_severa',                          label: 'DISNEA SEVERA' },
                { key: 'redflag_sangrado_abundante',                     label: 'SANGRADO ABUNDANTE' },
                { key: 'redflag_deficit_neurologico_subito',              label: 'DÉFICIT NEUROLÓGICO' },
                { key: 'redflag_dolor_toracico_opresivo_con_sudoracion', label: 'DOLOR TORÁCICO + SUDOR' },
              ].map(({ key, label }) => (
                <label key={key} className="flex items-center space-x-3 cursor-pointer bg-red-800/20 p-3 rounded border border-red-600 hover:bg-red-800/40">
                  <input type="checkbox" checked={form[key]}
                    onChange={e => set(key, e.target.checked)}
                    className="w-5 h-5 text-red-500" />
                  <span className="text-red-300 font-bold">{label}</span>
                </label>
              ))}
            </div>
            {anyRedFlag && (
              <div className="mt-4 bg-red-600 border border-red-400 p-3 rounded-lg flex items-center space-x-3">
                <AlertTriangle className="w-6 h-6 text-white animate-pulse" />
                <div>
                  <p className="text-white font-bold">¡BANDERA ROJA ACTIVADA!</p>
                  <p className="text-red-100 text-sm">Clasificación automática: CRÍTICO (ROJO)</p>
                </div>
              </div>
            )}
          </div>

          {/* Síntomas específicos */}
          <div className="bg-slate-700 p-4 rounded-lg">
            <h3 className="text-xl font-bold text-slate-200 mb-4">SÍNTOMAS ESPECÍFICOS</h3>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
              {[
                { key: 'fiebre_reportada',       label: 'Fiebre' },
                { key: 'tos',                    label: 'Tos' },
                { key: 'dificultad_respiratoria', label: 'Dificultad respiratoria' },
                { key: 'dolor_toracico',          label: 'Dolor torácico' },
                { key: 'sangrado_activo',         label: 'Sangrado activo' },
                { key: 'confusion',               label: 'Confusión / inconsciencia' },
              ].map(({ key, label }) => (
                <label key={key} className="flex items-center space-x-2 cursor-pointer">
                  <input type="checkbox" checked={form[key]}
                    onChange={e => set(key, e.target.checked)}
                    className="w-4 h-4 text-blue-500" />
                  <span className="text-slate-300 font-bold text-sm">{label}</span>
                </label>
              ))}
            </div>
          </div>

          {/* Texto libre */}
          <div className="bg-blue-900/30 border border-blue-500 p-4 rounded-lg">
            <h3 className="text-xl font-bold text-blue-400 mb-4 flex items-center space-x-2">
              <Stethoscope className="w-6 h-6" />
              <span>DESCRIPCIÓN LIBRE DE SÍNTOMAS</span>
            </h3>
            <textarea value={form.sintomas_texto}
              onChange={e => set('sintomas_texto', e.target.value)}
              className="w-full bg-slate-600 border border-slate-500 rounded-lg px-4 py-3 text-white h-28"
              placeholder="Mínimo 10 caracteres. Ej: Dolor en el pecho con irradiación al brazo izquierdo desde hace 2 horas…" />
          </div>

          {error && <p className="text-red-400 text-sm">{error}</p>}

          {/* Acciones */}
          <div className="flex space-x-4 pt-2">
            <button type="button" onClick={onClose}
              className="flex-1 bg-slate-600 hover:bg-slate-700 text-white px-6 py-4 rounded-lg font-bold text-lg">
              CANCELAR
            </button>
            <button type="submit" disabled={processing}
              className="flex-1 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white px-6 py-4 rounded-lg font-bold text-lg transition-all transform hover:scale-105">
              {processing ? 'PROCESANDO…' : 'PROCESAR TRIAJE'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default TriageForm;
