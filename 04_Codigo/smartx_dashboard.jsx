import React, { useState, useEffect } from 'react';
import { AlertTriangle, Heart, Activity, Clock, User, Plus, X, Check, AlertCircle, Stethoscope, Shield, Zap } from 'lucide-react';

const SmartXDashboard = () => {
  const [patients, setPatients] = useState([]);
  const [showNewPatient, setShowNewPatient] = useState(false);
  const [notifications, setNotifications] = useState([]);
  const [currentPatient, setCurrentPatient] = useState(null);

  // Estados del formulario
  const [formData, setFormData] = useState({
    edad: '',
    embarazo: 'No',
    motivo_consulta: '',
    tiempo_evolucion_horas: '',
    intensidad_sintoma: '',
    antecedentes_riesgo: 'Ninguno',
    fiebre_reportada: 'No',
    tos: 'No',
    dificultad_respiratoria: 'No',
    dolor_toracico: 'No',
    sintomas_digestivos: 'Ninguno',
    dolor_al_orinar: 'No',
    sangrado_activo: 'No',
    confusion: 'No',
    disminucion_movimientos_fetales: 'No aplica',
    redflag_disnea_severa: 'No',
    redflag_sangrado_abundante: 'No',
    redflag_deficit_neurologico_subito: 'No',
    redflag_dolor_toracico_opresivo_con_sudoracion: 'No',
    sintomas_texto: ''
  });

  // Simular datos de pacientes del día
  useEffect(() => {
    const samplePatients = [
      {
        id: 'PX-001',
        nombre: 'Paciente 001',
        edad: 65,
        hora_ingreso: '08:30',
        nivel: 'rojo',
        justificacion: 'Dolor Torácico Crítico',
        accion: 'PASAR A CHOQUE',
        tiempo_espera: 45,
        banderas_rojas: ['Dolor torácico opresivo'],
        sintomas_detectados: 'Dolor pecho, sudoración',
        patron_referencia: 'Síndrome coronario agudo (85%)'
      },
      {
        id: 'PX-002', 
        nombre: 'Paciente 002',
        edad: 32,
        hora_ingreso: '09:15',
        nivel: 'amarillo',
        justificacion: 'Fiebre Alta Persistente',
        accion: 'MONITOREO 30MIN',
        tiempo_espera: 20,
        banderas_rojas: [],
        sintomas_detectados: 'Fiebre, malestar general',
        patron_referencia: 'Influenza moderada (72%)'
      },
      {
        id: 'PX-003',
        nombre: 'Paciente 003', 
        edad: 28,
        hora_ingreso: '10:00',
        nivel: 'verde',
        justificacion: 'Síntomas Leves Inespecíficos',
        accion: 'SALA DE ESPERA',
        tiempo_espera: 10,
        banderas_rojas: [],
        sintomas_detectados: 'Dolor cabeza leve',
        patron_referencia: 'Cefalea tensional (65%)'
      }
    ];
    setPatients(samplePatients);
  }, []);

  const simulateTriageProcessing = async (data) => {
    // Simular procesamiento del motor SmartX
    await new Promise(resolve => setTimeout(resolve, 2000));
    
    // Simular resultado basado en datos
    let nivel = 'verde';
    let justificacion = 'Sintomatología Leve';
    let accion = 'SALA DE ESPERA';
    let banderasRojas = [];
    
    // Lógica simplificada de clasificación
    if (data.redflag_dolor_toracico_opresivo_con_sudoracion === 'Sí' ||
        data.redflag_disnea_severa === 'Sí' ||
        data.redflag_sangrado_abundante === 'Sí' ||
        data.redflag_deficit_neurologico_subito === 'Sí') {
      nivel = 'rojo';
      justificacion = 'Bandera Roja Crítica';
      accion = 'PASAR A CHOQUE';
      banderasRojas = ['Bandera roja detectada'];
    } else if (data.dificultad_respiratoria === 'Sí' || 
               data.dolor_toracico === 'Sí' ||
               parseInt(data.intensidad_sintoma) >= 7) {
      nivel = 'amarillo';
      justificacion = 'Síntomas Moderados';
      accion = 'MONITOREO 30MIN';
    }

    return {
      nivel,
      justificacion,
      accion,
      banderas_rojas: banderasRojas,
      sintomas_detectados: data.sintomas_texto || 'Síntomas estructurados',
      patron_referencia: 'Patrón clínico identificado',
      tiempo_procesamiento: '250ms'
    };
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    try {
      const resultado = await simulateTriageProcessing(formData);
      
      const newPatient = {
        id: `PX-${String(patients.length + 1).padStart(3, '0')}`,
        nombre: `Paciente ${String(patients.length + 1).padStart(3, '0')}`,
        edad: parseInt(formData.edad),
        hora_ingreso: new Date().toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' }),
        nivel: resultado.nivel,
        justificacion: resultado.justificacion,
        accion: resultado.accion,
        tiempo_espera: 0,
        banderas_rojas: resultado.banderas_rojas,
        sintomas_detectados: resultado.sintomas_detectados,
        patron_referencia: resultado.patron_referencia
      };

      setPatients([newPatient, ...patients]);
      
      // Notificación para casos críticos
      if (resultado.nivel === 'rojo') {
        addNotification({
          type: 'critical',
          title: 'CASO CRÍTICO DETECTADO',
          message: `${newPatient.id}: ${resultado.justificacion}`,
          action: resultado.accion
        });
      }

      setShowNewPatient(false);
      resetForm();
      
    } catch (error) {
      console.error('Error procesando triaje:', error);
    }
  };

  const addNotification = (notification) => {
    const id = Date.now();
    setNotifications(prev => [...prev, { ...notification, id }]);
    
    // Auto-remove after 10 seconds
    setTimeout(() => {
      setNotifications(prev => prev.filter(n => n.id !== id));
    }, 10000);
  };

  const resetForm = () => {
    setFormData({
      edad: '',
      embarazo: 'No',
      motivo_consulta: '',
      tiempo_evolucion_horas: '',
      intensidad_sintoma: '',
      antecedentes_riesgo: 'Ninguno',
      fiebre_reportada: 'No',
      tos: 'No',
      dificultad_respiratoria: 'No',
      dolor_toracico: 'No',
      sintomas_digestivos: 'Ninguno',
      dolor_al_orinar: 'No',
      sangrado_activo: 'No',
      confusion: 'No',
      disminucion_movimientos_fetales: 'No aplica',
      redflag_disnea_severa: 'No',
      redflag_sangrado_abundante: 'No',
      redflag_deficit_neurologico_subito: 'No',
      redflag_dolor_toracico_opresivo_con_sudoracion: 'No',
      sintomas_texto: ''
    });
  };

  const getPatientCardStyle = (nivel) => {
    switch(nivel) {
      case 'rojo':
        return 'bg-red-500 border-red-700 shadow-red-500/50 animate-pulse';
      case 'amarillo':
        return 'bg-yellow-500 border-yellow-700 shadow-yellow-500/30';
      case 'verde':
        return 'bg-green-500 border-green-700 shadow-green-500/20';
      default:
        return 'bg-gray-500 border-gray-700';
    }
  };

  const getUrgencyIcon = (nivel) => {
    switch(nivel) {
      case 'rojo':
        return <Zap className="w-8 h-8 text-white" />;
      case 'amarillo':
        return <Clock className="w-8 h-8 text-white" />;
      case 'verde':
        return <Check className="w-8 h-8 text-white" />;
      default:
        return <User className="w-8 h-8 text-white" />;
    }
  };

  return (
    <div className="min-h-screen bg-slate-900 text-white font-mono">
      {/* Header */}
      <header className="bg-slate-800 border-b-4 border-blue-500 p-4">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div className="flex items-center space-x-4">
            <div className="bg-blue-500 p-3 rounded-lg">
              <Stethoscope className="w-8 h-8 text-white" />
            </div>
            <div>
              <h1 className="text-3xl font-bold text-blue-400 tracking-tight">
                SMARTX TRIAJE
              </h1>
              <p className="text-slate-400 text-sm">
                Hospital Civil de Guadalajara | Sistema de Emergencias
              </p>
            </div>
          </div>
          
          <div className="flex items-center space-x-4">
            <div className="text-right">
              <p className="text-xl font-bold text-green-400">
                {new Date().toLocaleTimeString('es-ES')}
              </p>
              <p className="text-slate-400 text-sm">
                {new Date().toLocaleDateString('es-ES', { 
                  day: 'numeric', 
                  month: 'long', 
                  year: 'numeric' 
                })}
              </p>
            </div>
            
            <button 
              onClick={() => setShowNewPatient(true)}
              className="bg-blue-600 hover:bg-blue-700 text-white px-6 py-3 rounded-lg font-bold flex items-center space-x-2 transition-all transform hover:scale-105 shadow-lg"
            >
              <Plus className="w-5 h-5" />
              <span>NUEVO TRIAJE</span>
            </button>
          </div>
        </div>
      </header>

      {/* Stats Bar */}
      <div className="bg-slate-800 p-4 border-b border-slate-700">
        <div className="max-w-7xl mx-auto grid grid-cols-1 md:grid-cols-4 gap-4">
          <div className="bg-red-500/20 border border-red-500 rounded-lg p-4 text-center">
            <div className="flex items-center justify-center space-x-2 mb-2">
              <Zap className="w-6 h-6 text-red-400" />
              <h3 className="text-red-400 font-bold">CRÍTICOS</h3>
            </div>
            <p className="text-3xl font-bold text-red-400">
              {patients.filter(p => p.nivel === 'rojo').length}
            </p>
          </div>
          
          <div className="bg-yellow-500/20 border border-yellow-500 rounded-lg p-4 text-center">
            <div className="flex items-center justify-center space-x-2 mb-2">
              <Clock className="w-6 h-6 text-yellow-400" />
              <h3 className="text-yellow-400 font-bold">URGENTES</h3>
            </div>
            <p className="text-3xl font-bold text-yellow-400">
              {patients.filter(p => p.nivel === 'amarillo').length}
            </p>
          </div>
          
          <div className="bg-green-500/20 border border-green-500 rounded-lg p-4 text-center">
            <div className="flex items-center justify-center space-x-2 mb-2">
              <Check className="w-6 h-6 text-green-400" />
              <h3 className="text-green-400 font-bold">ESTABLES</h3>
            </div>
            <p className="text-3xl font-bold text-green-400">
              {patients.filter(p => p.nivel === 'verde').length}
            </p>
          </div>
          
          <div className="bg-slate-600/20 border border-slate-500 rounded-lg p-4 text-center">
            <div className="flex items-center justify-center space-x-2 mb-2">
              <Activity className="w-6 h-6 text-slate-400" />
              <h3 className="text-slate-400 font-bold">TOTAL HOY</h3>
            </div>
            <p className="text-3xl font-bold text-slate-400">
              {patients.length}
            </p>
          </div>
        </div>
      </div>

      {/* Main Dashboard */}
      <main className="max-w-7xl mx-auto p-6">
        <h2 className="text-2xl font-bold mb-6 text-slate-200">
          Dashboard de Pacientes - Hoy
        </h2>

        {/* Patient Cards Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {patients.map((patient) => (
            <div 
              key={patient.id}
              className={`${getPatientCardStyle(patient.nivel)} p-6 rounded-xl border-2 shadow-xl cursor-pointer transform transition-all hover:scale-105`}
              onClick={() => setCurrentPatient(patient)}
            >
              {/* Header with ID and Icon */}
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h3 className="text-2xl font-bold text-white">
                    {patient.id}
                  </h3>
                  <p className="text-white/80 text-sm">
                    {patient.hora_ingreso} | {patient.edad} años
                  </p>
                </div>
                <div className="flex flex-col items-center">
                  {getUrgencyIcon(patient.nivel)}
                  <span className="text-xs font-bold text-white mt-1">
                    {patient.nivel.toUpperCase()}
                  </span>
                </div>
              </div>

              {/* Justificación Médica */}
              <div className="mb-4">
                <h4 className="text-white font-bold text-lg leading-tight">
                  {patient.justificacion}
                </h4>
              </div>

              {/* Acción Requerida */}
              <div className="mb-4">
                <div className="bg-white/20 rounded-lg p-3">
                  <p className="text-white font-bold text-center text-lg">
                    {patient.accion}
                  </p>
                </div>
              </div>

              {/* Banderas Rojas */}
              {patient.banderas_rojas.length > 0 && (
                <div className="mb-4">
                  <div className="bg-red-800/50 border border-red-400 rounded-lg p-2">
                    <div className="flex items-center space-x-2">
                      <AlertTriangle className="w-4 h-4 text-red-200" />
                      <span className="text-red-200 font-bold text-sm">
                        BANDERAS ROJAS
                      </span>
                    </div>
                  </div>
                </div>
              )}

              {/* Tiempo de Espera */}
              <div className="flex items-center justify-between text-white/80 text-sm">
                <span>Tiempo espera:</span>
                <span className="font-bold">{patient.tiempo_espera} min</span>
              </div>
            </div>
          ))}
        </div>

        {patients.length === 0 && (
          <div className="text-center py-12">
            <User className="w-16 h-16 text-slate-600 mx-auto mb-4" />
            <h3 className="text-xl text-slate-400 mb-2">
              No hay pacientes registrados hoy
            </h3>
            <p className="text-slate-500 mb-6">
              Haz clic en "NUEVO TRIAJE" para comenzar
            </p>
          </div>
        )}
      </main>

      {/* New Patient Modal */}
      {showNewPatient && (
        <div className="fixed inset-0 bg-black/80 flex items-center justify-center p-4 z-50">
          <div className="bg-slate-800 rounded-xl p-6 w-full max-w-4xl max-h-screen overflow-y-auto border border-slate-600">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-2xl font-bold text-blue-400">
                NUEVO TRIAJE DE PACIENTE
              </h2>
              <button 
                onClick={() => setShowNewPatient(false)}
                className="text-slate-400 hover:text-white"
              >
                <X className="w-8 h-8" />
              </button>
            </div>

            <form onSubmit={handleSubmit} className="space-y-6">
              {/* Datos Demográficos */}
              <div className="bg-slate-700 p-4 rounded-lg">
                <h3 className="text-xl font-bold text-slate-200 mb-4">
                  DATOS DEMOGRÁFICOS
                </h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-slate-300 font-bold mb-2">
                      EDAD (años) *
                    </label>
                    <input 
                      type="number" 
                      required
                      min="0" 
                      max="120"
                      value={formData.edad}
                      onChange={(e) => setFormData({...formData, edad: e.target.value})}
                      className="w-full bg-slate-600 border border-slate-500 rounded-lg px-4 py-3 text-white text-lg font-bold focus:ring-2 focus:ring-blue-500"
                      placeholder="Edad del paciente"
                    />
                  </div>
                  
                  <div>
                    <label className="block text-slate-300 font-bold mb-2">
                      EMBARAZO
                    </label>
                    <select 
                      value={formData.embarazo}
                      onChange={(e) => setFormData({...formData, embarazo: e.target.value})}
                      className="w-full bg-slate-600 border border-slate-500 rounded-lg px-4 py-3 text-white text-lg font-bold focus:ring-2 focus:ring-blue-500"
                    >
                      <option value="No">No</option>
                      <option value="Sí">Sí</option>
                    </select>
                  </div>
                </div>
              </div>

              {/* Síntomas Principales */}
              <div className="bg-slate-700 p-4 rounded-lg">
                <h3 className="text-xl font-bold text-slate-200 mb-4">
                  SÍNTOMAS PRINCIPALES
                </h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-slate-300 font-bold mb-2">
                      MOTIVO CONSULTA
                    </label>
                    <select 
                      value={formData.motivo_consulta}
                      onChange={(e) => setFormData({...formData, motivo_consulta: e.target.value})}
                      className="w-full bg-slate-600 border border-slate-500 rounded-lg px-4 py-3 text-white text-lg font-bold focus:ring-2 focus:ring-blue-500"
                    >
                      <option value="">Seleccionar...</option>
                      <option value="Tós o síntomas respiratorios">Tos o síntomas respiratorios</option>
                      <option value="Dificultad respiratoria">Dificultad respiratoria</option>
                      <option value="Dolor torácico">Dolor torácico</option>
                      <option value="Dolor abdominal">Dolor abdominal</option>
                      <option value="Problema gastrointestinal">Problema gastrointestinal</option>
                      <option value="Problema urinario">Problema urinario</option>
                      <option value="Dolor de cabeza">Dolor de cabeza</option>
                      <option value="Mareo o desmayo">Mareo o desmayo</option>
                      <option value="Embarazo o síntoma relacionado con embarazo">Embarazo o síntoma relacionado</option>
                      <option value="Fiebre sin foco claro">Fiebre sin foco claro</option>
                    </select>
                  </div>
                  
                  <div>
                    <label className="block text-slate-300 font-bold mb-2">
                      INTENSIDAD SÍNTOMA (0-10)
                    </label>
                    <input 
                      type="number" 
                      min="0" 
                      max="10"
                      value={formData.intensidad_sintoma}
                      onChange={(e) => setFormData({...formData, intensidad_sintoma: e.target.value})}
                      className="w-full bg-slate-600 border border-slate-500 rounded-lg px-4 py-3 text-white text-lg font-bold focus:ring-2 focus:ring-blue-500"
                      placeholder="Escala de dolor 0-10"
                    />
                  </div>
                </div>
              </div>

              {/* RED FLAGS CRÍTICAS */}
              <div className="bg-red-900/30 border border-red-500 p-4 rounded-lg">
                <h3 className="text-xl font-bold text-red-400 mb-4 flex items-center space-x-2">
                  <AlertTriangle className="w-6 h-6" />
                  <span>BANDERAS ROJAS CRÍTICAS</span>
                </h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="flex items-center space-x-3 cursor-pointer">
                      <input 
                        type="checkbox" 
                        checked={formData.redflag_disnea_severa === 'Sí'}
                        onChange={(e) => setFormData({...formData, redflag_disnea_severa: e.target.checked ? 'Sí' : 'No'})}
                        className="w-5 h-5 text-red-500"
                      />
                      <span className="text-red-300 font-bold">DISNEA SEVERA</span>
                    </label>
                  </div>
                  
                  <div>
                    <label className="flex items-center space-x-3 cursor-pointer">
                      <input 
                        type="checkbox" 
                        checked={formData.redflag_sangrado_abundante === 'Sí'}
                        onChange={(e) => setFormData({...formData, redflag_sangrado_abundante: e.target.checked ? 'Sí' : 'No'})}
                        className="w-5 h-5 text-red-500"
                      />
                      <span className="text-red-300 font-bold">SANGRADO ABUNDANTE</span>
                    </label>
                  </div>
                  
                  <div>
                    <label className="flex items-center space-x-3 cursor-pointer">
                      <input 
                        type="checkbox" 
                        checked={formData.redflag_deficit_neurologico_subito === 'Sí'}
                        onChange={(e) => setFormData({...formData, redflag_deficit_neurologico_subito: e.target.checked ? 'Sí' : 'No'})}
                        className="w-5 h-5 text-red-500"
                      />
                      <span className="text-red-300 font-bold">DÉFICIT NEUROLÓGICO</span>
                    </label>
                  </div>
                  
                  <div>
                    <label className="flex items-center space-x-3 cursor-pointer">
                      <input 
                        type="checkbox" 
                        checked={formData.redflag_dolor_toracico_opresivo_con_sudoracion === 'Sí'}
                        onChange={(e) => setFormData({...formData, redflag_dolor_toracico_opresivo_con_sudoracion: e.target.checked ? 'Sí' : 'No'})}
                        className="w-5 h-5 text-red-500"
                      />
                      <span className="text-red-300 font-bold">DOLOR TORÁCICO + SUDOR</span>
                    </label>
                  </div>
                </div>
              </div>

              {/* Síntomas Específicos */}
              <div className="bg-slate-700 p-4 rounded-lg">
                <h3 className="text-xl font-bold text-slate-200 mb-4">
                  SÍNTOMAS ESPECÍFICOS
                </h3>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  {[
                    { key: 'fiebre_reportada', label: 'FIEBRE' },
                    { key: 'tos', label: 'TOS' },
                    { key: 'dificultad_respiratoria', label: 'DISNEA' },
                    { key: 'dolor_toracico', label: 'DOLOR TORÁCICO' },
                    { key: 'dolor_al_orinar', label: 'DOLOR ORINAR' },
                    { key: 'sangrado_activo', label: 'SANGRADO' },
                    { key: 'confusion', label: 'CONFUSIÓN' }
                  ].map(({ key, label }) => (
                    <div key={key}>
                      <label className="flex items-center space-x-2 cursor-pointer">
                        <input 
                          type="checkbox" 
                          checked={formData[key] === 'Sí'}
                          onChange={(e) => setFormData({...formData, [key]: e.target.checked ? 'Sí' : 'No'})}
                          className="w-4 h-4 text-blue-500"
                        />
                        <span className="text-slate-300 font-bold text-sm">{label}</span>
                      </label>
                    </div>
                  ))}
                </div>
              </div>

              {/* Descripción de Síntomas */}
              <div className="bg-blue-900/30 border border-blue-500 p-4 rounded-lg">
                <h3 className="text-xl font-bold text-blue-400 mb-4 flex items-center space-x-2">
                  <Stethoscope className="w-6 h-6" />
                  <span>DESCRIPCIÓN LIBRE DE SÍNTOMAS</span>
                </h3>
                <textarea 
                  value={formData.sintomas_texto}
                  onChange={(e) => setFormData({...formData, sintomas_texto: e.target.value})}
                  className="w-full bg-slate-600 border border-slate-500 rounded-lg px-4 py-3 text-white h-32 focus:ring-2 focus:ring-blue-500"
                  placeholder="Describa los síntomas del paciente en texto libre. Este campo alimenta el análisis del prompt de triaje médico de Mikel..."
                />
              </div>

              {/* Botones de Acción */}
              <div className="flex space-x-4 pt-6">
                <button 
                  type="button"
                  onClick={() => setShowNewPatient(false)}
                  className="flex-1 bg-slate-600 hover:bg-slate-700 text-white px-6 py-4 rounded-lg font-bold text-lg transition-all"
                >
                  CANCELAR
                </button>
                <button 
                  type="submit"
                  className="flex-1 bg-blue-600 hover:bg-blue-700 text-white px-6 py-4 rounded-lg font-bold text-lg transition-all transform hover:scale-105 shadow-lg"
                >
                  PROCESAR TRIAJE
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Patient Detail Modal */}
      {currentPatient && (
        <div className="fixed inset-0 bg-black/80 flex items-center justify-center p-4 z-50">
          <div className="bg-slate-800 rounded-xl p-6 w-full max-w-3xl border border-slate-600">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-2xl font-bold text-blue-400">
                DETALLE DEL PACIENTE: {currentPatient.id}
              </h2>
              <button 
                onClick={() => setCurrentPatient(null)}
                className="text-slate-400 hover:text-white"
              >
                <X className="w-8 h-8" />
              </button>
            </div>

            <div className="space-y-6">
              {/* Status Principal */}
              <div className={`${getPatientCardStyle(currentPatient.nivel)} p-6 rounded-xl`}>
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="text-3xl font-bold text-white mb-2">
                      {currentPatient.nivel.toUpperCase()}
                    </h3>
                    <p className="text-white text-xl font-bold">
                      {currentPatient.justificacion}
                    </p>
                    <p className="text-white/80 mt-2">
                      {currentPatient.accion}
                    </p>
                  </div>
                  {getUrgencyIcon(currentPatient.nivel)}
                </div>
              </div>

              {/* Información Clínica */}
              <div className="bg-slate-700 p-4 rounded-lg">
                <h4 className="text-lg font-bold text-slate-200 mb-4">ANÁLISIS CLÍNICO</h4>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <p className="text-slate-400 text-sm mb-1">SÍNTOMAS DETECTADOS</p>
                    <p className="text-white font-bold">{currentPatient.sintomas_detectados}</p>
                  </div>
                  <div>
                    <p className="text-slate-400 text-sm mb-1">PATRÓN DE REFERENCIA</p>
                    <p className="text-white font-bold">{currentPatient.patron_referencia}</p>
                  </div>
                </div>
              </div>

              {/* Banderas Rojas */}
              {currentPatient.banderas_rojas.length > 0 && (
                <div className="bg-red-900/30 border border-red-500 p-4 rounded-lg">
                  <h4 className="text-lg font-bold text-red-400 mb-2 flex items-center space-x-2">
                    <AlertTriangle className="w-5 h-5" />
                    <span>BANDERAS ROJAS ACTIVAS</span>
                  </h4>
                  <ul className="space-y-2">
                    {currentPatient.banderas_rojas.map((bandera, index) => (
                      <li key={index} className="text-red-300 font-bold">
                        • {bandera}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Información General */}
              <div className="bg-slate-700 p-4 rounded-lg">
                <h4 className="text-lg font-bold text-slate-200 mb-4">INFORMACIÓN GENERAL</h4>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div>
                    <p className="text-slate-400 text-sm mb-1">EDAD</p>
                    <p className="text-white font-bold text-lg">{currentPatient.edad} años</p>
                  </div>
                  <div>
                    <p className="text-slate-400 text-sm mb-1">HORA INGRESO</p>
                    <p className="text-white font-bold text-lg">{currentPatient.hora_ingreso}</p>
                  </div>
                  <div>
                    <p className="text-slate-400 text-sm mb-1">TIEMPO ESPERA</p>
                    <p className="text-white font-bold text-lg">{currentPatient.tiempo_espera} min</p>
                  </div>
                  <div>
                    <p className="text-slate-400 text-sm mb-1">PRIORIDAD</p>
                    <p className="text-white font-bold text-lg">#{patients.indexOf(currentPatient) + 1}</p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Critical Notifications */}
      <div className="fixed top-4 right-4 space-y-4 z-50">
        {notifications.map((notification) => (
          <div 
            key={notification.id}
            className="bg-red-600 border border-red-400 rounded-lg p-4 shadow-xl animate-pulse max-w-sm"
          >
            <div className="flex items-center space-x-3">
              <AlertCircle className="w-8 h-8 text-white flex-shrink-0" />
              <div>
                <h4 className="text-white font-bold text-lg">{notification.title}</h4>
                <p className="text-white/90">{notification.message}</p>
                <p className="text-red-200 font-bold mt-1">{notification.action}</p>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default SmartXDashboard;