# truth.py - the simulated "true" physical state that mock sensors sample. [SIMULATED]
# (port of lib/hal_mock/TruthSource.h). Produced by a scripted SYNTHETIC profile.


class TruthState:
    def __init__(self):
        self.truth_ms = 0
        self.segment = -1
        self.label = ""
        self.alt_m = 0.0
        self.vz_mps = 0.0
        self.pressure_pa = 0.0
        self.temp_c = 0.0
        self.accel_g = [0.0, 0.0, 0.0]
        self.gyro_dps = [0.0, 0.0, 0.0]
        self.mounted = False
        self.bus_v = 0.0
        self.current_ma = 0.0


class TruthSource:
    def truth_at(self, truth_ms):
        raise NotImplementedError
