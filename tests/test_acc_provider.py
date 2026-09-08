"""
tests/test_acc_provider.py — Teste do provider do Assetto Corsa Competizione (ACC)
==================================================================================
Valida:
  1. Tamanhos e alinhamentos exatos dos structs de memória compartilhada do ACC:
     - SPageFilePhysics (800 bytes)
     - SPageFileGraphic (1588 bytes)
     - SPageFileStatic (820 bytes)
  2. Mapeamento correto de canais: entradas, eletrônica GT3 (TC, TC Cut, ABS, Map),
     clima dinâmico (chuva, previsões e grip), temperaturas (água, freios, pneus),
     coordenadas multi-carro (playerCarID) e conversões de unidade.
  3. Lógica de detecção de conexão e desconexão por timeout.
"""
import ctypes
import math
import mmap
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from providers.acc import (
    ACCTelemetryProvider,
    SPageFilePhysics,
    SPageFileGraphic,
    SPageFileStatic,
)

# 1. Validação estrita de tamanhos dos structs
assert ctypes.sizeof(SPageFilePhysics) == 800, f"SPageFilePhysics size incorreto: {ctypes.sizeof(SPageFilePhysics)} (esperado 800)"
assert ctypes.sizeof(SPageFileGraphic) == 1588, f"SPageFileGraphic size incorreto: {ctypes.sizeof(SPageFileGraphic)} (esperado 1588)"
assert ctypes.sizeof(SPageFileStatic) == 820, f"SPageFileStatic size incorreto: {ctypes.sizeof(SPageFileStatic)} (esperado 820)"

# 2. Criação dos blocos de memória compartilhada do teste
maps = {}
for tag, cls in (("acpmf_physics", SPageFilePhysics),
                 ("acpmf_graphics", SPageFileGraphic),
                 ("acpmf_static", SPageFileStatic)):
    mm = mmap.mmap(-1, ctypes.sizeof(cls), tagname=f"Local\\{tag}")
    maps[tag] = (mm, cls)

p = SPageFilePhysics()
p.packetId = 1
p.gas, p.brake, p.clutch = 0.90, 0.15, 1.0     # clutch=1.0 -> pedal solto (0.0 na UI)
p.fuel = 55.0
p.gear = 4                                      # 3ª marcha
p.rpms = 7800
p.steerAngle = math.radians(28.5)              # radianos -> 28.5 graus
p.speedKmh = 215.3
p.accG[0], p.accG[1], p.accG[2] = 1.65, 0.98, -0.75

for i in range(4):
    p.wheelsPressure[i] = 27.5 + i * 0.2
    p.tyreWear[i] = 98.0 - i
    p.tyreCoreTemperature[i] = 85.0 + i
    p.tyreTempI[i], p.tyreTempM[i], p.tyreTempO[i] = 92.0, 88.0, 81.0
    p.suspensionTravel[i] = 0.025
    p.brakeTemp[i] = 520.0 - i * 30
    p.brakePressure[i] = 45.0 + i * 2.0
    p.padLife[i] = 28.5 - i * 0.5
    p.discLife[i] = 19.8 - i * 0.2
    p.wheelSlip[i] = 0.08

p.tc, p.abs = 0.25, 0.0
p.tcinAction = 1
p.absInAction = 0
p.pitLimiterOn = 0
p.turboBoost = 1.45
p.airTemp, p.roadTemp = 21.0, 26.5
p.waterTemp = 88.4
p.carDamage[0], p.carDamage[4] = 2.0, 8.0
p.brakeBias = 0.58
p.finalFF = 0.92

g = SPageFileGraphic()
g.packetId = 1
g.status = 2                     # AC_LIVE
g.session = 2                    # Race
g.completedLaps = 8
g.position = 3
g.iCurrentTime = 72_350
g.iLastTime = 138_420
g.iBestTime = 137_110
g.sessionTimeLeft = 1_800_000.0  # ms
g.currentSectorIndex = 2
g.lastSectorTime = 41_200
g.numberOfLaps = 25
g.tyreCompound = "Dry (DHE)"
g.normalizedCarPosition = 0.65
g.isInPit, g.isInPitLane = 0, 0
g.surfaceGrip = 0.985
g.windSpeed, g.windDirection = 3.5, 180.0
g.flag = 7                       # VERDE

# Multi-carro do ACC: 3 carros, jogador é o index 1
g.activeCars = 3
g.playerCarID = 1
g.carCoordinates[0][0], g.carCoordinates[0][1], g.carCoordinates[0][2] = 100.0, 10.0, 200.0
g.carCoordinates[1][0], g.carCoordinates[1][1], g.carCoordinates[1][2] = 250.5, 12.3, 480.8
g.carCoordinates[2][0], g.carCoordinates[2][1], g.carCoordinates[2][2] = 300.0, 15.0, 520.0

# Eletrônica GT3 e Cabine
g.TC = 4
g.TCCut = 2
g.ABS = 3
g.EngineMap = 1
g.exhaustTemperature = 650.0
g.wiperLV = 1
g.lightsStage = 2
g.rainLights = 0
g.DriverStintTimeLeft = 3_600_000       # 3600s
g.DriverStintTotalTimeLeft = 7_200_000  # 7200s
g.isValidLap = 1

# Clima e Grip
g.trackGripStatus = 2            # Optimum
g.rainIntensity = 0              # No Rain
g.rainIntensityIn10min = 1       # Drizzle
g.rainIntensityIn30min = 3       # Medium Rain

