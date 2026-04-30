"""
Punto de entrada del motor de inferencia dentro de la estructura backend/.
Re-exporta desde el módulo principal en 04_Codigo/.
"""
import sys
from pathlib import Path

# Añadir raíz de 04_Codigo al path para encontrar el motor original
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from smartx_motor_inferencia import (   # noqa: E402
    MotorInferenciaSmartX,
    Paciente,
    NivelSemaforo,
)

__all__ = ["MotorInferenciaSmartX", "Paciente", "NivelSemaforo"]
