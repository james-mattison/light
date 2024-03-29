#!/usr/bin/env python3
import requests
import threading
import argparse
import json
import time
import os

"""
light.py: methods for controlling Philips Hue Lights via its RESTful API.
maintainer: James Mattison <james.mattison7@gmail.com>


This script expects you to have LIGHT_USER and LIGHT_UNIT in your environmental 
variables. 
LIGHT_USER -> the user ID that you get from the Philips developer API.
              This account is free and can be signed up for here: 
              https://developers.meethue.com/
LIGHT_UNIT -> the HTTP endpoint for the Hue Bridge.
"""

# Disable HTTPS invalid certificate warnings.
requests.packages.urllib3.disable_warnings()

HELP = """
lights <action> [ <subtarg> ]
actions:
  get-lights            Get a list of lights
  get-colors            Get a list of colors you can set the lights to
  get-xy                Get the XY identifier for the current hue

  on / off              Turn on, or off, all lights. If --targets, turn off
                        only the specified lights
  blink                 Blink all lights. If --targets, blink specified lights
  fade                  Loop through all available colors

"""

parser = argparse.ArgumentParser(add_help=False)
parser.add_argument("action", action="store")
parser.add_argument("subtarg", action="store", nargs="?")
parser.add_argument("-H", "--help", action="help")
parser.add_argument("-t", "--targets", action="store", nargs="*", help="A list of bulbs to target.")
parser.add_argument("-I", "--interval", action="store", default=0, type=float,
                    help="The interval at which to blink")
parser.add_argument("-i", "--iterations", action="store", default=0, type=int)
parser.add_argument("-b", "--brightness", action="store", default=None, type=int)
parser.add_argument("-h", "--hue", action="store", default=None, type=int)
parser.add_argument("-s", "--saturation", action="store", default=None)
parser.add_argument("-v", "--verbose", action="store_true", default=False)
HELP_ITEMS = [
    ("get-lights", "Get a list of connected lights."),
    ("get-colors", "Get a list of valid colors"),
    ("on", "Turn light(s) on"),
    ("off", "Turn light(s) off"),
    ("fade", "Fade light(s) colors")
]

class LightException(BaseException):

    def __init__(self, msg: str):
        self.msg = msg

    def __str__(self):
        return self.msg


class Verbose:
    """
    Control verbosity. This is intended to be used with "glight" in order
    to suppress console output messages.
    """
    _verbose = False

    @property
    def verbose(self) -> bool:
        return self._verbose

    @verbose.setter
    def verbose(self, val: bool):
        self._verbose = val


#
# Load the username and IP address.
# The username is gotten from the Hue Developers website. The IP address is determined by the user at setup time.
#
USER = os.environ['LIGHT_USER']
UNIT = os.environ['LIGHT_UNIT']

#
# approximate color codes for each light.
#
BASE_COLORS = {
    "red": 0,
    "orange": 4000,
    "yellow": 8000,
    "lime": 12000,
    "green": 16000,
    "dark_green": 20000,
    "forest_green": 24000,
    "teal": 28000,
    "cyan": 32000,
    "light_blue": 36000,
    "blue": 40000,
    "dark_blue": 44000,
    "magenta": 48000,
    "purple": 52000,
    "pink": 56000,
    "bright_pink": 60000
}

def make_request(*endpoints: str, kind: str = "get", body: dict = None) -> dict or None:
    """
    create the API request for the Hue controller
    endpoints: URL chunks
    kind: request kind, lower case
    body: the JSON-formatted payload for the request
    """
    if body:
        body = {k: v for k, v in body.items() if v is not None}
    targ = f"api/{USER}"
    for endpoint in endpoints:
        targ += "/" + endpoint

    targ = "/".join([UNIT, targ])
    kinds = {
        "get": requests.get,
        "post": requests.post,
        "put": requests.put
    }

    if not kind in kinds:
        print(f"{kind} not in {kinds}")
        raise LightException(f"Invalid request kind: {kind}. Needs to be one of {kinds}.")

    req = kinds[kind](targ, verify=False, json=body)

    return req.json()


