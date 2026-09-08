"""
providers/acc.py
================
Provider de telemetria para o Assetto Corsa Competizione (ACC).

Diferente do AC1, o Assetto Corsa Competizione publica estruturas expandidas
na memória compartilhada do Windows (Shared Memory):
    Local\\acpmf_physics   — atualizado a ~333 Hz (SPageFilePhysics, 800 bytes)
    Local\\acpmf_graphics  — atualizado a ~60 Hz  (SPageFileGraphic, 1588 bytes)
    Local\\acpmf_static    — escrito ao entrar na sessão (SPageFileStatic, 820 bytes)

Principais diferenças em relação ao AC1:
    - SPageFileGraphic contém coordenadas de até 60 carros em pista e playerCarID
    - Canais de eletrônica detalhados (TC level, TC Cut level, ABS level, Engine Map)
    - Clima dinâmico (chuva atual, previsão para 10 min e 30 min, estágio de pista/grip)
    - Vida útil de pastilhas e discos de freio (padLife, discLife)
    - Temperatura de água do motor (waterTemp) e escapamento (exhaustTemperature)
    - Angulo de esterçamento publicado em radianos
    - Validação de volta (isValidLap) e tempos de stint do piloto
"""

import ctypes
import ctypes.wintypes as wintypes
import math
import time
from typing import Optional

from core.models import TelemetryState
from providers.base import TelemetryProvider


# ---------------------------------------------------------------------------
# Constantes de configuração
# ---------------------------------------------------------------------------

MMAP_PHYSICS  = "acpmf_physics"
MMAP_GRAPHICS = "acpmf_graphics"
MMAP_STATIC   = "acpmf_static"

STALE_TIMEOUT = 2.0
REMAP_TIMEOUT = 5.0

# ACC_STATUS
AC_OFF    = 0
AC_REPLAY = 1
AC_LIVE   = 2
AC_PAUSE  = 3

# ACC_SESSION_TYPE
SESSION_NAMES = {
    -1: "Desconhecida",
    0: "Practice",
    1: "Qualify",
    2: "Race",
    3: "Hotlap",
    4: "Time Attack",
    5: "Drift",
    6: "Drag",
    7: "Hotstint",
    8: "Superpole",
}

# ACC_FLAG_TYPE
FLAG_NAMES = {
    0: "",
    1: "AZUL",
    2: "AMARELA",
    3: "PRETA",
    4: "BRANCA",
    5: "XADREZ",
    6: "PENALIDADE",
    7: "VERDE",
    8: "LARANJA",
}

# ACC_TRACK_GRIP_STATUS
TRACK_GRIP_NAMES = {
    0: "Green",
    1: "Fast",
    2: "Optimum",
    3: "Greasy",
    4: "Damp",
    5: "Wet",
    6: "Flooded",
}

# ACC_RAIN_INTENSITY
RAIN_INTENSITY_NAMES = {
    0: "No Rain",
    1: "Drizzle",
    2: "Light Rain",
    3: "Medium Rain",
    4: "Heavy Rain",
    5: "Thunderstorm",
}


# ---------------------------------------------------------------------------
# Dicionários de Nomes Oficiais (ACC Content)
# ---------------------------------------------------------------------------

