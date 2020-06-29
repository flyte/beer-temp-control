from datetime import datetime, timedelta
from enum import Enum

from simple_pid import PID


class Direction(Enum):
    COOLING = "cooling"
    HEATING = "heating"


class Controller:
    def __init__(
        self,
        setpoint,
        pid_kp=1,
        pid_ki=0.1,
        pid_kd=0.05,
        power_mult=30,
        power_max=254,
        power_min=0,
    ):
        self._current_temp = None
        self._delta_t = None
        self._pid_kp = pid_kp
        self._pid_ki = pid_ki
        self._pid_kd = pid_kd
        self._pid = PID(
            pid_kp,
            pid_ki,
            pid_kd,
            setpoint=setpoint,
            sample_time=1,
            output_limits=(-power_max / power_mult, power_max / power_mult),
        )
        self._power_multiplier = power_mult
        self._power_max = power_max
        self._power_min = power_min

    @property
    def current_temp(self):
        return self._current_temp

    @current_temp.setter
    def current_temp(self, value):
        self._current_temp = value
        self.update()

    @property
    def power_level(self):
        # This should be clamped already by the PID, but just to be sure
        return max(
            self._power_min,
            min(abs(self._delta_t * self._power_multiplier), self._power_max),
        )

    @property
    def direction(self):
        return Direction.HEATING if self._delta_t >= 0 else Direction.COOLING

    @property
    def setpoint(self):
        return self._pid.setpoint

    @setpoint.setter
    def setpoint(self, value):
        self._pid.setpoint = value

    def update(self):
        self._delta_t = self._pid(self._current_temp)