def get_color_names() -> list:
    """Return a list of strings of the names of the colors"""
    names = []
    for color in BASE_COLORS.keys():
        names.append(color)
    return names


class LightThreadLoader:
    """
    LightThreadLoader: implementation of threading (to be used with glight).
    The purpose of this class is to permit multiple lights to do independent tasks
    (for example, to use the "fade" feature, which color cycles between all the colors
    that the light supports.)

    """
    threads = {}

    @staticmethod
    def terminate_thread(bulb_name: str):
        """Terminate an actively running thread."""
        if bulb_name in LightThreadLoader.threads.keys():
            del LightThreadLoader.threads[bulb_name]

    def __init__(self, target, *args, **kwargs):
        self.poisoned = False               # Break out of the thread (causes join)
        self.target = target                #
        self.args = args
        self.kwargs = kwargs
        self.forever = kwargs.pop('forever')
        self.thread = self._load_thread()

    def _load_thread(self) -> None or threading.Thread:
        """Instantiate the thread. This will do the work specified by the 0-position of *args."""
        def foreverer(callback, *args, **kwargs):
            """Inner closure to run callback indefinitely, until poisoned."""
            while True:
                if self.poisoned:
                    break
                callback(*args, **kwargs)

        self.terminate_thread(self.target)
        xargs = list(self.args)

        if self.poisoned:
            print(f"Poisoned - attempting to start thread that is poisoned for {self.target}.")
            return

        bulb = _Light(self.target)
        cb = foreverer

        if Verbose.verbose:
            print(f"Thread start, xargs: {xargs}, kwargs: {self.kwargs}")

        thread = threading.Thread(
            target=cb,
            args=(bulb.color_cycle,),
            kwargs=self.kwargs,
            daemon=True)
        self.threads[self.target] = thread
        return thread

    def start(self):
        """Start the thread"""
        print("- Thread started")
        self.thread.start()

    def poison(self):
        """Set the thread to be poisoned. This will cause it to complete after the current iteration."""
        print(f"Poisoning thread for {self.target}")
        self.poisoned = True
        while self.thread.is_alive():
            print("Waiting for thread shutdown...")
            time.sleep(0.1)
        del self