ACC_CARS = {
    # GT3
    "amr_v8_vantage_gt3": "Aston Martin Vantage V8 GT3",
    "amr_v12_vantage_gt3": "Aston Martin Vantage V12 GT3",
    "audi_r8_lms": "Audi R8 LMS GT3",
    "audi_r8_lms_evo": "Audi R8 LMS Evo GT3",
    "audi_r8_lms_evo_ii": "Audi R8 LMS Evo II GT3",
    "bentley_continental_gt3_2016": "Bentley Continental GT3 (2016)",
    "bentley_continental_gt3_2018": "Bentley Continental GT3 (2018)",
    "bmw_m6_gt3": "BMW M6 GT3",
    "bmw_m4_gt3": "BMW M4 GT3",
    "ferrari_488_gt3": "Ferrari 488 GT3",
    "ferrari_488_gt3_evo": "Ferrari 488 GT3 Evo",
    "ferrari_296_gt3": "Ferrari 296 GT3",
    "emil_frey_jaguar_g3": "Emil Frey Jaguar G3",
    "honda_nsx_gt3": "Honda NSX GT3",
    "honda_nsx_gt3_evo": "Honda NSX GT3 Evo",
    "lamborghini_huracan_gt3": "Lamborghini Huracán GT3",
    "lamborghini_huracan_gt3_evo": "Lamborghini Huracán GT3 Evo",
    "lamborghini_huracan_gt3_evo_2": "Lamborghini Huracán GT3 Evo 2",
    "lexus_rc_f_gt3": "Lexus RC F GT3",
    "mclaren_650s_gt3": "McLaren 650S GT3",
    "mclaren_720s_gt3": "McLaren 720S GT3",
    "mclaren_720s_gt3_evo": "McLaren 720S GT3 Evo",
    "mercedes_amg_gt3": "Mercedes-AMG GT3",
    "mercedes_amg_gt3_evo": "Mercedes-AMG GT3 Evo",
    "nissan_gt_r_gt3_2017": "Nissan GT-R Nismo GT3 (2017)",
    "nissan_gt_r_gt3_2018": "Nissan GT-R Nismo GT3 (2018)",
    "porsche_991_gt3_r": "Porsche 911 GT3 R (991)",
    "porsche_991ii_gt3_r": "Porsche 911 GT3 R (991 II)",
    "porsche_992_gt3_r": "Porsche 911 GT3 R (992)",
    # One-Make & Cup
    "porsche_991_cup": "Porsche 911 GT3 Cup (991 II)",
    "porsche_992_cup": "Porsche 911 GT3 Cup (992)",
    "lamborghini_huracan_st": "Lamborghini Huracán Super Trofeo",
    "lamborghini_huracan_st_evo2": "Lamborghini Huracán ST Evo 2",
    "ferrari_488_challenge_evo": "Ferrari 488 Challenge Evo",
    "bmw_m2_cs_racing": "BMW M2 CS Racing",
    # GT4
    "alpine_a110_gt4": "Alpine A110 GT4",
    "aston_martin_v8_vantage_gt4": "Aston Martin Vantage GT4",
    "audi_r8_gt4": "Audi R8 LMS GT4",
    "bmw_m4_gt4": "BMW M4 GT4",
    "chevrolet_camaro_gt4r": "Chevrolet Camaro GT4.R",
    "ginetta_g55_gt4": "Ginetta G55 GT4",
    "ktm_xbow_gt4": "KTM X-Bow GT4",
    "maserati_mc_gt4": "Maserati GranTurismo MC GT4",
    "mclaren_570s_gt4": "McLaren 570S GT4",
    "mercedes_amg_gt4": "Mercedes-AMG GT4",
    "porsche_718_cayman_gt4_mr": "Porsche 718 Cayman GT4 Clubsport MR",
}

ACC_TRACKS = {
    "barcelona": "Circuit de Barcelona-Catalunya",
    "brands_hatch": "Brands Hatch",
    "cota": "Circuit of the Americas",
    "donington": "Donington Park",
    "hungaroring": "Hungaroring",
    "imola": "Imola (Enzo e Dino Ferrari)",
    "indianapolis": "Indianapolis Motor Speedway",
    "kyalami": "Kyalami Grand Prix Circuit",
    "laguna_seca": "Laguna Seca",
    "misano": "Misano World Circuit",
    "monza": "Autodromo Nazionale Monza",
    "mount_panorama": "Mount Panorama (Bathurst)",
    "nurburgring": "Nürburgring GP",
    "nurburgring_24h": "Nürburgring 24h",
    "oulton_park": "Oulton Park",
    "paul_ricard": "Circuit Paul Ricard",
    "red_bull_ring": "Red Bull Ring",
    "silverstone": "Silverstone Circuit",
    "snetterton": "Snetterton Circuit",
    "spa": "Circuit de Spa-Francorchamps",
    "suzuka": "Suzuka Circuit",
    "valencia": "Circuit Ricardo Tormo (Valencia)",
    "watkins_glen": "Watkins Glen",
    "zandvoort": "Circuit Zandvoort",
    "zolder": "Circuit Zolder",
}


# ---------------------------------------------------------------------------
# Structs da memória compartilhada (Layout Oficial ACC)
# ---------------------------------------------------------------------------

