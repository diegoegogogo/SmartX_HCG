import React from 'react';
import { Zap, Clock, Check, AlertTriangle, User } from 'lucide-react';

const LEVEL_STYLES = {
  rojo:     'bg-red-500 border-red-700 shadow-red-500/50 animate-pulse',
  amarillo: 'bg-yellow-500 border-yellow-700 shadow-yellow-500/30',
  verde:    'bg-green-500 border-green-700 shadow-green-500/20',
};

const LEVEL_ICONS = {
  rojo:     <Zap className="w-8 h-8 text-white" />,
  amarillo: <Clock className="w-8 h-8 text-white" />,
  verde:    <Check className="w-8 h-8 text-white" />,
};

/**
 * Tarjeta individual de paciente para el dashboard de triaje.
 *
 * Props:
 *   patient  — objeto paciente { id, edad, hora_ingreso, nivel, justificacion,
 *               accion, tiempo_espera, banderas_rojas, modo }
 *   onClick  — callback cuando se hace clic para ver detalle
 */
const PatientCard = ({ patient, onClick }) => {
  const { id, edad, hora_ingreso, nivel, justificacion, accion,
          tiempo_espera, banderas_rojas = [], modo } = patient;

  const cardClass = LEVEL_STYLES[nivel] || 'bg-gray-500 border-gray-700';

  return (
    <div
      className={`${cardClass} p-6 rounded-xl border-2 shadow-xl cursor-pointer
                  transform transition-all hover:scale-105`}
      onClick={onClick}
    >
      {/* ID + hora + edad */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-2xl font-bold text-white">
            {id}
            {modo === 'simulacion' && (
              <span className="ml-2 text-xs bg-orange-600 text-white px-1 rounded">
                sin conexión
              </span>
            )}
          </h3>
          <p className="text-white/80 text-sm">
            {hora_ingreso} | {edad} años
          </p>
        </div>
        <div className="flex flex-col items-center">
          {LEVEL_ICONS[nivel] || <User className="w-8 h-8 text-white" />}
          <span className="text-xs font-bold text-white mt-1">
            {nivel?.toUpperCase()}
          </span>
        </div>
      </div>

      {/* Justificación (diagnóstico breve) */}
      <div className="mb-4">
        <h4 className="text-white font-bold text-xl text-center bg-black/20 rounded-lg p-3">
          {justificacion}
        </h4>
      </div>

      {/* Acción directiva */}
      <div className="mb-4">
        <div className="bg-white/20 rounded-lg p-4 border-2 border-white/30">
          <p className="text-white font-bold text-center text-lg tracking-wide">
            {accion}
          </p>
        </div>
      </div>

      {/* Banderas rojas */}
      {banderas_rojas.length > 0 && (
        <div className="mb-4 bg-red-800/50 border border-red-400 rounded-lg p-2">
          <div className="flex items-center space-x-2">
            <AlertTriangle className="w-4 h-4 text-red-200" />
            <span className="text-red-200 font-bold text-sm">BANDERAS ROJAS</span>
          </div>
        </div>
      )}

      {/* Tiempo de espera */}
      <div className="flex items-center justify-between text-white/80 text-sm">
        <span>
          <Clock className="w-3 h-3 inline mr-1" />
          Espera: {tiempo_espera} min
        </span>
      </div>
    </div>
  );
};

export default PatientCard;