class _Light:
    """
    Light: Class that controls specific bulbs.

    The hue API returns a dictionary, with the keys being a string of an integer, and the values
    consisting of JSON objects that specify the light's current configuration and state.


    """
    _lights = {}
    _bulbs = {}

    def __init__(self, name: str):
        self.name = name                                # bulb name
        self.light_index, self.light = self.get_light() # int, dict
        self._saturation = None                         # int, 0-255
        self._brightness = None                         # int, 0-255
        self._hue = None                                # int, 0-255
        self._room = None                               # str

        self._bulbs[self.name] = self                   # List[_Light]

    @staticmethod
    def get_all_lights():
        """
        Retreive the JSON-formatted object from the Hue Bridge for each light.
        """
        if not _Light._lights:
            _Light._lights = make_request("lights")
        return _Light._lights

    @staticmethod
    def get_all_bulbs():
        """Retrieive all currently discovered bulbs."""
        return _Light._bulbs


    def get_light(self) -> (int, dict):
        """
        Get the actual light object - a JSON formatted object containing the light's config
        and current state.
        """
        lts = self.get_all_lights()

        for idx, ob in lts.items():
            if ob['name'] == self.name:
                return idx, ob

    def set_room(self, name: str) -> None:
        """Map the name of the room to this light. """
        self._room = name

    def get_room(self) -> str:
        """Return the room that this light is located in, as a string."""
        return self._room

    def configure(self, *args, **kwargs) -> None:
        """Change the state of the light."""
        return self._set_state(*args, **kwargs)

    def _set_state(self,
                   on: bool = False,
                   saturation=255,
                   brightness=255,
                   hue=None,
                   forever=False,
                   **kwargs):
        """
        Update the state of a light.

        on: if True, the light is powered on. If false, it is not.
        saturation: an int between 0 and 255; controls whether the light is more white or more color
        brightness: an int between 0 and 255; contrils the brightness of the light.
        hue: a CMYK representation of the color that the light should be set to.
        forever: perform this action on repeat?
        """

        left = ['saturation', 'brightness', 'hue']
        right = [saturation, brightness, hue]
        attribs = dict(zip(left, right))

        for k, v in attribs.items():
            if v:
                setattr(self, k, v)

        body = dict()
        body['sat'] = saturation
        body['bri'] = brightness
        if hue is not None:
            body['hue'] = hue
        if kwargs.get("xy"):
            body['xy'] = kwargs['xy']
        body['on'] = on

        make_request("lights",
                     self.light_index,
                     "state",
                     body=body,
                     kind="put")

    def turn_off(self):
        """Turn this bulb OFF"""
        self._set_state(False)

    def turn_on(self, **kwargs):
        """Turn this bulb ON"""
        self._set_state(True, **kwargs)

    def blink(self, **kwargs):
        """Blink this bulb one time"""
        interval = float(kwargs.get('interval', 1.0))
        if interval is None:
            interval = 1.0

        self._set_state(False)
        time.sleep(interval / 2)
        self._set_state(True)
        time.sleep(interval / 2)

    def set_color(self, color: str, **kwargs):
        """
        Set the color for this bulb. color is expected to be a string with the name of the color, which
        must be in BASE_COLOR's keys.
        """
        clr = None
        if color in BASE_COLORS.keys():
            clr = BASE_COLORS[color]
            self._set_state(True, hue=clr, **kwargs)
        else:
            print(f"Color: {color} not in {list(BASE_COLORS.keys())}")

    def color_cycle(self, interval: int = None, step: int = None, **kwargs):
        """
        Continuously change the color of the bulb. If self.forever, then will continue to
        change until the whole script is terminated.
        """
        if not step:
            step = 200
        else:
            step = int(step)
        if not interval:
            interval = 1.0

        brightness = kwargs.get('brightness') or 255

        for i in range(0, 64000, int(step)):
            self.configure(True, hue=i, brightness=brightness)

        for i in range(0, 64000, 0 - int(step)):
            self.configure(True, hue=i, brightness=brightness)

    def get_state(self):
        ret = make_request("lights", str(self.light_index))
        # print(ret)
        try:
            if ret['state']['on'] is True:
                print(f"- {ret['name']} is ON")
                return True
            else:
                print(f" - {ret['name']} is OFF")
                return False
        except AttributeError as e:
            print(e)


def get_rooms(permit_unreachable: bool = False) -> dict:
    """Retrieve all rooms containing lights. This will give a dictionary like:
    {
        "Bedroom": [ "BedroomLight1", "BedroomLight2" ]
    }
    """
    groups = make_request("groups")
    lights = make_request("lights")
    rooms = {}
    for group in groups.values():
        for idx, bulb in lights.items():
            if idx in group['lights']:
                if not group.get('name') in rooms.keys():
                    rooms[group['name']] = []
                rooms[group['name']].append(bulb)
    return rooms

def get_lights(permit_unreachable: bool = False) -> dict:
    """
    Get a dictionary containing the name of the light, and then the JSON formatted configuration
    for the light. If permit_unreachable, allows the program to continue running if contact with
    the hue bridge is lost.
    """
    lights = {}
    names = _Light.get_all_lights()
    rooms = get_rooms()
    lts = make_request("lights")
    for idx, lt in lts.items():
        if not permit_unreachable:
            if lt['state']['reachable']:
                lights[lt['name']] = _Light(lt['name'])
            else:
                continue
        else:
            lights[lt['name']] = _Light(lt['name'])
        lights[lt['name']].light_index = idx

    for room, obj in rooms.items():
        for lt in lights.keys():
            for ob in obj:
                if lt == ob.get('name'):
                    lights[lt].set_room(room)
    return lights


def get_lights_by_room(permit_unreachable = False) -> dict:
    """
    Build the rooms dict.
    """
    obs = get_lights(permit_unreachable)
    rooms = {}
    for name, bulb in obs.items():
        if not bulb.get_room() in rooms.keys():
            rooms[bulb.get_room()] = []
        rooms[bulb.get_room()].append(bulb)
    return rooms