class SPageFilePhysics(ctypes.Structure):
    """
    Bloco acpmf_physics do ACC — 800 bytes.
    Atualizado a alta frequência (~333 Hz).
    """
    _pack_ = 4
    _fields_ = [
        ("packetId",             ctypes.c_int32),
        ("gas",                  ctypes.c_float),       # 0..1
        ("brake",                ctypes.c_float),       # 0..1
        ("fuel",                 ctypes.c_float),       # litros
        ("gear",                 ctypes.c_int32),       # 0=Ré, 1=N, 2=1ª ...
        ("rpms",                 ctypes.c_int32),
        ("steerAngle",           ctypes.c_float),       # radianos
        ("speedKmh",             ctypes.c_float),
        ("velocity",             ctypes.c_float * 3),
        ("accG",                 ctypes.c_float * 3),   # [lat, vert, lon] em G
        ("wheelSlip",            ctypes.c_float * 4),
        ("wheelLoad",            ctypes.c_float * 4),
        ("wheelsPressure",       ctypes.c_float * 4),   # PSI
        ("wheelAngularSpeed",    ctypes.c_float * 4),   # rad/s
        ("tyreWear",             ctypes.c_float * 4),
        ("tyreDirtyLevel",       ctypes.c_float * 4),
        ("tyreCoreTemperature",  ctypes.c_float * 4),   # °C
        ("camberRAD",            ctypes.c_float * 4),
        ("suspensionTravel",     ctypes.c_float * 4),   # metros
        ("drs",                  ctypes.c_float),
        ("tc",                   ctypes.c_float),       # intervenção 0..1
        ("heading",              ctypes.c_float),
        ("pitch",                ctypes.c_float),
        ("roll",                 ctypes.c_float),
        ("cgHeight",             ctypes.c_float),
        ("carDamage",            ctypes.c_float * 5),   # F, R, L, Ri, total
        ("numberOfTyresOut",     ctypes.c_int32),
        ("pitLimiterOn",         ctypes.c_int32),
        ("abs",                  ctypes.c_float),       # intervenção 0..1
        ("kersCharge",           ctypes.c_float),
        ("kersInput",            ctypes.c_float),
        ("autoShifterOn",        ctypes.c_int32),
        ("rideHeight",           ctypes.c_float * 2),
        ("turboBoost",           ctypes.c_float),
        ("ballast",              ctypes.c_float),
        ("airDensity",           ctypes.c_float),
        ("airTemp",              ctypes.c_float),       # °C
        ("roadTemp",             ctypes.c_float),       # °C
        ("localAngularVel",      ctypes.c_float * 3),
        ("finalFF",              ctypes.c_float),       # 0..1
        ("performanceMeter",     ctypes.c_float),
        ("engineBrake",          ctypes.c_int32),
        ("ersRecoveryLevel",     ctypes.c_int32),
        ("ersPowerLevel",        ctypes.c_int32),
        ("ersHeatCharging",      ctypes.c_int32),
        ("ersIsCharging",        ctypes.c_int32),
        ("kersCurrentKJ",        ctypes.c_float),
        ("drsAvailable",         ctypes.c_int32),
        ("drsEnabled",           ctypes.c_int32),
        ("brakeTemp",            ctypes.c_float * 4),   # °C
        ("clutch",               ctypes.c_float),
        ("tyreTempI",            ctypes.c_float * 4),
        ("tyreTempM",            ctypes.c_float * 4),
        ("tyreTempO",            ctypes.c_float * 4),
        ("isAIControlled",       ctypes.c_int32),
        ("tyreContactPoint",     (ctypes.c_float * 3) * 4),
        ("tyreContactNormal",    (ctypes.c_float * 3) * 4),
        ("tyreContactHeading",   (ctypes.c_float * 3) * 4),
        ("brakeBias",            ctypes.c_float),       # 0..1
        ("localVelocity",        ctypes.c_float * 3),
        # Campos estendidos específicos do ACC:
        ("P2PActivations",       ctypes.c_int32),
        ("P2PStatus",            ctypes.c_int32),
        ("currentMaxRpm",        ctypes.c_int32),
        ("mz",                   ctypes.c_float * 4),
        ("fx",                   ctypes.c_float * 4),
        ("fy",                   ctypes.c_float * 4),
        ("slipRatio",            ctypes.c_float * 4),
        ("slipAngle",            ctypes.c_float * 4),
        ("tcinAction",           ctypes.c_int32),       # TC ativo (1 ou 0)
        ("absInAction",          ctypes.c_int32),       # ABS ativo (1 ou 0)
        ("suspensionDamage",     ctypes.c_float * 4),
        ("tyreTemp",             ctypes.c_float * 4),
        ("waterTemp",            ctypes.c_float),       # °C água do motor
        ("brakePressure",        ctypes.c_float * 4),   # bar
        ("frontBrakeCompound",   ctypes.c_int32),
        ("rearBrakeCompound",    ctypes.c_int32),
        ("padLife",              ctypes.c_float * 4),   # pastilhas de freio
        ("discLife",             ctypes.c_float * 4),   # discos de freio
        ("ignitionOn",           ctypes.c_int32),
        ("starterEngineOn",      ctypes.c_int32),
        ("isEngineRunning",      ctypes.c_int32),
        ("kerbVibration",        ctypes.c_float),
        ("slipVibrations",       ctypes.c_float),
        ("gVibrations",          ctypes.c_float),
        ("absVibrations",        ctypes.c_float),
    ]


