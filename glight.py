#!/usr/bin/env python3
import gi
import light
import os
import subprocess
import atexit


"""
glight: a GTK interface for the light.py library.
        This provides a graphical interface to control the lights.
        See the img/ folder for screenshots.
"""

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk

Gdk.threads_init()

bashrc = os.path.abspath(os.path.join(os.path.expanduser("~"), ".bashrc"))
subprocess.run(f"source {bashrc}", shell = True)
print(f"Sourced bashrc.")


class GladeFileLoader:
    """Load the glight.glade file"""

    def __init__(self):
        self.builder = Gtk.Builder()
        self.builder.add_from_file("glight.glade")

    def __getitem__(self, item):
        return self.builder.get_object(item)


loader = GladeFileLoader()


class ConfigStore:
    """
    ConfigStore: class to store the settings in the spinners in the interface.
    This class contains the values as they currently are shown in the interface.

    """
    hue = 0
    brightness = 0
    saturation = 0
    poisoned = False
    threads = {}

    @staticmethod
    def get() -> dict:
        """
        Return brightness, saturation, and hue in a dictionary. This refers to the
        values in the SpinBoxes at the present moment, not  the values that are currently
        running on any light.
        """
        return {
            "brightness": ConfigStore.brightness,
            "saturation": ConfigStore.saturation,
            "hue": ConfigStore.hue
        }

    @staticmethod
    def load_thread(name, thread):
        """
        :return:
        """
        if name in ConfigStore.threads:
            del ConfigStore.threads[name]
        ConfigStore.threads[name] = thread

    @staticmethod
    def shutdown_threads():
        ConfigStore.poisoned = True


class LightPanel:
    _objects = {}

    def __init__(self):
        self.rooms = {}
        self.grid = loader['gridRooms']
        self.lights = {}
        self._frames = []
        self._checkboxes = {}
        self.pack_box()

    def update_check_colors(self):
        self.rooms = light.get_lights_by_room()
        for name, bulbs in self.rooms.items():
            for bulb in bulbs:
                # if bulb.name != name:
                #     continue
                # print(f"Parsing bulb: {bulb.name}")
                if bulb.get_state() is True:
                    self._checkboxes[bulb.name].modify_fg(Gtk.StateType.NORMAL, Gdk.color_parse("blue"))
                else:
                    self._checkboxes[bulb.name].modify_fg(Gtk.StateType.NORMAL, Gdk.color_parse("red"))

    def pack_box(self):
        """
        Pack the checkboxes into the main window. Populates the checkboxes
        array that is used to deterine the color of the text on the box.
        """
        if len(self._frames) != 0:
            for ob in self._frames:
                self.grid.remove(ob)

        self._checkboxes = {}

        col = 0
        row = 0
        self.rooms = light.get_lights_by_room()

        for i, (name, room) in enumerate(self.rooms.items()):

            label = Gtk.Label(xalign = 0)
            html_safe = name.replace(' ', '')
            label.set_markup(f"<u><big><b><a href='#{html_safe}'>{name}:</a></b></big></u>")
            label.connect("activate-link", self._on_link_clicked)

            frame = Gtk.Frame()
            box = Gtk.Box(orientation = Gtk.Orientation.VERTICAL, expand = True)
            self._frames.append(frame)

            for bulb in room:
                if not name in self._checkboxes:
                    check = Gtk.CheckButton(label = bulb.name)
                    self._checkboxes[bulb.name.replace(' ', '')] = check
                else:
                    check = self._checkboxes[bulb.name.replace(' ', '')]

                if i % 3 == 0:
                    col += 1
                    row = 0

                box.pack_end(check, True, True, 0)

                self.lights[bulb.name] = bulb

            frame.add(box)

            box.set_valign(True)
            box.pack_start(label, True, True, 0)
            self.grid.attach(frame, row, col, 1, 1)
            row += 1
            self._objects[name] = room

        return self.grid

    def _on_link_clicked(self, label, uri):
        target = uri.strip("#")

        room_bulbs = light.get_lights_by_room()
        room_bulbs = {k.replace(' ', ''): v for k, v in room_bulbs.items()}
        # print(room_bulbs)
        for bulb in room_bulbs[target]:
            check = self._checkboxes[bulb.name]
            state = check.get_active()
            check.set_active(not state)
        self.update_check_colors()
        return True

    def get_checkboxes_by_room(self, room):
        return self._checkboxes[room]

    def get_checkboxes(self, checks_only = True):
        boxes = {}
        for light, check in self._checkboxes.items():
            if not light in boxes.keys():
                boxes[light] = []
                boxes[light].append(check)
        if not checks_only:
            return self._checkboxes
        else:
            return boxes

    def get_frames(self):
        return self._frames