def wait_for_join():
    """Wait until all threads have either died or been joined."""
    threads = [thread for thread in LightThreadLoader.threads if thread.is_alive()]
    if not threads:
        print("All threads terminated.")
        quit(0)
    else:
        print(f"Waiting for {len(threads)} to join...")
        time.sleep(1)
        wait_for_join()

#
Light = _Light

if __name__ == "__main__":
    lights = make_request("lights")

    args = parser.parse_args()
    if args.verbose:
        Verbose.verbose = True

    optional_kwargs = {}
    for kwarg in ['brightness', 'saturation', 'hue']:
        if args.__dict__.get(kwarg):
            optional_kwargs[kwarg] = args.__dict__.get(kwarg)

    lights = get_lights()

    if args.targets:
        targs = {k: v for k, v in lights.items() if k in args.targets}
    else:
        targs = {}

    if args.action in ["on", "off"]:
        for targ, bulb in targs.items():
            print(f"Turning {args.action} {targ}")
            if args.action == "on":
                bulb.turn_on()
            else:
                bulb.turn_off()


    elif args.action == "color":
        if not args.subtarg:
            print("Failed: you must provide a color to set the light(s) to.\n",
                  "Use get-colors to get a list of valid colors.")
        else:
            for name, bulb in targs.items():
                loader = LightThreadLoader(bulb.set_color, args.subtarg, **optional_kwargs, forever=False)
                loader.start()
            wait_for_join()


    elif args.action == "get-colors":
        print("colors:")
        for color in get_color_names():
            print(" -", color)


    elif args.action == "get-lights":
        print("lights:")
        for light_name in lights.keys():
            print(" -", light_name)

    elif args.action == "blink":
        if args.interval is not None:
            interval = float(args.interval)
        else:
            interval = 1.0

        for name, bulb in targs.items():
            loader = LightThreadLoader(bulb.blink, interval=interval)
            loader.start()
        wait_for_join()

    elif args.action == "fade":
        print(f"fade:")
        for t in targs:
            print("- ", t)

        for name, bulb in targs.items():
            if args.interval:
                interval = int(args.interval)
            else:
                interval = 1.0
            if args.brightness:
                optional_kwargs['brightness'] = args.brightness
            loader = LightThreadLoader(bulb.color_cycle, interval, args.brightness, **optional_kwargs)
            loader.start()
        time.sleep(3600)

    elif args.action == "increment":
        print(f"increment:")
        for t in targs:
            print(" -", t)
        if args.interval:
            howlong = int(args.interval)
        elif args.iterations and not args.interval:
            howlong = int(args.iterations)
        else:
            howlong = 30

        if not args.subtarg:
            print("Need specific light.")
        else:
            if args.subtarg in targs.keys():
                bulb = targs[args.subtarg]
                bulb.turn_on(**optional_kwargs)
                for x in range(0, 65535, (int(65535 / howlong))):
                    bulb.configure(on=True, hue=x, brightness=args.brightness)
                    time.sleep(65535 / howlong / 1000)
                bulb.turn_off()

    elif args.action == "get-xy":
        for name, lt in lights.items():
            bulb_info = lt.get_light()
            print(bulb_info)


    elif args.action in ["id", "identify"]:

        for name, bulb in lights.items():
            print("----IDENTIFYING ----")
            print(f"BULB NAME: {name}")
            print("----IDENTIFYING ----")
            if args.interval is not None:
                interval = float(args.interval)
            else:
                interval = 1.0
            optional_kwargs['interval'] = interval

            try:
                for _ in range(10):
                    bulb.blink(**optional_kwargs)
                    print(".", end="", flush=True)
            except KeyboardInterrupt:
                bulb.turn_on()
    else:
        if args.action in get_color_names():
            for name, bulb in targs.items():
                loader = LightThreadLoader(bulb.set_color, args.action, **optional_kwargs)
                loader.start()
            wait_for_join()
        else:
            print(f"{args.action} is unknown to this script.")