class SPageFileGraphic(ctypes.Structure):
    """
    Bloco acpmf_graphics do ACC — 1588 bytes.
    Atualizado a ~60 Hz (sessão, tempos, eletrônica e clima).
    """
    _pack_ = 4
    _fields_ = [
        ("packetId",                 ctypes.c_int32),
        ("status",                   ctypes.c_int32),   # ACC_STATUS
        ("session",                  ctypes.c_int32),   # ACC_SESSION_TYPE
        ("currentTime",              ctypes.c_wchar * 15),
        ("lastTime",                 ctypes.c_wchar * 15),
        ("bestTime",                 ctypes.c_wchar * 15),
        ("split",                    ctypes.c_wchar * 15),
        ("completedLaps",            ctypes.c_int32),
        ("position",                 ctypes.c_int32),
        ("iCurrentTime",             ctypes.c_int32),   # ms
        ("iLastTime",                ctypes.c_int32),   # ms
        ("iBestTime",                ctypes.c_int32),   # ms
        ("sessionTimeLeft",          ctypes.c_float),   # ms
        ("distanceTraveled",         ctypes.c_float),   # metros na sessão
        ("isInPit",                  ctypes.c_int32),
        ("currentSectorIndex",       ctypes.c_int32),
        ("lastSectorTime",           ctypes.c_int32),   # ms
        ("numberOfLaps",             ctypes.c_int32),
        ("tyreCompound",             ctypes.c_wchar * 33),
        ("replayTimeMultiplier",     ctypes.c_float),
        ("normalizedCarPosition",    ctypes.c_float),   # 0..1
        # Array multi-carro do ACC (até 60 carros em pista):
        ("activeCars",               ctypes.c_int32),
        ("carCoordinates",           (ctypes.c_float * 3) * 60),
        ("carID",                    ctypes.c_int32 * 60),
        ("playerCarID",              ctypes.c_int32),   # índice do jogador em carCoordinates
        ("penaltyTime",              ctypes.c_float),
        ("flag",                     ctypes.c_int32),   # ACC_FLAG_TYPE
        ("penalty",                  ctypes.c_int32),
        ("idealLineOn",              ctypes.c_int32),
        ("isInPitLane",              ctypes.c_int32),
        ("surfaceGrip",              ctypes.c_float),
        ("mandatoryPitDone",         ctypes.c_int32),
        ("windSpeed",                ctypes.c_float),
        ("windDirection",            ctypes.c_float),
        # Controles eletrônicos e cabine ACC:
        ("isSetupMenuVisible",       ctypes.c_int32),
        ("mainDisplayIndex",         ctypes.c_int32),
        ("secondaryDisplayIndex",    ctypes.c_int32),
        ("TC",                       ctypes.c_int32),   # Seletor de TC (ex: 1..11)
        ("TCCut",                    ctypes.c_int32),   # Seletor de TC Cut (ex: 1..11)
        ("EngineMap",                ctypes.c_int32),   # Mapa de motor (1..N)
        ("ABS",                      ctypes.c_int32),   # Seletor de ABS (ex: 1..11)
        ("fuelXLap",                 ctypes.c_float),   # Consumo estimado por volta
        ("rainLights",               ctypes.c_int32),
        ("flashingLights",           ctypes.c_int32),
        ("lightsStage",              ctypes.c_int32),
        ("exhaustTemperature",       ctypes.c_float),
        ("wiperLV",                  ctypes.c_int32),
        ("DriverStintTotalTimeLeft", ctypes.c_int32),   # ms
        ("DriverStintTimeLeft",      ctypes.c_int32),   # ms
        ("rainTyres",                ctypes.c_int32),
        ("sessionIndex",             ctypes.c_int32),
        ("usedFuel",                 ctypes.c_float),
        ("deltaLapTime",             ctypes.c_wchar * 15),
        ("iDeltaLapTime",            ctypes.c_int32),   # ms
        ("estimatedLapTime",         ctypes.c_wchar * 15),
        ("iEstimatedLapTime",        ctypes.c_int32),   # ms
        ("isDeltaPositive",          ctypes.c_int32),
        ("iSplit",                   ctypes.c_int32),
        ("isValidLap",               ctypes.c_int32),   # 1 = volta válida, 0 = anulada
        ("fuelEstimatedLaps",        ctypes.c_float),
        ("trackStatus",              ctypes.c_wchar * 33),
        ("missingMandatoryPits",     ctypes.c_int32),
        ("Clock",                    ctypes.c_float),   # segundos do relógio do jogo
        ("directionLightsLeft",      ctypes.c_int32),
        ("directionLightsRight",     ctypes.c_int32),
        ("GlobalYellow",             ctypes.c_int32),
        ("GlobalYellow1",            ctypes.c_int32),
        ("GlobalYellow2",            ctypes.c_int32),
        ("GlobalYellow3",            ctypes.c_int32),
        ("GlobalWhite",              ctypes.c_int32),
        ("GlobalGreen",              ctypes.c_int32),
        ("GlobalChequered",          ctypes.c_int32),
        ("GlobalRed",                ctypes.c_int32),
        ("mfdTyreSet",               ctypes.c_int32),
        ("mfdFuelToAdd",             ctypes.c_float),
        ("mfdTyrePressure",          ctypes.c_float * 4),
        ("trackGripStatus",          ctypes.c_int32),   # ACC_TRACK_GRIP_STATUS
        ("rainIntensity",            ctypes.c_int32),   # ACC_RAIN_INTENSITY atual
        ("rainIntensityIn10min",     ctypes.c_int32),   # ACC_RAIN_INTENSITY em 10m
        ("rainIntensityIn30min",     ctypes.c_int32),   # ACC_RAIN_INTENSITY em 30m
        ("currentTyreSet",           ctypes.c_int32),
        ("strategyTyreSet",          ctypes.c_int32),
        ("gapAhead",                 ctypes.c_int32),   # ms
        ("gapBehind",                ctypes.c_int32),   # ms
    ]