panel = LightPanel()


class Spinners:

    def _on_color_changed(self, widget):
        iter = widget.get_active_iter()
        if iter is not None:
            model = widget.get_model()
            color = light.BASE_COLORS[model[iter][0]]
            ConfigStore.hue = color

    def _on_saturation_changed(self, widget):
        saturation = widget.get_value_as_int()
        ConfigStore.saturation = saturation

    def _on_brightness_changed(self, widget):
        brightness = widget.get_value_as_int()
        ConfigStore.brightness = brightness

    packed = False

    def __init__(self):
        self.combo = loader['comboColors']
        if not self.packed:
            for color, hue in light.BASE_COLORS.items():
                self.combo.append_text(color)
        self.combo.set_entry_text_column(0)
        self.combo.set_active(0)
        self.packed = True

        self.combo.connect("changed", self._on_color_changed)
        self.brightness_spinner = loader['spinBrightness']
        self.brightness_spinner.set_range(0, 255)
        self.brightness_spinner.connect('value-changed', self._on_brightness_changed)

        self.saturation_spinner = loader['spinSaturation']
        self.saturation_spinner.connect('value-changed', self._on_saturation_changed)


class InfoWindow:

    @staticmethod
    def get_color_approximation(hue):
        if isinstance(hue, str):
            return hue
        a = []
        for val in light.BASE_COLORS.values():
            a.append(abs(hue - val))
        return list(light.BASE_COLORS.keys())[a.index(min(a))]

    @staticmethod
    def hide(window, event):
        print(f"Hiding info window.")
        window.hide()
        return True

    def __init__(self, bulb_name: str):
        self.cnf = None
        self.bulb_name = bulb_name
        self.window = loader['winInfo']
        self.window.connect("delete-event", self.hide)
        self.name_label = loader['lblBulbName']
        self.name_label.set_text(bulb_name)
        self.capabilities_label = loader['lblCapabilities']
        self.state_label = loader['lblState']
        self.saturation_label = loader['lblSaturation']
        self.brightness_label = loader['lblBrightness']
        self.color_label = loader['lblColor']

    def set_labels(self):
        self.cnf = self.get_bulb_dict(self.bulb_name)
        state = "ON" if self.cnf['state'] == True else "OFF"
        self.state_label.set_text(state)
        self.saturation_label.set_text(str(self.cnf['saturation']))
        self.brightness_label.set_text(str(self.cnf['brightness']))
        self.capabilities_label.set_text(str(self.cnf['capabilities']))
        try:
            color = light.BASE_COLORS[self.cnf['color']]
        except:
            color = "(approx) " + self.get_color_approximation(self.cnf['color'])
        self.color_label.set_text(color)

    def get_bulb_dict(self, name):
        lights = light.make_request("lights")
        for i, vals in lights.items():
            if vals['name'] == name:
                state = {
                    "state": vals['state']['on'],
                    "brightness": vals['state']['bri'],
                    "saturation": vals['state'].get('sat'),
                    "color": vals['state'].get('hue') or "",
                    "capabilities": "Color" if vals['state'].get("ct") else "White Only"
                }
                return state

    def show(self):
        self.window.show()


