from pid_class import PID
from geometry_msgs.msg import PoseStamped
from sensor_msgs.msg import Range
from std_msgs.msg import String
import rospy
import numpy as np
from pidrone_pkg.msg import axes_err, Mode, State
from h2rMultiWii import MultiWii
import time
import signal


class StateController(object):
    
    ARMED = 0
    DISARMED = 4
    FLYING = 5

    def __init__(self):
        self.initial_set_z = 30.0
        self.set_z = self.initial_set_z
        self.ultra_z = 0

        self.error = axes_err()
        self.pid = PID()

        self.set_vel_x = 0
        self.set_vel_y = 0

        self.last_heartbeat = None

        self.cmd_velocity = [0, 0]
        self.cmd_yaw_velocity = 0

        self.prev_angx = 0
        self.prev_angy = 0
        self.prev_angt = None

        self.mw_angle_comp_x = 0
        self.mw_angle_comp_y = 0
        self.mw_angle_alt_scale = 1.0
        self.mw_angle_coeff = 10.0

        self.commanded_mode = self.DISARMED
        self.current_mode = self.DISARMED

        self.keep_going = True

    def arm(self, board):
        arm_cmd = [1500, 1500, 2000, 900]
        board.sendCMD(8, MultiWii.SET_RAW_RC, arm_cmd)
        board.receiveDataPacket()
        rospy.sleep(1)

    def disarm(self, board):
        disarm_cmd = [1500, 1500, 1000, 900]
        board.sendCMD(8, MultiWii.SET_RAW_RC, disarm_cmd)
        board.receiveDataPacket()
        rospy.sleep(1)

    def fly(self, msg):
        if msg is not None:
            self.set_vel_x = msg.x_velocity
            self.set_vel_y = msg.y_velocity

            self.cmd_velocity = [msg.x_i, msg.y_i]
            self.cmd_yaw_velocity = msg.yaw_velocity

            new_set_z = self.set_z + msg.z_velocity
            if 0.0 < new_set_z < 49.0:
                self.set_z = new_set_z

    def heartbeat_callback(self, msg):
        self.last_heartbeat = rospy.Time.now()

    def ultra_callback(self, msg):
        if msg.range != -1:
            # scale ultrasonic reading to get z accounting for tilt of the drone
            self.ultra_z = msg.range * self.mw_angle_alt_scale
            self.error.z.err = self.set_z - self.ultra_z

    def vrpn_callback(self, msg):
        # mocap uses y-axis to represent the drone's z-axis motion
        self.ultra_z = msg.pose.position.y
        self.error.z.err = self.set_z - self.ultra_z

    def plane_callback(self, msg):
        self.error.x.err = (msg.x.err - self.mw_angle_comp_x) * self.ultra_z + self.set_vel_x
        self.error.y.err = (msg.y.err + self.mw_angle_comp_y) * self.ultra_z + self.set_vel_y

    def mode_callback(self, msg):
        self.commanded_mode = msg.mode
        
        if self.current_mode == self.FLYING:
            self.fly(msg)

    def calc_angle_comp_values(self, mw_data):
        new_angt = time.time()
        new_angx = mw_data['angx'] / 180.0 * np.pi
        new_angy = mw_data['angy'] / 180.0 * np.pi
        self.mw_angle_comp_x = np.tan((new_angx - self.prev_angx) * (new_angt - self.prev_angt)) * self.mw_angle_coeff
        self.mw_angle_comp_y = np.tan((new_angy - self.prev_angy) * (new_angt - self.prev_angt)) * self.mw_angle_coeff

        self.mw_angle_alt_scale = np.cos(new_angx) * np.cos(new_angy)
        # I JUST ADDED THIS IN HAHA
        self.pid.throttle.mw_angle_alt_scale = self.mw_angle_alt_scale

        self.prev_angx = new_angx
        self.prev_angy = new_angy
        self.prev_angt = new_angt

    def shouldIDisarm(self):
        if rospy.Time.now() - self.last_heartbeat > rospy.Duration.from_sec(5):
            return True
        else:
            return False

    def ctrl_c_handler(self, signal, frame):
        print "Caught ctrl-c! About to Disarm!"
        self.keep_going = False