class SPageFileStatic(ctypes.Structure):
    """
    Bloco acpmf_static do ACC — 820 bytes.
    Escrito uma vez ao entrar na sessão.
    """
    _pack_ = 4
    _fields_ = [
        ("smVersion",                ctypes.c_wchar * 15),
        ("acVersion",                ctypes.c_wchar * 15),
        ("numberOfSessions",         ctypes.c_int32),
        ("numCars",                  ctypes.c_int32),
        ("carModel",                 ctypes.c_wchar * 33),
        ("track",                    ctypes.c_wchar * 33),
        ("playerName",               ctypes.c_wchar * 33),
        ("playerSurname",            ctypes.c_wchar * 33),
        ("playerNick",               ctypes.c_wchar * 33),
        ("sectorCount",              ctypes.c_int32),
        ("maxTorque",                ctypes.c_float),
        ("maxPower",                 ctypes.c_float),
        ("maxRpm",                   ctypes.c_int32),
        ("maxFuel",                  ctypes.c_float),
        ("suspensionMaxTravel",      ctypes.c_float * 4),
        ("tyreRadius",               ctypes.c_float * 4),
        ("maxTurboBoost",            ctypes.c_float),
        ("deprecated_1",             ctypes.c_float),
        ("deprecated_2",             ctypes.c_float),
        ("penaltiesEnabled",         ctypes.c_int32),
        ("aidFuelRate",              ctypes.c_float),
        ("aidTireRate",              ctypes.c_float),
        ("aidMechanicalDamage",      ctypes.c_float),
        ("aidAllowTyreBlankets",     ctypes.c_int32),
        ("aidStability",             ctypes.c_float),
        ("aidAutoClutch",            ctypes.c_int32),
        ("aidAutoBlip",              ctypes.c_int32),
        ("hasDRS",                   ctypes.c_int32),
        ("hasERS",                   ctypes.c_int32),
        ("hasKERS",                  ctypes.c_int32),
        ("kersMaxJ",                 ctypes.c_float),
        ("engineBrakeSettingsCount", ctypes.c_int32),
        ("ersPowerControllerCount",  ctypes.c_int32),
        ("trackSPlineLength",        ctypes.c_float),
        ("trackConfiguration",       ctypes.c_wchar * 33),
        ("ersMaxJ",                  ctypes.c_float),
        ("isTimedRace",              ctypes.c_int32),
        ("hasExtraLap",              ctypes.c_int32),
        ("carSkin",                  ctypes.c_wchar * 33),
        ("reversedGridPositions",    ctypes.c_int32),
        ("PitWindowStart",           ctypes.c_int32),
        ("PitWindowEnd",             ctypes.c_int32),
        ("isOnline",                 ctypes.c_int32),
        ("dryTyresName",             ctypes.c_wchar * 33),
        ("wetTyresName",             ctypes.c_wchar * 33),
    ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ms_to_laptime_str(ms: int) -> str:
    """Converte milissegundos para 'm:ss.mmm'. Retorna '--:--.---' se inválido."""
    if ms <= 0 or ms >= 3_600_000:
        return "--:--.---"
    minutes = ms // 60000
    seconds = (ms % 60000) // 1000
    millis  = ms % 1000
    return f"{minutes}:{seconds:02d}.{millis:03d}"


def _clean_acc_car_name(raw: str) -> str:
    """Normaliza o nome do carro GT3/GT4 do ACC."""
    if not raw:
        return "Unknown Car"
    key = raw.replace("\x00", "").strip().lower()
    if key in ACC_CARS:
        return ACC_CARS[key]
    # Fallback: remove prefixos e formata
    clean = key.replace("_", " ").title()
    for acr in ("Gt3", "Gt4", "Gtr", "Lms", "Evo", "Amg", "Bmw", "Ktm"):
        clean = clean.replace(acr, acr.upper())
    return clean or "Unknown Car"


def _clean_acc_track_name(raw: str) -> str:
    """Normaliza o nome da pista oficial do ACC."""
    if not raw:
        return "Unknown Track"
    key = raw.replace("\x00", "").strip().lower()
    if key in ACC_TRACKS:
        return ACC_TRACKS[key]
    return key.replace("_", " ").title() or "Unknown Track"


# ---------------------------------------------------------------------------
# Acesso à memória compartilhada via API do Windows
# ---------------------------------------------------------------------------

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

FILE_MAP_READ = 0x0004

_kernel32.OpenFileMappingW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
_kernel32.OpenFileMappingW.restype = wintypes.HANDLE

_kernel32.MapViewOfFile.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                    wintypes.DWORD, wintypes.DWORD, ctypes.c_size_t]
_kernel32.MapViewOfFile.restype = wintypes.LPVOID

