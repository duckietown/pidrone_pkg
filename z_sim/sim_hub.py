from z_flight_sim import DroneSim
from pid_class import PID
import matplotlib.pyplot as plt
import time

def main():
    sim = DroneSim()
    pid = PID(60.,60.,100.)
    
    ts = []
    ps = []

    target = 0.5
    pid.reset()
    sim.step()
    sim.pos = 0.08
    while sim.t < 10:
        sim.step()
        
        m = sim.measure_pos()
        if m is not None:
            print sim.t, sim.throttle, sim.accel, sim.pos
            ts.append(sim.t)
            ps.append(m)
            pwm = pid.step(target - m ,sim.t)
            
            sim.set_throttle(pwm)

    plt.plot(ts, ps)
    plt.show()

if __name__ == '__main__':
    main()