class ButtonPanel:

    @staticmethod
    def get_configs():
        cnf = {
            "brightness": ConfigStore.brightness,
            "saturation": ConfigStore.saturation,
            "hue": ConfigStore.hue
        }
        return cnf

    def _on_on_clicked(self, button):
        for name, checks in panel.get_checkboxes().items():
            for check in checks:
                if check.get_active():
                    name = check.get_label()
                    print(
                        f"{name} -> ON (Saturation: {ConfigStore.saturation} Brightness: {ConfigStore.brightness} Hue: {ConfigStore.hue}")
                    panel.lights[name]._set_state(True, saturation = ConfigStore.saturation,
                                                  brightness = ConfigStore.brightness, hue = ConfigStore.hue)
                    check.modify_fg(Gtk.StateType.NORMAL, Gdk.color_parse("red"))
        panel.update_check_colors()

    def _on_off_clicked(self, button):
        for name, checks in panel.get_checkboxes().items():
            for check in checks:
                if check.get_active():
                    name = check.get_label()
                    print(f"{name} -> OFF")
                    panel.lights[name]._set_state(False, saturation = ConfigStore.saturation,
                                                  brightness = ConfigStore.brightness, hue = ConfigStore.hue)
                    check.modify_fg(Gtk.StateType.NORMAL, Gdk.color_parse("red"))

        panel.update_check_colors()

    def _on_blink_clicked(self, button):
        for _, checks in panel.get_checkboxes().items():
            for check in checks:
                if check.get_active():
                    name = check.get_label()
                    print(f"{name} -> BLINK")
                    forever = loader['btnForever'].get_active()
                    print(panel.lights[name].name)
                    thread = light.LightThreadLoader(panel.lights[name].blink,
                                                     kwargs = {"brightness": ConfigStore.brightness,
                                                               "saturation": ConfigStore.saturation,
                                                               "hue": ConfigStore.hue}, forever = forever)
                    panel.lights[name].blink(saturation = ConfigStore.saturation, brightness = ConfigStore.brightness,
                                             hue = ConfigStore.hue)

    def _on_fade_clicked(self, button):

        def fade(bulb):
            while not ConfigStore.poisoned:
                bulb.color_cycle(brightness = ConfigStore.brightness, saturation = ConfigStore.saturation)

        for _, checks in panel.get_checkboxes():
            for check in checks:
                if check.get_active():
                    #
                    # thread = threading.Thread(target=fade, args=(panel.lights[check.get_label()],), daemon=True)
                    # thread.start()
                    # ConfigStore.load_thread(check.get_label(), thread)
                    forever = loader['btnForever'].get_active()
                    thread = light.LightThreadLoader(check.get_label(), forever = forever)
                    thread.start()
                    print(f"Started thread for {check.get_label()}")
                    name = check.get_label()
                    print(f"{name} -> FADE")

    def _on_info_clicked(self, button):
        for name, check in panel.get_checkboxes().items():
            if check[0].get_active():
                name = check[0].get_label()
                info_window = InfoWindow(name)
                info_window.set_labels()
                info_window.show()
                break

    def __init__(self):
        self.on_button = loader['btnOn']
        self.on_button.connect("clicked", self._on_on_clicked)
        self.off_button = loader['btnOff']
        self.off_button.connect("clicked", self._on_off_clicked)
        self.blink_button = loader['btnBlink']
        self.blink_button.connect("clicked", self._on_blink_clicked)
        self.fade_button = loader['btnFade']
        self.fade_button.connect("clicked", self._on_fade_clicked)
        self.info_button = loader['btnInfo']
        self.info_button.connect("clicked", self._on_info_clicked)


class MainWindow:
    _packed = False

    def __init__(self):
        self.win = loader['winMain']
        self.win.set_keep_above(True)
        self.win.connect("destroy", Gtk.main_quit)
        # self.win.connect("NSApplicationBlockTermination", Gtk.main_quit)

        self.panel = panel
        self.panel.update_check_colors()
        self.frame = loader['boxMain']
        self.button_panel = ButtonPanel()
        self.spinners = Spinners()

        if not self._packed:
            self.frame.pack_start(self.panel.grid, True, True, 0)
            self._packed = True

    def start(self):
        self.win.show_all()
        Gtk.main()


if __name__ == '__main__':
    atexit.register(ConfigStore.shutdown_threads)
    ConfigStore.hue = light.BASE_COLORS['green']
    ConfigStore.saturation = 255
    ConfigStore.brightness = 255
    win = MainWindow()
    win.start()
