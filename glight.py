import gi
import light
import threading
import atexit

gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GObject


class GladeFileLoader:

    def __init__(self):
        self.builder = Gtk.Builder()
        self.builder.add_from_file("glight.glade")

    def __getitem__(self, item):
        return self.builder.get_object(item)


loader = GladeFileLoader()


class ConfigStore:

    hue = 0
    brightness = 0
    saturation = 0
    poisoned = False
    threads = {}

    @staticmethod
    def get():
        return {"brightness": ConfigStore.brightness,
                "saturation": ConfigStore.saturation,
                "hue": ConfigStore.hue
                }

    @staticmethod
    def load_thread(name, thread):
        if name in ConfigStore.threads:
            del ConfigStore.threads[name]
        ConfigStore.threads[name] = thread

    @staticmethod
    def shutdown_threads():
        ConfigStore.poisoned = True

class LightPanel:

    def __init__(self):
        self.lights = light.get_lights()
        self.grid = loader['gridLights']
        self._packed = []
        self.pack_box()

    def pack_box(self):
        if len(self._packed) != 0:
            for ob in self._packed:
                self.grid.remove(ob)

        col = 0
        row = 0
        for i, (name, bulb) in enumerate(self.lights.items()):
            check = Gtk.CheckButton(label = name)
            if i % 3 == 0:
                col += 1
                row = 0
            self.grid.attach(check, row, col, 1, 1)
            row += 1
            if not check in self._packed:
                self._packed.append(check)
        return self.grid

    def get_packed(self):
        return self._packed

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
        colors = light.get_color_names()

        self.combo = loader['comboColors']
        if not self.packed:
            for color, hue in light.BASE_COLORS.items():
                self.combo.append_text(color)
        self.combo.set_entry_text_column(0)
        self.packed = True

        self.combo.connect("changed", self._on_color_changed)
        self.brightness_spinner = loader['spinBrightness']
        self.brightness_spinner.connect('value-changed', self._on_brightness_changed)

        self.saturation_spinner = loader['spinSaturation']
        self.saturation_spinner.connect('value-changed', self._on_saturation_changed)


class InfoWindow:

    @staticmethod
    def get_color_approximation(hue):
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
                    "color": vals['state'].get('hue') or 0
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
        for check in panel.get_packed():
            if check.get_active():
                name = check.get_label()
                print(f"{name} -> ON")
                panel.lights[name]._set_state(True, saturation=ConfigStore.saturation, brightness=ConfigStore.brightness, hue = ConfigStore.hue)

    def _on_off_clicked(self, button):
        for check in panel.get_packed():
            if check.get_active():
                name = check.get_label()
                print(f"{name} -> ON")
                panel.lights[name]._set_state(False,saturation=ConfigStore.saturation, brightness=ConfigStore.brightness, hue = ConfigStore.hue)

    def _on_blink_clicked(self, button):
        for check in panel.get_packed():
            if check.get_active():
                name = check.get_label()
                print(f"{name} -> ON")
                panel.lights[name].blink(saturation=ConfigStore.saturation, brightness=ConfigStore.brightness, hue = ConfigStore.hue)

    def _on_fade_clicked(self, button):

        def fade(bulb):
            while not ConfigStore.poisoned:
                bulb.color_cycle(brightness=ConfigStore.brightness, saturation=ConfigStore.saturation)

        for check in panel.get_packed():
            if check.get_active():
                thread = threading.Thread(target = fade, args = (panel.lights[check.get_label()],), daemon = True)
                thread.start()
                ConfigStore.load_thread(check.get_label(), thread)
                print(f"Started thread for {check.get_label()}")
                name = check.get_label()
                print(f"{name} -> FADE")

    def _on_info_clicked(self, button):
        for check in panel.get_packed():
            if check.get_active():
                name = check.get_label()
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


    def __init__(self):
        self.win = loader['winMain']
        self.frame = loader['boxMain']
        self.panel = panel
        self.panel.pack_box()
        self.button_panel = ButtonPanel()
        self.spinners = Spinners()

        self.frame.pack_start(self.panel.grid, True, True, 0)

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