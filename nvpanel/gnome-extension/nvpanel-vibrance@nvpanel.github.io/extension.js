import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GObject from 'gi://GObject';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

const BUS_NAME = 'io.github.nvpanel.Vibrance';
const OBJ_PATH = '/io/github/nvpanel/Vibrance';
const IFACE = `
<node>
  <interface name="${BUS_NAME}">
    <method name="Set"><arg type="d" direction="in" name="vibrance"/></method>
    <method name="Get"><arg type="d" direction="out" name="vibrance"/></method>
  </interface>
</node>`;

// vibrance in [-1, 1]. Negative: plain desaturation. Positive: boost weighted
// by how unsaturated each pixel is, so already-vivid colours are left alone.
const SHADER = `
uniform sampler2D tex;
uniform float vibrance;
void main() {
  vec4 c = texture2D(tex, cogl_tex_coord_in[0].xy);
  float luma = dot(c.rgb, vec3(0.2126, 0.7152, 0.0722));
  float sat = max(c.r, max(c.g, c.b)) - min(c.r, min(c.g, c.b));
  float amount = vibrance < 0.0 ? vibrance : vibrance * (1.0 - sat) * 2.0;
  c.rgb = clamp(mix(vec3(luma), c.rgb, 1.0 + amount), 0.0, 1.0);
  cogl_color_out = c * cogl_color_in;
}`;

const VibranceEffect = GObject.registerClass(
class VibranceEffect extends Clutter.ShaderEffect {
    _init() {
        super._init();
        this.set_shader_source(SHADER);
        this.set_uniform_value('tex', 0);
        this.setVibrance(0);
    }

    setVibrance(v) {
        // An explicit float GValue is required: GJS would turn an integral JS
        // number such as 1.0 into an int, which a float uniform silently ignores.
        const value = new GObject.Value();
        value.init(GObject.TYPE_FLOAT);
        value.set_float(v);
        this.set_uniform_value('vibrance', value);
        this.queue_repaint();
    }
});

export default class NvpanelVibrance extends Extension {
    enable() {
        this._effect = new VibranceEffect();
        this._value = 0;
        this._dbus = Gio.DBusExportedObject.wrapJSObject(IFACE, this);
        this._dbus.export(Gio.DBus.session, OBJ_PATH);
        this._ownerId = Gio.bus_own_name(
            Gio.BusType.SESSION, BUS_NAME, Gio.BusNameOwnerFlags.NONE, null, null, null);
    }

    disable() {
        if (this._ownerId)
            Gio.bus_unown_name(this._ownerId);
        this._ownerId = 0;
        this._dbus?.unexport();
        this._dbus = null;
        this._detach();
        this._effect = null;
    }

    _detach() {
        if (this._attached) {
            Main.uiGroup.remove_effect(this._effect);
            this._attached = false;
        }
    }

    // D-Bus: Set(d vibrance) with vibrance in [-1, 1]
    Set(v) {
        this._value = Math.max(-1, Math.min(1, v));
        if (this._value === 0) {
            this._detach();
            return;
        }
        this._effect.setVibrance(this._value);
        if (!this._attached) {
            Main.uiGroup.add_effect_with_name('nvpanel-vibrance', this._effect);
            this._attached = true;
        }
    }

    Get() {
        return this._value;
    }
}
