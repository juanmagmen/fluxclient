# -*- coding: utf-8 -*-
"""

.. moduleauthor:: Yen Feng <yen@flux3dp.com>
.. note::

   An example of intersphinx is this: you **cannot** use :mod:`pickle` on this class.


"""
from io import BytesIO
import struct
import logging
import sys
from uuid import UUID

import msgpack
from PIL import Image

from fluxclient.hw_profile import HW_PROFILE
from fluxclient.commands.misc import get_device_endpoint
from fluxclient.robot import connect_robot
from fluxclient.encryptor import KeyObject
from fluxclient.upnp.task import UpnpTask
from fluxclient.commands.misc import get_or_create_default_key
from fluxclient.sdk import *

logger = logging.getLogger(__name__)


def prepare_robot(endpoint, server_key, client_key):
    def conn_callback(*args):
        sys.stdout.write(".")
        sys.stdout.flush()
        return True
    robot = connect_robot(endpoint, server_key=server_key,
                          client_key=client_key, conn_callback=conn_callback)
    pos = robot.position()
    if pos == "CommandTask":
        robot.begin_scan()
    elif pos == "ScanTask":
        pass
    else:
        raise RuntimeError("Unknow position: %s" % pos)

    return robot


def type_check(instance, type_candidates, err_msg=''):
    if isinstance(instance, type_candidates):
        return
    else:
        raise TypeError('{} type: {} is not supported'.format(err_msg, type(instance)))


