"""
mock_game.py — Simulador de Telemetria do Assetto Corsa Competizione (ACC)
===========================================================================
Gera telemetria gravando diretamente na memória compartilhada do Windows
(Local\\acpmf_physics, Local\\acpmf_graphics, Local\\acpmf_static)
usando as estruturas nativas do Assetto Corsa Competizione (ACC).

COMO USAR:
  1. Terminal A: python mock_game.py
  2. Terminal B: python main.pyw (com MOCK_MODE = False ou sem --mock)
"""

import ctypes
import math
import mmap
import time

from providers.acc import SPageFilePhysics, SPageFileGraphic, SPageFileStatic
from providers.mock import MockTelemetryProvider


def run_mock_acc():
    print("=" * 65)
    print("  ACC Mock Telemetry | Circuit de Spa-Francorchamps | Ferrari 296 GT3")
    print("=" * 65)
    print("  Inicializando memória compartilhada do Windows para ACC...")

    # Criação dos mapeamentos de memória (Windows) do ACC
    shm_p = mmap.mmap(-1, ctypes.sizeof(SPageFilePhysics), "Local\\acpmf_physics")
    shm_g = mmap.mmap(-1, ctypes.sizeof(SPageFileGraphic), "Local\\acpmf_graphics")
    shm_s = mmap.mmap(-1, ctypes.sizeof(SPageFileStatic), "Local\\acpmf_static")

    # Vinculando as structs aos buffers de memória para escrita direta
    physics = SPageFilePhysics.from_buffer(shm_p)
    graphics = SPageFileGraphic.from_buffer(shm_g)
    static = SPageFileStatic.from_buffer(shm_s)

    # 1. Preenche bloco estático do ACC
    static.smVersion = "1.8"
    static.acVersion = "1.9.8"
    static.carModel = "ferrari_296_gt3"
    static.track = "spa"
    static.playerName = "ACC Pilot"
    static.playerSurname = "Sim"
    static.maxRpm = 8500
    static.maxFuel = 110.0
    static.trackSPlineLength = 7004.0
    static.sectorCount = 3
    static.isOnline = 0
    static.dryTyresName = "DHE"
    static.wetTyresName = "WH"

    print("  Memória mapeada com sucesso (Physics: 800B, Graphics: 1588B, Static: 820B).")
    print("  Gerando telemetria ACC a 60 Hz... (Pressione Ctrl+C para sair)")
    print("=" * 65)

    provider = MockTelemetryProvider()
    provider.connect()

    packet_id = 0

    try:
        while True:
            state = provider.get_state()
            packet_id += 1

            # --- Atualiza Física ACC ---
            physics.packetId = packet_id
            physics.gas = state.gas
            physics.brake = state.brake
            physics.clutch = 1.0 - state.clutch  # 1.0 = embreagem solta no jogo
            physics.fuel = state.fuel
            physics.gear = state.gear
            physics.rpms = state.rpm
            # No ACC o volante é fornecido em radianos
            physics.steerAngle = math.radians(state.steer_angle)
            physics.speedKmh = state.speed_kmh
            physics.accG[0] = state.g_lat
            physics.accG[1] = state.g_vert
            physics.accG[2] = state.g_lon
            physics.tc = state.tc_intervention
            physics.abs = state.abs_intervention
            physics.tcinAction = 1 if state.tc_active else 0
            physics.absInAction = 1 if state.abs_active else 0
            physics.waterTemp = 89.5
            physics.finalFF = state.ffb_level

            for i in range(4):
                physics.tyreCoreTemperature[i] = state.tyre_temp[i]
                physics.wheelsPressure[i] = state.tyre_pressure[i]
                physics.tyreWear[i] = state.tyre_wear[i]
                physics.suspensionTravel[i] = state.suspension_travel[i] / 1000.0  # volta para metros
                physics.brakeTemp[i] = state.brake_temp[i]
                physics.tyreTempI[i] = state.tyre_temp_inner[i]
                physics.tyreTempM[i] = state.tyre_temp_middle[i]
                physics.tyreTempO[i] = state.tyre_temp_outer[i]
                physics.brakePressure[i] = 50.0 * state.brake
                physics.padLife[i] = 29.0
                physics.discLife[i] = 19.5

            # --- Atualiza Gráficos ACC ---
            graphics.packetId = packet_id
            graphics.status = 2  # AC_LIVE
            graphics.session = 0 # Practice
            graphics.currentTime = state.current_time
            graphics.lastTime = state.last_time
            graphics.bestTime = state.best_time

            def t_to_ms(t_str):
                try:
                    if not t_str or t_str.startswith("-"): return 0
                    if "." in t_str:
                        parts = t_str.rsplit(".", 1)
                        m_s = parts[0].split(":")
                        m = int(m_s[0]) if len(m_s) >= 2 else 0
                        s = int(m_s[-1])
                        return (m * 60 * 1000) + (s * 1000) + int(parts[1])
                except Exception:
                    pass
                return 0

            graphics.iCurrentTime = t_to_ms(state.current_time)
            graphics.iLastTime = t_to_ms(state.last_time)
            graphics.iBestTime = t_to_ms(state.best_time)
            graphics.distanceTraveled = state.distance_traveled
            graphics.currentSectorIndex = state.sector_index
            graphics.completedLaps = state.completed_laps
            graphics.isInPit = 1 if state.in_pit else 0
            graphics.isInPitLane = 1 if state.in_pit_lane else 0
            graphics.normalizedCarPosition = state.track_position
            graphics.surfaceGrip = 0.99
            graphics.tyreCompound = "Dry (DHE)"

            # Multi-carro do ACC:
            graphics.activeCars = 1
            graphics.playerCarID = 0
            graphics.carCoordinates[0][0] = state.car_x
            graphics.carCoordinates[0][1] = state.car_y
            graphics.carCoordinates[0][2] = state.car_z

            # Eletrônica GT3 e Status
            graphics.TC = 3
            graphics.TCCut = 2
            graphics.ABS = 3
            graphics.EngineMap = 1
            graphics.exhaustTemperature = 680.0
            graphics.isValidLap = 1
            graphics.trackGripStatus = 2  # Optimum
            graphics.rainIntensity = 0    # No Rain
            graphics.rainIntensityIn10min = 0
            graphics.rainIntensityIn30min = 0

            # Feedback no terminal
            if packet_id % 60 == 0:
                print(f"  Volta: {state.lap_number:02d} | Tempo: {state.current_time} | Vel: {int(state.speed_kmh):03d} km/h | TC: {graphics.TC} ABS: {graphics.ABS}", end="\r")

            time.sleep(1 / 60.0)

    except KeyboardInterrupt:
        print("\n\n  Mock ACC encerrado.")
    finally:
        shm_p.close()
        shm_g.close()
        shm_s.close()


if __name__ == "__main__":
    run_mock_acc()
