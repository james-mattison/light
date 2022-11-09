#!/usr/bin/env python3 
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GObject

import light

bulbs = light.get_lights()

class LightControlWindow(Gtk.Window):
    brightness = 255
    saturation = 255
    hue = None

    def on_on_clicked(self, button):
        for name, button in self.checks.items():
            if button.get_active():
                print(button.get_label())
                bulbs[button.get_label()]._set_state(True, self.saturation, self.brightness, hue=self.hue)

    def on_off_clicked(self, button):
        for name, button in self.checks.items():
            if button.get_active():
                bulbs[button.get_label()]._set_state(False, self.saturation, self.brightness, hue=self.hue)

    def on_blink_clicked(self, button):
        for name, button in self.checks.items():
            if button.get_active():
                bulbs[button.get_label()].blink(brightness=self.brightness, saturation=self.saturation)

    def on_fade_clicked(self, button):
        for name, button in self.checks.items():
            if button.get_active():
                bulbs[button.get_label()].color_cycle(brightness=self.brightness, saturation=self.saturation,
                                                      hue=self.hue)

    def on_info_clicked(self, button):
        ...

    def _on_brightness_changed(self, widget):
        self.brightness = widget.get_value_as_int()
        print(f"Bri: {self.brightness}")

    def _on_saturation_changed(self, widget):
        self.saturation = widget.get_value_as_int()
        print(f"Sat: {self.saturation}")

    def _on_color_changed(self, widget):
        iter = widget.get_active_iter()
        if iter is not None:
            model = widget.get_model()
            color = light.BASE_COLORS[model[iter][0]]
            self.hue = color

    def _populate_lights(self):
        lights = light.get_lights()

        grid = Gtk.Grid()
        grid.set_row_spacing(5)
        grid.set_column_spacing(5)

        checks = {}
        row = 0
        col = 0

        for i, (name, bulb) in enumerate(lights.items()):
            chk = Gtk.CheckButton(label=name)
            checks[name] = chk
            if i % 3 == 0:
                col += 1
                row = 0
            grid.attach(chk, row, col, 1, 1)
            row += 1

        return grid, checks

    def _populate_actions(self):
        actions = {
            "On": self.on_on_clicked,
            "Off": self.on_off_clicked,
            "Blink": self.on_blink_clicked,
            "Fade": self.on_fade_clicked,
            "Info": self.on_info_clicked
        }

        btn_box = Gtk.Box(spacing = 10)

        buttons = {}

        for action, callback in actions.items():
            button = Gtk.Button(label=action)
            button.connect('clicked', callback)
            buttons[action] = button
            btn_box.pack_start(button, False, False, 0)

        return btn_box, buttons

    def _populate_sliders(self):
        sliders = [
            "Brightness",
            "Saturation"
        ]

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        bri_adjustment = Gtk.Adjustment(upper=255, step_increment=1, page_increment=10)
        sat_adjustment = Gtk.Adjustment(upper=255, step_increment=1, page_increment=10)

        bri_box = Gtk.Box()
        bri_label = Gtk.Label(label="Brightnesss")
        bri_spin = Gtk.SpinButton()
        bri_spin.set_adjustment(bri_adjustment)
        bri_spin.connect('value-changed', self._on_brightness_changed)
        bri_box.pack_start(bri_label, True, False, 0)
        bri_box.pack_start(bri_spin, False, False, 0)

        sat_box = Gtk.Box()
        sat_label = Gtk.Label(label="Saturation")
        sat_spin = Gtk.SpinButton()
        sat_spin.set_adjustment(sat_adjustment)
        sat_spin.connect('value-changed', self._on_saturation_changed)
        sat_box.pack_start(sat_label, False, True, 0)
        sat_box.pack_start(sat_spin, False, False, 0)

        hue_box = Gtk.Box()
        hue_label = Gtk.Label(label="Color")
        color_combo = Gtk.ComboBoxText()
        for lt, hue in light.BASE_COLORS.items():
            color_combo.append_text(lt)

        color_combo.connect('changed', self._on_color_changed)
        color_combo.set_entry_text_column(0)
        hue_box.pack_start(hue_label, False, False, 0)
        hue_box.pack_start(color_combo, False, False, 0)

        box.pack_start(bri_box, False, False, 0)
        box.pack_start(sat_box, False, False, 0)
        box.pack_start(hue_box, False, False, 0)

        return box

    def __init__(self):
        Gtk.Window.__init__(self)
        self.set_title("Grid")
        self.set_default_size(640, 480)
        self.connect('destroy', Gtk.main_quit)

        self.box = Gtk.Box(spacing=1, orientation=Gtk.Orientation.VERTICAL)

        self.check_grid, self.checks = self._populate_lights()
        self.action_grid, self.action_buttons = self._populate_actions()
        self.sliders_grid = self._populate_sliders()

        self.box.pack_start(self.check_grid, True, True, 0)
        self.box.pack_start(self.action_grid, True, True, 0)
        self.box.pack_start(self.sliders_grid, True, True, 0)
        self.add(self.box)

win = LightControlWindow()
win.show_all()
Gtk.main()
