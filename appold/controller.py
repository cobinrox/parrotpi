from .config import SIMULATION_MODE

# Select servo backend
if SIMULATION_MODE:
    from .sim.sim_servo import SimServo as Servo
    from .sim.sim_audio import SimAudio as Audio
    from .sim.sim_inputs import SimInput as Input
else:
    from .hardware.gpio_servo import RealServo as Servo
    from .hardware.gpio_audio import RealAudio as Audio
    from .hardware.gpio_inputs import RealInput as Input