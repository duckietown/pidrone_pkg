#!/usr/bin/env python
import rospy
from pidrone_pkg.msg import RC
from geometry_msgs.msg import Pose, PoseStamped
import time
import tf
import math

millis = lambda: int(round(time.time() * 1000))

kp = {
	'lr': 	0,
	'fb': 	100,
	'yaw': 		0,
	'alt': 		000
}

ki = {
	'lr': 	0.0,
	'fb':	0.0,
	'yaw': 		0.0,
	'alt': 		0.0
} 
kd = {
	'lr': 	0.0,
	'fb': 	0.0,
	'yaw': 		0.0,
	'alt': 		0.0
}


# these positions are global (ie what comes out of the motion tracker)
sp_global  = Pose() # set point
pos_global = Pose() # set point

sp_global.position.x = -0.04
sp_global.position.y = 0.6
sp_global.position.z = 0.185
sp_global.orientation.x = 0
sp_global.orientation.y = 0
sp_global.orientation.z = 0
sp_global.orientation.w = 1

pos_global.position.x = 0
pos_global.position.y = 0
pos_global.position.z = 0
pos_global.orientation.x = 0
pos_global.orientation.y = 0
pos_global.orientation.z = 0
pos_global.orientation.w = 1

# these positions are definted relative to the orientation of the quad
sp 	= {'fb': 0.0, 'lr': 0.0, 'alt': 0.0, 'yaw': 0.0} # set point
pos = {'fb': 0.0, 'lr': 0.0, 'alt': 0.0, 'yaw': 0.0} # current position

output = {'fb': 0.0, 'lr': 0.0, 'alt': 0.0, 'yaw': 0.0}

err   = {'fb': 0.0, 'lr': 0.0, 'alt': 0.0, 'yaw': 0.0}
Pterm = {'fb': 0.0, 'lr': 0.0, 'alt': 0.0, 'yaw': 0.0}
Iterm = {'fb': 0.0, 'lr': 0.0, 'alt': 0.0, 'yaw': 0.0}
Dterm = {'fb': 0.0, 'lr': 0.0, 'alt': 0.0, 'yaw': 0.0}

def pid():
    cmdpub = rospy.Publisher('/pidrone/commands', RC, queue_size=1)
    rc = RC()
    time_prev = millis()
    while not rospy.is_shutdown():
        global sp_global
        global pos_global
        time.sleep(0.05)
        time_elapsed = millis() - time_prev
        time_prev = millis() 
        (sp_global_roll, sp_global_pitch, sp_global_yaw) = tf.transformations.euler_from_quaternion([sp_global.orientation.x, sp_global.orientation.y, sp_global.orientation.z, sp_global.orientation.w])

        (pos_global_roll, pos_global_pitch, pos_global_yaw) = tf.transformations.euler_from_quaternion([pos_global.orientation.x, pos_global.orientation.y, pos_global.orientation.z, pos_global.orientation.w])

        print((pos_global_roll, pos_global_yaw, pos_global_pitch))

        # convert to the quad's frame of reference from the global
        global sp
        global pos
	# XXX jgo: is this supposed to be multiplication of the vector ~_global
	# (in the xz plane) by the rotation matrix induced by ~_global_yaw?  if
	# so, could you be missing a minus sign in front of one of the sin functions?
        sp['fb'] = math.cos(sp_global_yaw) * sp_global.position.z + math.sin(sp_global_yaw) * sp_global.position.x
        sp['lr'] = math.sin(sp_global_yaw) * sp_global.position.z + math.cos(sp_global_yaw) * sp_global.position.x

        pos['fb'] = math.cos(pos_global_yaw) * pos_global.position.z + math.sin(pos_global_yaw) * pos_global.position.x
        pos['lr'] = math.sin(pos_global_yaw) * pos_global.position.z + math.cos(pos_global_yaw) * pos_global.position.x

        sp['yaw'] = sp_global_yaw - pos_global_yaw
        pos['yaw'] = 0.0

        sp['alt'] = sp_global.position.y - pos_global.position.y
        pos['alt'] = 0.0
	# XXX jgo: also it seems like you are setting "sp" yaw and alt relative
	# to the values held by "pos", and setting "pos" values to 0,
	# indicating that both are in the reference frame of "pos". Yet, the fb
	# and lr values of "sp" and "pos" are both set relative to their own
	# yaw values. Do you perhaps mean to use pos_global_yaw rather than
	# sp_global_yaw, and maybe -pos_global_yaw in both cases rather than
	# pos_global_yaw? (this sign matter interacts with whether and where a minus sign
	# should go in front of a sin term above). my suspicion is reinforced,
	# figuring that the output feeds to the roll and pitch of the aircraft in its current
	# position, it seems like you want the fb and lr of both "sp" and "pos"
	# represented in the frame of "pos".  

	# XXX jgo: my apologies if I'm misinterpreting this.


        old_err = err
        for key in sp.keys(): 
            err[key] = sp[key] - pos[key] # update the error

            # calc the PID components of each axis
            Pterm[key] = err[key]
	    # XXX jgo: this is a very literal interpretation of the I term
	    # which might be difficult to tune for reasons which we can
	    # discuss.  it is more typical to take the integral over a finite
	    # interval in the past. This can be implemented with a ring buffer,
	    # or quickly approximated with an exponential moving average.
            Iterm[key] += err[key] * time_elapsed
	    # XXX jgo: the sign of Dterm * kd should act as a viscosity or
	    # resistance term.  if our error goes from 5 to 4, 
	    # then Dterm ~ 4 - 5 = -1; so it looks like kd should be a positive number. 
            Dterm[key] = (err[key] - old_err[key])/time_elapsed
	    # XXX jgo: definitely get something working with I and D terms equal to 0 before using these

            output[key] = Pterm[key] * kp[key] + Iterm[key] * ki[key] + Dterm[key] * kd[key]
        rc.roll = max(1000, min(1500 + output['lr'], 2000))
        rc.pitch = max(1000, min(1500 + output['fb'], 2000))
        rc.yaw = max(1000, min(1500 + output['yaw'], 2000))
        rc.throttle = max(1000, min(1500 + output['alt'], 2000))
        rc.aux1 = 1500
        rc.aux2 = 1500
        rc.aux3 = 1500
        rc.aux4 = 1500
        cmdpub.publish(rc)

def update_sp(data):
    global sp_global
    sp_global = data.pose
    sp_global.position.y -= 0.2

def update_pos(data):
    global pos_global
    pos_global = data.pose

if __name__ == '__main__':
    rospy.init_node('pid_node', anonymous=True)
    try:
        rospy.Subscriber("/vrpn_client_node/wand/pose", PoseStamped, update_sp)
        rospy.Subscriber("/vrpn_client_node/drone/pose", PoseStamped, update_pos)
        pid()
        rospy.spin()

    except rospy.ROSInterruptException:
        pass