_kernel32.UnmapViewOfFile.argtypes = [wintypes.LPCVOID]
_kernel32.UnmapViewOfFile.restype = wintypes.BOOL

_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
_kernel32.CloseHandle.restype = wintypes.BOOL


class SharedBlock:
    """Um bloco de memória compartilhada do Windows aberto em leitura."""

    def __init__(self, handle, address):
        self._handle = handle
        self._address = address

    @classmethod
    def open(cls, tag: str) -> Optional["SharedBlock"]:
        """Abre o bloco pelo nome. Retorna None se não existir (jogo fechado)."""
        for name in (f"Local\\{tag}", tag):
            handle = _kernel32.OpenFileMappingW(FILE_MAP_READ, False, name)
            if not handle:
                continue
            address = _kernel32.MapViewOfFile(handle, FILE_MAP_READ, 0, 0, 0)
            if not address:
                _kernel32.CloseHandle(handle)
                continue
            return cls(handle, address)
        return None

    def read(self, struct_cls):
        """Copia o bloco de memória para uma nova instância da classe de struct."""
        dest = struct_cls()
        ctypes.memmove(ctypes.byref(dest), self._address, ctypes.sizeof(struct_cls))
        return dest

    def close(self):
        if self._address:
            _kernel32.UnmapViewOfFile(self._address)
            self._address = None
        if self._handle:
            _kernel32.CloseHandle(self._handle)
            self._handle = None


# ---------------------------------------------------------------------------
# Provider Principal do ACC
# ---------------------------------------------------------------------------

