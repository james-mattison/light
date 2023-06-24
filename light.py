#!/usr/bin/env python3
import subprocess
import requests
import threading
import argparse
import json
import time
import os

import light

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

parser = argparse.ArgumentParser(add_help = False)
parser.add_argument("action", action = "store")
parser.add_argument("subtarg", action = "store", nargs = "?")
parser.add_argument("-H", "--help", action = "help")
parser.add_argument("-t", "--targets", action = "store", nargs = "*", help = "A list of bulbs to target.")
parser.add_argument("-I", "--interval", action = "store", default = 0, type = float,
                    help = "The interval at which to blink")
parser.add_argument("-i", "--iterations", action = "store", default = 0, type = int)
parser.add_argument("-b", "--brightness", action = "store", default = None, type = int)
parser.add_argument("-h", "--hue", action = "store", default = None, type = int)
parser.add_argument("-s", "--saturation", action = "store", default = None)
parser.add_argument("-v", "--verbose", action = "store_true", default = False)
HELP_ITEMS = [
    ("get-lights", "Get a list of connected lights."),
    ("get-colors", "Get a list of valid colors"),
    ("on", "Turn light(s) on"),
    ("off", "Turn light(s) off"),
    ("fade", "Fade light(s) colors")
]


class Verbose:
    _verbose = False

    @property
    def verbose(self):
        return self._verbose

    @verbose.setter
    def verbose(self, val: bool):
        self._verbose = val
    

USER = os.environ['LIGHT_USER']
UNIT = os.environ['LIGHT_UNIT']


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

def make_request(*endpoints, kind = "get", body = None):
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
        return 
    
    req = kinds[kind](targ, verify = False, json = body)

    return req.json()

def get_color_names():
    names = []
    for color in BASE_COLORS.keys():
        names.append(color)
    return names


lights = make_request("lights")


class LightThreadLoader:

    threads = {}

    @staticmethod
    def terminate_thread(bulb_name):
        if bulb_name in LightThreadLoader.threads.keys():
            del LightThreadLoader.threads[bulb_name]



    def __init__(self, target, *args, **kwargs):
        self.poisoned = False
        self.target = target
        self.args = args
        self.kwargs = kwargs
        self.forever = kwargs.pop('forever')
        self.thread = self._load_thread()

    def _load_thread(self):
        def foreverer(callback, *args, **kwargs):
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
            target = cb,
            args = (bulb.color_cycle, ),
            kwargs = self.kwargs,
            daemon = True)
        self.threads[self.target] = thread
        return thread

    def start(self):
        print("- Thread started")
        self.thread.start()

    def poison(self):
        print(f"Poisoning thread for {self.target}")
        self.poisoned = True
        while self.thread.is_alive():
            print("Waiting for thread shutdown...")
            time.sleep(0.1)
        del self


class _Color:

    def __init__(self, color: str):
        self.color = None

    def build_color_map(self):
        ...


class _Light:

    _lights = {}

    def __init__(self, name: str):
        self.name = name

        self.light_index, self.light = self.get_light()

        self._saturation = None
        self._brightness = None
        self._hue = None

    def get_light(self):
        lts = make_request("lights")

        for idx, ob in lts.items():
            if ob['name'] == self.name:
                return idx, ob

    def configure(self, *args, **kwargs):
        return self._set_state(*args, **kwargs)

    def _set_state(self,
        on: bool = False, 
        saturation = 255, 
        brightness = 255,
        hue = None,
        forever = False):

        left = ['saturation', 'brightness', 'hue']
        right = [ saturation, brightness, hue]
        attribs = dict(zip(left, right))

        for k, v in attribs.items():
            if v:
                setattr(self, k, v)

        body = {}
        body['sat'] = saturation
        body['bri'] = brightness
        if hue is not None:
            body['hue'] = hue
        body['on'] = on

        make_request("lights",
            self.light_index, 
            "state", 
            body = body,
            kind = "put")

    def turn_off(self):
        self._set_state(False)

    def turn_on(self, **kwargs):
        self._set_state(True, **kwargs)

    def blink(self,  **kwargs):
        interval = float(kwargs.get('interval', 1.0))
        if interval is None:
            interval = 1.0

        self._set_state(False)
        time.sleep(interval / 2)
        self._set_state(True)
        time.sleep(interval / 2)

    def set_color(self, color: str, **kwargs):
        clr = None
        if color in BASE_COLORS.keys():
            clr = BASE_COLORS[color]
            self._set_state(True, hue = clr, **kwargs)
        else:
            print(f"Color: {color} not in {list(BASE_COLORS.keys())}")

    def color_cycle(self, interval: int = None, step: int = None, **kwargs):
        if not step:
            step = 200
        else:
            step = int(step)
        if not interval: 
            interval = 1.0

        brightness = kwargs.get('brightness') or 10


        while True:
            for i in range(0, 64000, int(step)):
                self.configure(True, hue = i, brightness = brightness)
                
            for i in range(0, 64000, 0 - int(step)):
                self.configure(True, hue = i, brightness = brightness)

Light = _Light

def get_lights(permit_unreachable: bool = False):
    lights = {}
    lts = make_request("lights")
    for idx, lt in lts.items():
        if not permit_unreachable:
            if lt['state']['reachable']:
                lights[lt['name']] = _Light(lt['name'])
        else:
            lights[lt['name']] = _Light(lt['name'])
    return lights

def map_colors():
    map = {}

    light = _Light('Office')

    for x in range(0, 64000, 4000):
        light.configure(True, hue = x)
        clr = input(f"[x] Color name: ")
        map[clr] = x

    f = open("colors.json", "w")
    json.dump(map, f, indent = 4)
    f.close()

    return map


def wait_for_join():
    threads = [ thread for thread in LightThreadLoader.threads if thread.is_alive()]
    if not threads:
        print("All threads terminated.")
        quit(0)
    else:
        print(f"Waiting for {len(threads)} to join...")
        time.sleep(1)
        wait_for_join()

if __name__ == "__main__":
    args = parser.parse_args()
    if args.verbose:
        Verbose.verbose = True

    optional_kwargs = {}
    for kwarg in [ 'brightness', 'saturation', 'hue' ]:
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
                loader = LightThreadLoader(bulb.set_color, args.subtarg, **optional_kwargs, forever = False)
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
            loader = LightThreadLoader(bulb.blink, interval = interval)
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
                    bulb.configure(on = True, hue = x, brightness = args.brightness)
                    time.sleep(65535 / howlong / 1000)
                bulb.turn_off()

    elif args.action == "get-xy":
        for name, lt in lights.items():
            bulb_info = lt.get_light()
            print(bulb_info)

    
    elif args.action in [ "id", "identify" ]:
        
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
                    bulb.blink( **optional_kwargs)
                    print(".", end = "", flush = True)
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
