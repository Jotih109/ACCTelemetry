"""
providers/assettocorsa.py (ACC Redirect)
========================================
Redireciona todas as importações para providers.acc (Assetto Corsa Competizione).
Garante compatibilidade total com módulos e testes existentes.
"""

from providers.acc import (
    ACCTelemetryProvider,
    AssettoCorsaTelemetryProvider,
    ACTelemetryProvider,
    SPageFilePhysics,
    SPageFileGraphic,
    SPageFileStatic,
    SharedBlock,
    SESSION_NAMES,
    FLAG_NAMES,
    TRACK_GRIP_NAMES,
    RAIN_INTENSITY_NAMES,
    ACC_CARS,
    ACC_TRACKS,
)

__all__ = [
    "ACCTelemetryProvider",
    "AssettoCorsaTelemetryProvider",
    "ACTelemetryProvider",
    "SPageFilePhysics",
    "SPageFileGraphic",
    "SPageFileStatic",
    "SharedBlock",
    "SESSION_NAMES",
    "FLAG_NAMES",
    "TRACK_GRIP_NAMES",
    "RAIN_INTENSITY_NAMES",
    "ACC_CARS",
    "ACC_TRACKS",
]