class ACCTelemetryProvider(TelemetryProvider):
    """
    Provider de telemetria nativo para Assetto Corsa Competizione (ACC).

    Conecta automaticamente via memória compartilhada do Windows (acpmf_physics,
    acpmf_graphics, acpmf_static) e preenche o TelemetryState completo.
    """

    def __init__(self):
        self._mm_physics: Optional[SharedBlock] = None
        self._mm_graphics: Optional[SharedBlock] = None
        self._mm_static: Optional[SharedBlock] = None

        self._last_packet_id = -1
        self._last_packet_change = 0.0
        self._is_connected = False

        self._static: Optional[SPageFileStatic] = None
        self._static_signature = ""

    def connect(self) -> bool:
        """Abre os três blocos de memória compartilhada do ACC."""
        if self._mm_physics is not None and self._mm_graphics is not None:
            return True

        self._mm_physics  = SharedBlock.open(MMAP_PHYSICS)
        self._mm_graphics = SharedBlock.open(MMAP_GRAPHICS)
        self._mm_static   = SharedBlock.open(MMAP_STATIC)

        if self._mm_physics is None or self._mm_graphics is None:
            self._release()
            return False

        print("[ACC] Memória compartilhada do Assetto Corsa Competizione conectada.")
        return True

    def get_state(self) -> TelemetryState:
        """Lê a telemetria do ACC e retorna um TelemetryState completo."""
        state = TelemetryState(is_connected=False)

        if self._mm_physics is None or self._mm_graphics is None:
            return state

        try:
            physics  = self._mm_physics.read(SPageFilePhysics)
            graphics = self._mm_graphics.read(SPageFileGraphic)
        except Exception:
            self._release()
            return state

        # Detecção de conexão e atualização
        now = time.monotonic()
        if physics.packetId != self._last_packet_id:
            self._last_packet_id = physics.packetId
            self._last_packet_change = now

        fresh = (now - self._last_packet_change) < STALE_TIMEOUT
        in_session = graphics.status in (AC_LIVE, AC_PAUSE, AC_REPLAY)
        self._is_connected = bool(fresh and in_session and physics.packetId > 0)

        if not self._is_connected:
            if (now - self._last_packet_change) > REMAP_TIMEOUT:
                self._release()
            return state

        state.is_connected = True

        static = self._read_static()
        self._fill_static(state, static)
        self._fill_physics(state, physics, static)
        self._fill_graphics(state, graphics)

        return state

    def close(self):
        """Libera mapeamentos de memória."""
        self._release()
        print("[ACC] Memória compartilhada liberada.")

    # -----------------------------------------------------------------------
    # Métodos Internos
    # -----------------------------------------------------------------------

    def _read_static(self) -> Optional[SPageFileStatic]:
        if self._mm_static is None:
            return self._static

        try:
            static = self._mm_static.read(SPageFileStatic)
        except Exception:
            return self._static

        signature = f"{static.carModel}|{static.track}|{static.trackConfiguration}"
        if signature != self._static_signature:
            self._static_signature = signature
            self._static = static
            print(f"[ACC] Sessão: {static.track} / {static.carModel} (SM v{static.smVersion}, ACC v{static.acVersion})")
        return self._static

    def _release(self):
        for attr in ("_mm_physics", "_mm_graphics", "_mm_static"):
            mm = getattr(self, attr, None)
            if mm is not None:
                try:
                    mm.close()
                except Exception:
                    pass
            setattr(self, attr, None)

        self._is_connected = False
        self._last_packet_id = -1
        self._last_packet_change = 0.0

    def _fill_static(self, state: TelemetryState, static: Optional[SPageFileStatic]):
        if static is None:
            return

        state.car_name = _clean_acc_car_name(static.carModel)
        state.track_name = _clean_acc_track_name(static.track)

        if static.maxRpm > 0:
            state.max_rpm = float(static.maxRpm)
        if static.maxFuel > 0:
            state.fuel_capacity = float(static.maxFuel)
        if static.trackSPlineLength > 100:
            state.track_length = float(static.trackSPlineLength)
        if static.sectorCount > 0:
            state.sector_count = int(static.sectorCount)

        state.player_name = f"{static.playerName} {static.playerSurname}".strip()
        state.has_drs  = bool(static.hasDRS)
        state.has_ers  = bool(static.hasERS)
        state.has_kers = bool(static.hasKERS)
        state.has_abs  = True
        state.has_tc   = True

    def _fill_physics(self, state: TelemetryState, p: SPageFilePhysics,
                      static: Optional[SPageFileStatic]):
        # Entradas do piloto
        state.gas   = max(0.0, min(1.0, float(p.gas)))
        state.brake = max(0.0, min(1.0, float(p.brake)))
        # No ACC/AC clutch=1.0 significa embreagem solta. Invertemos: 0=solta, 1=pisada.
        state.clutch = max(0.0, min(1.0, 1.0 - float(p.clutch)))

        # No ACC steerAngle vem em radianos. Convertemos para graus:
        deg = math.degrees(float(p.steerAngle))
        state.steer_angle = deg
        # Normalizado estimado (-1.0 a 1.0) assumindo lock típico de GT3 (~480° total, 240° de cada lado)
        state.steer_norm = max(-1.0, min(1.0, deg / 240.0))

        # Motor e Câmbio
        state.speed_kmh = max(0.0, float(p.speedKmh))
        state.rpm = int(max(0, p.rpms))
        if state.max_rpm <= 0:
            state.max_rpm = float(p.currentMaxRpm if p.currentMaxRpm > 0 else max(state.rpm + 1000, 8500))
        state.gear = int(p.gear)
        state.turbo_boost = max(0.0, float(p.turboBoost))
        if static is not None and static.maxTurboBoost > 0:
            state.turbo_boost_max = float(static.maxTurboBoost)

        state.fuel = max(0.0, float(p.fuel))

        # Eletrônica
        state.abs_active = (p.abs > 0.02) or (p.absInAction > 0)
        state.tc_active  = (p.tc > 0.02) or (p.tcinAction > 0)
        state.abs_intervention = max(0.0, min(1.0, float(p.abs)))
        state.tc_intervention  = max(0.0, min(1.0, float(p.tc)))
        state.pit_limiter = bool(p.pitLimiterOn)
        state.drs_available = bool(p.drsAvailable)
        state.drs_active    = bool(p.drsEnabled) or p.drs > 0.5
        state.kers_charge   = max(0.0, min(1.0, float(p.kersCharge)))
        state.ers_recovery_level = int(p.ersRecoveryLevel)
        state.engine_brake = int(p.engineBrake)
        state.brake_bias = max(0.0, min(1.0, float(p.brakeBias)))
        state.auto_shifter = bool(p.autoShifterOn)

        # Força G e FFB
        state.g_lat  = float(p.accG[0])
        state.g_vert = float(p.accG[1])
        state.g_lon  = float(p.accG[2])
        state.ffb_level = max(0.0, min(1.0, abs(float(p.finalFF))))

        # Pneus [FL, FR, RL, RR]
        state.tyre_temp     = [float(v) for v in p.tyreCoreTemperature]
        state.tyre_pressure = [float(v) for v in p.wheelsPressure]
        state.tyre_wear     = [max(0.0, min(100.0, float(v))) for v in p.tyreWear]
        state.tyre_slip     = [float(v) for v in p.wheelSlip]
        state.tyre_dirt     = [float(v) for v in p.tyreDirtyLevel]
        state.suspension_travel = [float(v) * 1000.0 for v in p.suspensionTravel]

        state.tyre_temp_inner  = [float(v) for v in p.tyreTempI]
        state.tyre_temp_middle = [float(v) for v in p.tyreTempM]
        state.tyre_temp_outer  = [float(v) for v in p.tyreTempO]

        # Freios e Danos
        state.brake_temp = [float(v) for v in p.brakeTemp]
        state.brake_pressure = [float(v) for v in p.brakePressure]
        state.pad_life = [float(v) for v in p.padLife]
        state.disc_life = [float(v) for v in p.discLife]

        state.ambient_temp = float(p.airTemp)
        state.track_temp   = float(p.roadTemp)
        state.water_temp   = float(p.waterTemp)

        damage = [max(0.0, float(v)) for v in p.carDamage]
        state.car_damage_parts = damage[:4]
        state.car_damage = min(100.0, max(damage))
        state.tyres_out = int(p.numberOfTyresOut)

    def _fill_graphics(self, state: TelemetryState, g: SPageFileGraphic):
        state.current_time = _ms_to_laptime_str(g.iCurrentTime)
        state.last_time    = _ms_to_laptime_str(g.iLastTime)
        state.best_time    = _ms_to_laptime_str(g.iBestTime)

        state.sector_index = max(0, min(2, int(g.currentSectorIndex)))
        state.last_sector_time = max(0, int(g.lastSectorTime))

        state.lap_number = int(g.completedLaps) + 1
        state.completed_laps = int(g.completedLaps)
        state.race_position = int(g.position)

        norm = float(g.normalizedCarPosition)
        if 0.0 <= norm <= 1.0:
            state.track_position = norm
            state.distance_traveled = norm * state.track_length

        state.session_type = SESSION_NAMES.get(int(g.session), "Desconhecida")
        state.session_time_left = max(0.0, float(g.sessionTimeLeft) / 1000.0)
        state.total_laps = int(g.numberOfLaps)
        state.is_paused = (g.status == AC_PAUSE)
        state.is_replay = (g.status == AC_REPLAY)

        state.in_pit = bool(g.isInPit)
        state.in_pit_lane = bool(g.isInPitLane)
        state.mandatory_pit_done = bool(g.mandatoryPitDone)
        state.penalty_time = max(0.0, float(g.penaltyTime))
        state.flag = FLAG_NAMES.get(int(g.flag), "")

        state.tyre_compound = (g.tyreCompound or "").replace("\x00", "").strip()
        grip = float(g.surfaceGrip)
        state.surface_grip = grip if 0.0 < grip <= 1.0 else 1.0

        state.wind_speed = max(0.0, float(g.windSpeed))
        state.wind_direction = float(g.windDirection)

        # --- Coordenadas do Carro (Multi-Carro no ACC) ---
        player_id = int(g.playerCarID)
        if 0 <= player_id < 60:
            coords = g.carCoordinates[player_id]
        else:
            coords = g.carCoordinates[0]
        state.car_x = float(coords[0])
        state.car_y = float(coords[1])
        state.car_z = float(coords[2])

        # --- Eletrônica Específica do ACC ---
        state.tc_level = int(g.TC)
        state.tc_cut_level = int(g.TCCut)
        state.abs_level = int(g.ABS)
        state.engine_map = int(g.EngineMap)

        # --- Clima Dinâmico e Condições do ACC ---
        state.rain_intensity = RAIN_INTENSITY_NAMES.get(int(g.rainIntensity), "No Rain")
        state.rain_intensity_in_10min = RAIN_INTENSITY_NAMES.get(int(g.rainIntensityIn10min), "No Rain")
        state.rain_intensity_in_30min = RAIN_INTENSITY_NAMES.get(int(g.rainIntensityIn30min), "No Rain")
        state.track_grip_status = TRACK_GRIP_NAMES.get(int(g.trackGripStatus), "Optimum")

        # Densidade de chuva aproximada 0.0 a 1.0
        rain_map = {0: 0.0, 1: 0.2, 2: 0.4, 3: 0.65, 4: 0.85, 5: 1.0}
        state.rain_density = rain_map.get(int(g.rainIntensity), 0.0)

        # Pista molhada: se grip é baixo ou chovendo
        grip_wetness = {0: 0.0, 1: 0.0, 2: 0.0, 3: 0.2, 4: 0.5, 5: 0.8, 6: 1.0}
        state.track_wetness = max(state.rain_density, grip_wetness.get(int(g.trackGripStatus), 0.0))

        # --- Stints, Luzes e Validade da Volta ---
        state.is_valid_lap = bool(g.isValidLap)
        state.exhaust_temp = float(g.exhaustTemperature)
        state.wiper_stage = int(g.wiperLV)
        state.lights_stage = int(g.lightsStage)
        state.rain_lights = bool(g.rainLights)
        state.stint_time_left = max(0, int(g.DriverStintTimeLeft // 1000))
        state.stint_total_time_left = max(0, int(g.DriverStintTotalTimeLeft // 1000))


# Aliases para compatibilidade total com o ecossistema existente
AssettoCorsaTelemetryProvider = ACCTelemetryProvider
ACTelemetryProvider = ACCTelemetryProvider