s = SPageFileStatic()
s.smVersion, s.acVersion = "1.8", "1.9.8"
s.carModel = "ferrari_296_gt3"
s.track = "spa"
s.playerName, s.playerSurname = "Joao", "Lamim"
s.sectorCount = 3
s.maxRpm = 8500
s.maxFuel = 110.0
s.maxTurboBoost = 2.0
s.trackSPlineLength = 7004.0
s.isOnline = 1

for tag, obj in (("acpmf_physics", p), ("acpmf_graphics", g), ("acpmf_static", s)):
    mm, cls = maps[tag]
    mm.seek(0)
    mm.write(bytes(obj))

# 3. Leitura e testes via ACCTelemetryProvider
prov = ACCTelemetryProvider()
assert prov.connect(), "connect() falhou com os blocos criados"

# packetId precisa mudar para o provider considerar "fresco"
p.packetId = 2
maps["acpmf_physics"][0].seek(0)
maps["acpmf_physics"][0].write(bytes(p))
st = prov.get_state()

checks = [
    ("is_connected", st.is_connected, True),
    ("car_name", st.car_name, "Ferrari 296 GT3"),
    ("track_name", st.track_name, "Circuit de Spa-Francorchamps"),
    ("max_rpm", st.max_rpm, 8500.0),
    ("track_length", st.track_length, 7004.0),
    ("fuel_capacity", st.fuel_capacity, 110.0),
    ("gas", round(st.gas, 2), 0.90),
    ("brake", round(st.brake, 2), 0.15),
    ("clutch (invertido)", round(st.clutch, 2), 0.0),
    ("steer_angle (graus)", round(st.steer_angle, 1), 28.5),
    ("gear", st.gear, 4),
    ("rpm", st.rpm, 7800),
    ("speed_kmh", round(st.speed_kmh, 1), 215.3),
    ("fuel", round(st.fuel, 1), 55.0),
    ("turbo_boost", round(st.turbo_boost, 2), 1.45),
    ("g_lat", round(st.g_lat, 2), 1.65),
    ("g_lon", round(st.g_lon, 2), -0.75),
    ("tc_active", st.tc_active, True),
    ("abs_active", st.abs_active, False),
    ("tc_intervention", round(st.tc_intervention, 2), 0.25),
    ("brake_bias", round(st.brake_bias, 2), 0.58),
    ("ffb_level", round(st.ffb_level, 2), 0.92),
    # Eletrônica específica do ACC:
    ("tc_level", st.tc_level, 4),
    ("tc_cut_level", st.tc_cut_level, 2),
    ("abs_level", st.abs_level, 3),
    ("engine_map", st.engine_map, 1),
    # Clima e Grip:
    ("rain_intensity", st.rain_intensity, "No Rain"),
    ("rain_intensity_in_10min", st.rain_intensity_in_10min, "Drizzle"),
    ("rain_intensity_in_30min", st.rain_intensity_in_30min, "Medium Rain"),
    ("track_grip_status", st.track_grip_status, "Optimum"),
    # Temperaturas e Freios estendidos:
    ("water_temp", round(st.water_temp, 1), 88.4),
    ("exhaust_temp", round(st.exhaust_temp, 1), 650.0),
    ("brake_temp[0]", round(st.brake_temp[0], 1), 520.0),
    ("brake_pressure[0]", round(st.brake_pressure[0], 1), 45.0),
    ("pad_life[0]", round(st.pad_life[0], 1), 28.5),
    ("disc_life[0]", round(st.disc_life[0], 1), 19.8),
    # Coordenadas multi-carro (playerCarID = 1):
    ("car_x (playerCarID=1)", round(st.car_x, 1), 250.5),
    ("car_y (playerCarID=1)", round(st.car_y, 1), 12.3),
    ("car_z (playerCarID=1)", round(st.car_z, 1), 480.8),
    # Sessão e Tempos:
    ("current_time", st.current_time, "1:12.350"),
    ("last_time", st.last_time, "2:18.420"),
    ("best_time", st.best_time, "2:17.110"),
    ("sector_index", st.sector_index, 2),
    ("last_sector_time", st.last_sector_time, 41200),
    ("lap_number", st.lap_number, 9),
    ("race_position", st.race_position, 3),
    ("track_position", round(st.track_position, 2), 0.65),
    ("session_type", st.session_type, "Race"),
    ("flag", st.flag, "VERDE"),
    ("is_valid_lap", st.is_valid_lap, True),
    ("stint_time_left", st.stint_time_left, 3600),
    ("stint_total_time_left", st.stint_total_time_left, 7200),
    ("wiper_stage", st.wiper_stage, 1),
    ("lights_stage", st.lights_stage, 2),
]

fails = [(n, got, exp) for n, got, exp in checks if got != exp]
for n, got, exp in checks:
    mark = "OK " if (n, got, exp) not in fails else "ERRO"
    print(f"  [{mark}] {n:28s} = {got!r}" + ("" if (n, got, exp) not in fails else f"  (esperado {exp!r})"))

# Desconexão por congelamento de packetId
prov._last_packet_change -= 3.0
st2 = prov.get_state()
print(f"\n  [{'OK ' if not st2.is_connected else 'ERRO'}] desconexao por packetId congelado -> is_connected={st2.is_connected}")
assert not st2.is_connected, "Deveria desconectar após packetId congelado"

prov.close()
for mm, _ in maps.values():
    mm.close()

print(f"\n=== {len(checks) - len(fails)}/{len(checks)} verificacoes passaram com sucesso ===")
sys.exit(1 if fails else 0)