if __name__ == '__main__':

    rospy.init_node('state_controller')

    sc = StateController()
    sc.last_heartbeat = rospy.Time.now()

    # ROS Setup
    ###########

    # Publishers
    ############
    errpub = rospy.Publisher('/pidrone/err', axes_err, queue_size=1)
    modepub = rospy.Publisher('/pidrone/mode', Mode, queue_size=1)

    # Subscribers
    #############
    rospy.Subscriber("/pidrone/plane_err", axes_err, sc.plane_callback)
    rospy.Subscriber("/pidrone/infrared", Range, sc.ultra_callback)
    rospy.Subscriber("/pidrone/vrpn_pos", PoseStamped, sc.vrpn_callback)
    rospy.Subscriber("/pidrone/set_mode_vel", Mode, sc.mode_callback)
    rospy.Subscriber("/pidrone/heartbeat", String, sc.heartbeat_callback)

    # Non-ROS Setup
    ###############
    signal.signal(signal.SIGINT, sc.ctrl_c_handler)
    board = MultiWii("/dev/ttyUSB0")

    sc.prev_angt = time.time()

    mode_to_pub = Mode()

    while not rospy.is_shutdown() and sc.keep_going:
        mode_to_pub.mode = sc.current_mode
        modepub.publish(mode_to_pub)
        errpub.publish(sc.error)

        mw_data = board.getData(MultiWii.ATTITUDE)
        analog_data = board.getData(MultiWii.ANALOG)

        try:
            if not sc.current_mode == sc.DISARMED:
                sc.calc_angle_comp_values(mw_data)

                if sc.shouldIDisarm():
                    print "Disarming because a safety check failed."
                    break

            fly_cmd = sc.pid.step(sc.error, sc.cmd_velocity, sc.cmd_yaw_velocity)

            if sc.current_mode == sc.DISARMED:
                if sc.commanded_mode == sc.DISARMED:
                    print 'DISARMED -> DISARMED'
                elif sc.commanded_mode == sc.ARMED:
                    sc.arm(board)
                    sc.current_mode = sc.ARMED
                    print 'DISARMED -> ARMED'
                else:
                    print 'Cannot transition from Mode %d to Mode %d' % (sc.current_mode, sc.commanded_mode)

            elif sc.current_mode == sc.ARMED:
                if sc.commanded_mode == sc.ARMED:
                    idle_cmd = [1500, 1500, 1500, 1000]
                    board.sendCMD(8, MultiWii.SET_RAW_RC, idle_cmd)
                    board.receiveDataPacket()
                    print 'ARMED -> ARMED'
                elif sc.commanded_mode == sc.FLYING:
                    sc.current_mode = sc.FLYING
                    sc.pid.reset(sc)
                    print 'ARMED -> FLYING'
                elif sc.commanded_mode == sc.DISARMED:
                    sc.disarm(board)
                    sc.current_mode = sc.DISARMED
                    print 'ARMED -> DISARMED'
                else:
                    print 'Cannot transition from Mode %d to Mode %d' % (sc.current_mode, sc.commanded_mode)

            elif sc.current_mode == sc.FLYING:
                if sc.commanded_mode == sc.FLYING:
                    r, p, y, t = fly_cmd
                    print 'Fly Commands (r, p, y, t): %d, %d, %d, %d' % (r, p, y, t)
                    board.sendCMD(8, MultiWii.SET_RAW_RC, fly_cmd)
                    board.receiveDataPacket()
                    print 'FLYING -> FLYING'
                elif sc.commanded_mode == sc.DISARMED:
                    sc.disarm(board)
                    sc.current_mode = sc.DISARMED
                    print 'FLYING -> DISARMED'
                else:
                    print 'Cannot transition from Mode %d to Mode %d' % (sc.current_mode, sc.commanded_mode)
        except:
            print "BOARD ERRORS!!!!!!!!!!!!!!"
            raise

    sc.disarm(board)
    print "Shutdown Received"