class Delta(object):
    """We use this as a public class example class.

      I don't **know** what's going *on*::

       print(ola)

      hi

    """
    def __init__(self, target=None, ip=None, client_key=None, password=None):
        super(Delta, self).__init__()

        self.connect_delta(target=target, ip=ip, client_key=client_key, password=password)

        # ipaddr, metadata = get_device_endpoint(target, client_key, 23811)
        # self.robot = connect_robot(ipaddr, metadata=metadata, client_key=client_key)

        self.tool_head_pos = [0, 0, HW_PROFILE["model-1"]["height"]]
        self.motor_pos = {"e0": 0.0, "e1": 0.0, "e2": 0.0}
        self.laser_status = {"L": False, "R": False}
        self.motor_status = {"e0": True, "e1": True, "e2": False}  # [("e0", "E"), ("e1", "S"), ("e2", "U")]
        self.loose_flag = False

    def __del__(self):
        # turn off laser
        # self.turn_laser("L", False)
        # self.turn_laser("R", False)
        pass

    def connect_delta(self, target, ip, client_key, password):
        if client_key:
            if type(client_key) == str:
                client_key = get_or_create_default_key(client_key)
            elif type(client_key) == KeyObject:
                pass
            else:
                type_check(client_key, (str, KeyObject), 'client_key')
        else:
            client_key = get_or_create_default_key()
        if target:
            type_check(target, str, 'target')
            target = UUID(target)
        if ip:
            type_check(ip, str, 'ip')
        if password:
            type_check(password, str, 'password')

        options = {'uuid': UUID(int=0)}
        for i, name in [(target, 'uuid'), (ip, 'ipaddr'), (client_key, 'client_key')]:
            if i:
                options[name] = i
        if password:
            options['backend_options'] = {'password': password}

        upnp_task = UpnpTask(**options)

        print('authorized', upnp_task.authorized)
        if not upnp_task.authorized:
            # password = 'a'
            if password:
                upnp_task.authorize_with_password(password)
                if upnp_task.authorized:
                    upnp_task.add_trust('sdk key', client_key.public_key_pem.decode())
                    print('[Warning]: adding new key into flux delta', file=sys.stderr)
        print('authorized', upnp_task.authorized)
        if upnp_task.authorized:
            self.robot = connect_robot((upnp_task.ipaddr, 23811), client_key)
            ret = self.robot._make_cmd(b"task icontrol")
            print('ret', ret)
            assert ret == b"ok", ret
        else:
            raise RuntimeError("cannot connect to flux delta")

    def get_position(self):
        """
        Get the current position of toolhead

        :return: coordinate of each tower
        :rtype: (float, float, float)

        >>> f.get_position()
        (0, 0, 280)
        """
        return tuple(self.tool_head_pos)

    def home(self):
        """
        Set each axis back to home.

        :return: the distance each axis goes
        :rtype: (float, float, float)

        >>> f.home()
        (20.0, 20.0, 20.0)
        >>> f.get_position()
        (0, 0, 280)
        """
        self.loose_flag = False
        buf = msgpack.packb(CMD_G028)
        self.send_asdf(buf)

    def move(self, x=None, y=None, z=None, speed=None, relative=False, **kargs):
        """
        Move the toolhead to (x, y, z)

        :param float x: x coordinate, optional
        :param float y: y coordinate, optional
        :param float z: z coordinate, optional
        :param bool relative: moving relatively or not, default: False

        :param float e0: length mortor e0 move , optional
        :param float e1: length mortor e0 move , optional
        :param float e2: length mortor e0 move , optional


        :return: position after moving command
        :rtype: (float, float, float)

        :raises ValueError: if trying to the exceed the limitation of machine

        * basic usage

        >>> f.get_position()
        (0.0, 0.0, 280.0)
        >>> f.move(50, 40, 30)
        (50.0, 40.0, 30.0)
        >>> f.move(x=80)  # only set the coordinate you want
        (80.0, 40.0, 30.0)
        >>> f.move(x=-10, relative=True)  # using relative flag
        (70.0, 40.0, 30.0)
        >>> f.move(z=-100)
        ValueError: Invalid coordinate

        * control motor during moving

        >>> f.move(50, 40, 30, e0=10)
        (50.0, 40.0, 30.0)

        """
        tmp_pos = self.tool_head_pos[:]
        for name, v, index in [("x", x, 0), ("y", y, 1), ("z", z, 2)]:
            if isinstance(v, (int, float)):
                if relative:
                    tmp_pos[index] += v
                else:
                    tmp_pos[index] = float(v)
            elif v is None:
                pass
            else:
                raise TypeError("unsupported type({1}) for {0} coordinate".format(name, type(v)))
                break
        if tmp_pos[0] ** 2 + tmp_pos[1] ** 2 > HW_PROFILE["model-1"]["radius"] or tmp_pos[2] > HW_PROFILE["model-1"]["height"] or tmp_pos[2] < 0:
            raise ValueError("Invalid coordinate")
        else:
            self.tool_head_pos = tmp_pos

        command = ["X5", "X{}".format(self.tool_head_pos[0]), "Y{}".format(self.tool_head_pos[1]), "Z{}".format(self.tool_head_pos[2])]
        for e, c in [("e0", "E"), ("e1", "S"), ("e2", "U")]:
            if e in kargs:
                if isinstance(kargs[e], (int, float)):
                    command.append("{}{}".format(c, kargs[e]))
                else:
                    raise TypeError("unsupported type({1}) for {0} motor".format(e, type(c)))
                    break
        command = " ".join(command)
        logger.debug(command)
        # robot.makecomamnd.(command)

        return tuple(self.tool_head_pos)

    def get_position_motor(self, motor):
        """
        Get the current position of specified motor

        :param str motor: name of the motor, should be one of the ``"e0", "e1", "e2"``
        :return: the current position of specified motor
        :rtype: float
        :raises ValueError: raise error if using undifine motor name

        >>> f.get_position_motor("e0")
        12.34

        """
        if motor in self.motor_pos:
            return self.motor_pos[motor]
        else:
            raise ValueError("Invalid motor name")

    def move_motor(self, e0=None, e1=None, e2=None):
        """
        Move the motors

        :param float e0: length to move, optional
        :param float e1: length to move, optional
        :param float e2: length to move, optional

        >>> f.move_motor(e0=10)
        >>> f.move_motor(e0=10, e1=10)

        """
        self.move(e0=e0, e1=e1, e2=e2)

    def lock_motor(self, motor):
        """
        Lock the specified motor.

        :param str motor: name of the motor, should be one of the ``"e0", "e1", "e2", "XYZ"``

        >>> f.lock_motor('XYZ')

        """
        pass

    def release_motor(self):
        """
        Release the specified motor.

        :param str motor: name of the motor, should be one of the ``"e0", "e1", "e2", "XYZ"``

        .. note::

            If you ever released motor "XYZ", You have to :meth:`home` before calling :meth:`move` them.

        >>> f.release_motor('XYZ')

        """
        if motor == 'XYZ':
            self.loose_flag = True

    def get_position_laser(self, laser):
        """
        Find out whether the laser is on

        :param str laser: Which laser, should be ``"L"`` or ``"R"``
        :raises ValueError: if the laser parameter is not ``"L"`` or ``"R"``

        >>> f.get_position_laser('L')
        True

        """

        if laser == "L" or laser == "R":
            return self.laser_status[laser]
        else:
            if isinstance(laser, str):
                raise ValueError("Invalid laser name")
            else:
                raise TypeError("Invalid argument type")

    def turn_laser(self, laser, on):
        """
        Control the red laser on machine

        :param str laser: Which laser, should be ``"L"`` or ``"R"``
        :param bool on: turn *on* or *off* the laser
        :raises ValueError: if the laser parameter is not ``"L"`` or ``"R"``

        >>> f.turn_laser('L', True)  # Turn on left laser
        True
        >>> f.turn_laser('R', False)  # Turn off right laser
        False

        """

        if laser == "L" or laser == "R":
            self.laser_status[laser] = bool(on)
            self.robot.scan_laser(self.laser_status["L"], self.laser_status["R"])
        else:
            if isinstance(laser, str):
                raise ValueError("Invalid laser name")
            else:
                raise TypeError("Invalid argument type")

        return self.laser_status[laser]

    def get_image(self):
        """
        Take a picture with Delta's built in camera

        :return: a image object
        :rtype: PIL.Image.Image

        """
        images = self.robot.oneshot()
        image_buf = images[0][1]

        return Image.open(BytesIO(image_buf))

    def serial_write(self, buf):
        """
        """
        pass

    def serial_read(self, buf_size):
        """
        """
        pass

    def disable_motor(self, motor):
        """
        Enable motor control

        :param str motor: Which motor to disable, should be one of ``"XYZ"``, ``"e0"``, ``"e1"``, ``"e2"``
        :raises TypeError: motor is not str
        :raises ValueError: if the motor's name is not one of ``"XYZ"``, ``"e0"``, ``"e1"``, ``"e2"``

        """
        if motor in ["XYZ", "e0", "e1", "e2"]:
            self.motor_status[motor] = False
        else:
            if isinstance(motor, str):
                raise ValueError("Wrong motor name")
            else:
                raise TypeError("Wrong motor type: {}".format(type(motor)))

    def enable_motor(self, motor):
        """
        Disable a motor

        :param str motor: Which motor to enable, should be one of ``"XYZ"``, ``"e0"``, ``"e1"``, ``"e2"``
        :raises TypeError: motor is not str
        :raises ValueError: if the motor's name is not one of ``"XYZ"``, ``"e0"``, ``"e1"``, ``"e2"``

        """
        if motor in ["XYZ", "e0", "e1", "e2"]:
            self.motor_status[motor] = True
        else:
            if isinstance(motor, str):
                raise ValueError("Wrong motor name")
            else:
                raise TypeError("Wrong motor type: {}".format(type(motor)))

    def get_head_info(self):
        """
        Get the basic toolhead info(immutable data).

        :return: dict consist of toolhead's basic information
        :rtype: dict

        >>> f.get_headinfo()  # no tool head connected
        {"module": "N/A"}

        >>> f.get_headinfo()  # print head
        {"version": "1.0.8", "module": "EXTRUDER", "id": "203236325346430100240001", "vendor": "FLUX .inc"}

        >>> f.get_headinfo()  # laser head
        {"version": "1.0.3", "module": "LASER", "id":"203236325346430100260004", "vendor": "FLUX .inc"}


        .. note::

            For current toolhead status use :meth:`get_headstatus`

        """
        # t = self.robot.maintain_headinfo()
        # copy dict
        pass

    def get_head_status(self):
        """
        Get the current toolhead status(mutable data).

        :return: dict consist of toolhead's currrent information
        :rtype: dict

        >>> flux.get_headstatus()
        {"real temp": [24.8], "target_fan": [0.0], "tt":[nan]}

        .. note::

            For basic toolhead information use :meth:`get_headinfo`

        """
        pass

    def set_temp(self, temp):
        """
        Set the temperature of print head

        :param number power: The power of print head, should be within [0.0, 200.0]
        :raises TypeError: if temp is not a number
        :raises ValueError: if the temp is not in [0.0, 200.0]
        :raises RuntimeError: if using wrong type of toolhead

        >>> f.set_temp(200)
        """
        if self.head_type == "EXTRUDER":  # TODO
            if isinstance(temp, (int, float)):
                if temp <= 200.0 and temp >= 0.0:
                    pass  # TODO
                else:
                    raise ValueError("Invalid temperature")
            else:
                raise TypeError("unsupported temp type: {}".format(type(temp)))
        else:
            raise RuntimeError("Head error: {}".format(self.head_type))

    def set_fan(self, speed):
        """
        Set the speed of toolhead's fan

        :param number speed: The power of laser head, should be within [0.0, 1.0]
        :raises TypeError: if speed is not a number
        :raises ValueError: if the power is not in [0.0, 1.0]
        :raises RuntimeError: if using wrong type of toolhead

        >>> f.set_fan(0.5)
        """
        if self.head_type == "EXTRUDER":  # TODO
            if isinstance(speed, (int, float)):
                if speed <= 1.0 and speed >= 0.0:
                    pass  # TODO
                else:
                    raise ValueError("Invalid fan speed")
            else:
                raise TypeError("unsupported speed type: {}".format(type(speed)))
        else:
            raise RuntimeError("Head error: {}".format(self.head_type))

    def set_power(self, power):
        """
        Set the power of laser toolhead

        :param number power: The power of laser head, should be within [0.0, 1.0]
        :raises TypeError: if power is not a number
        :raises ValueError: if the power is not in [0.0, 1.0]
        :raises RuntimeError: if using wrong type of toolhead

        >>> f.set_power(0.5)
        """
        if self.head_type == "LASER":  # TODO
            if isinstance(power, (int, float)):
                if power <= 1.0 and power >= 0.0:
                    pass  # TODO
                else:
                    raise ValueError("Invalid laser power, should be within [0.0, 1.0]")
            else:
                raise TypeError("unsupported power type: {}".format(type(power)))
        else:
            raise RuntimeError("Head error: {}".format(self.head_type))

    def send_asdf(self, buf):
        ret = self.robot.send_binary(buf)
        if ret == 'OK':
            pass
        else:
            raise RuntimeError(ret)

    # def function(self):
    #     """This function prints hello with a name
    #     function:: format_exception(etype, value, tb[, limit=None])

    #     :param str sender: The person sending the message
    #     :param str recipient: The recipient of the message
    #     :param str message_body: The body of the message
    #     :param priority: The priority of the message, can be a number 1-5
    #     :type priority: integer or None
    #     :return: the message id
    #     :rtype: int
    #     :raises ValueError: if the message_body exceeds 160 characters
    #     :raises TypeError: if the message_body is not a basestring

    #     >>> print_hello_with_name('foo')
    #     Hello, foo

    #     """
    #     pass

if __name__ == '__main__':
    # f = Delta(target='4644314102ece08561a1f89cb44fa63a', password='flux')
    f = Delta(ip='192.168.18.114', password='flux')
    # f = Delta(ip='192.168.18.114')

    # print(f.get_position())
    # print(f.home())
    # input('a')
    # from fluxclient.sdk.delta import Delta
