"""
Weather App — Kivy (Android Compatible)
Install:  pip install kivy requests
Package:  buildozer android debug  (see buildozer.spec)
"""

import threading
import requests
from datetime import datetime
from kivy.app import App
from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.widget import Widget
from kivy.graphics import Color, RoundedRectangle, Rectangle
from kivy.metrics import dp
from kivy.core.window import Window

# ── Colors ─────────────────────────────────────────────────────────────────────
BG_COLOR   = (0.04, 0.09, 0.13, 1)
CARD_COLOR = (0.08, 0.14, 0.23, 1)
ACC_COLOR  = (0.22, 0.74, 0.97, 1)
FG_COLOR   = (0.89, 0.91, 0.94, 1)
DIM_COLOR  = (0.39, 0.45, 0.55, 1)

# ── Config ─────────────────────────────────────────────────────────────────────
REFRESH_SECS = 600
GEO_URL      = "https://geocoding-api.open-meteo.com/v1/search"
WEATHER_URL  = "https://api.open-meteo.com/v1/forecast"

# ── WMO Codes ──────────────────────────────────────────────────────────────────
WMO_CODES = {
    0:  ("Clear Sky",          "☀"),  1:  ("Mainly Clear",       "🌤"),
    2:  ("Partly Cloudy",      "⛅"), 3:  ("Overcast",           "☁"),
    45: ("Foggy",              "🌫"), 48: ("Icy Fog",            "🌫"),
    51: ("Light Drizzle",      "🌦"), 53: ("Drizzle",            "🌦"),
    55: ("Heavy Drizzle",      "🌧"), 61: ("Light Rain",         "🌧"),
    63: ("Rain",               "🌧"), 65: ("Heavy Rain",         "🌧"),
    71: ("Light Snow",         "🌨"), 73: ("Snow",               "❄"),
    75: ("Heavy Snow",         "❄"), 80: ("Showers",            "🌦"),
    81: ("Heavy Showers",      "🌧"), 95: ("Thunderstorm",       "⛈"),
}
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


# ── API ────────────────────────────────────────────────────────────────────────
def geocode(city):
    r = requests.get(GEO_URL, params={"name": city, "count": 1, "language": "en"}, timeout=8)
    r.raise_for_status()
    results = r.json().get("results")
    if not results:
        return None
    loc = results[0]
    return {"name": f"{loc['name']}, {loc.get('country','')}",
            "lat": loc["latitude"], "lon": loc["longitude"],
            "tz": loc.get("timezone", "auto")}


def fetch_weather(lat, lon, tz):
    params = {
        "latitude": lat, "longitude": lon, "timezone": tz,
        "current": ["temperature_2m", "apparent_temperature",
                    "relative_humidity_2m", "wind_speed_10m",
                    "wind_direction_10m", "weather_code", "visibility"],
        "daily": ["weather_code", "temperature_2m_max", "temperature_2m_min"],
        "forecast_days": 7,
    }
    r = requests.get(WEATHER_URL, params=params, timeout=8)
    r.raise_for_status()
    return r.json()


def wind_label(deg):
    return ["N","NE","E","SE","S","SW","W","NW"][round(deg / 45) % 8]


# ── Custom Widgets ─────────────────────────────────────────────────────────────
class Card(BoxLayout):
    """BoxLayout with a rounded dark background."""
    def __init__(self, radius=12, **kwargs):
        super().__init__(**kwargs)
        self._radius = radius
        self.bind(pos=self._draw, size=self._draw)

    def _draw(self, *_):
        self.canvas.before.clear()
        with self.canvas.before:
            Color(*CARD_COLOR)
            RoundedRectangle(pos=self.pos, size=self.size,
                             radius=[self._radius])


class DetailTile(Card):
    def __init__(self, title, **kwargs):
        super().__init__(orientation="vertical", padding=dp(10),
                         spacing=dp(4), **kwargs)
        self.title_lbl = Label(text=title, font_size=dp(11),
                               color=DIM_COLOR, size_hint_y=None, height=dp(18))
        self.value_lbl = Label(text="—", font_size=dp(15), bold=True,
                               color=FG_COLOR, size_hint_y=None, height=dp(22))
        self.add_widget(self.title_lbl)
        self.add_widget(self.value_lbl)


class ForecastCard(Card):
    def __init__(self, **kwargs):
        super().__init__(orientation="vertical", padding=dp(8),
                         spacing=dp(2), **kwargs)
        self.day  = Label(text="",  font_size=dp(11), bold=True, color=DIM_COLOR)
        self.icon = Label(text="",  font_size=dp(22), color=FG_COLOR)
        self.hi   = Label(text="",  font_size=dp(13), bold=True, color=FG_COLOR)
        self.lo   = Label(text="",  font_size=dp(11), color=DIM_COLOR)
        for w in (self.day, self.icon, self.hi, self.lo):
            self.add_widget(w)


# ── Root Layout ────────────────────────────────────────────────────────────────
class WeatherRoot(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(orientation="vertical",
                         padding=dp(14), spacing=dp(10), **kwargs)
        with self.canvas.before:
            Color(*BG_COLOR)
            self._bg = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=lambda *_: setattr(self._bg, 'pos', self.pos),
                  size=lambda *_: setattr(self._bg, 'size', self.size))

        self._loc      = None
        self._refresh  = None

        self._build()

    def _build(self):
        # ── Search bar ────────────────────────────────────────────────────────
        search_row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        self.search_input = TextInput(
            hint_text="Search city…", multiline=False,
            font_size=dp(15), background_color=CARD_COLOR,
            foreground_color=FG_COLOR, hint_text_color=DIM_COLOR,
            cursor_color=ACC_COLOR, padding=[dp(12), dp(10)],
            size_hint_x=0.75)
        self.search_input.bind(on_text_validate=lambda _: self._search())

        search_btn = Button(
            text="Search", font_size=dp(14), bold=True,
            background_color=ACC_COLOR, color=BG_COLOR,
            size_hint_x=0.25)
        search_btn.bind(on_press=lambda _: self._search())

        search_row.add_widget(self.search_input)
        search_row.add_widget(search_btn)
        self.add_widget(search_row)

        # Status
        self.status_lbl = Label(text="Type a city and tap Search",
                                color=DIM_COLOR, font_size=dp(12),
                                size_hint_y=None, height=dp(20))
        self.add_widget(self.status_lbl)

        # ── Hero card ─────────────────────────────────────────────────────────
        hero = Card(orientation="horizontal", size_hint_y=None,
                    height=dp(130), padding=dp(16), spacing=dp(12))

        left = BoxLayout(orientation="vertical", size_hint_x=0.35)
        self.icon_lbl = Label(text="🌡", font_size=dp(56), color=FG_COLOR)
        left.add_widget(self.icon_lbl)
        hero.add_widget(left)

        right = BoxLayout(orientation="vertical", size_hint_x=0.65, spacing=dp(2))
        self.city_lbl = Label(text="Search a city", font_size=dp(15),
                               bold=True, color=FG_COLOR, halign="left",
                               text_size=(Window.width * 0.55, None))
        self.temp_lbl = Label(text="", font_size=dp(42), bold=True,
                               color=(*ACC_COLOR[:3], 1), halign="left")
        self.cond_lbl = Label(text="", font_size=dp(13),
                               color=DIM_COLOR, halign="left")
        for w in (self.city_lbl, self.temp_lbl, self.cond_lbl):
            right.add_widget(w)
        hero.add_widget(right)
        self.add_widget(hero)

        # ── Detail strip ──────────────────────────────────────────────────────
        det = GridLayout(cols=4, size_hint_y=None, height=dp(72), spacing=dp(6))
        self._det = {}
        for key, title in [("hum","💧 Humidity"), ("wind","💨 Wind"),
                            ("feels","🌡 Feels"), ("vis","👁 Vis")]:
            tile = DetailTile(title, size_hint_x=0.25)
            det.add_widget(tile)
            self._det[key] = tile.value_lbl
        self.add_widget(det)

        # ── Forecast label ────────────────────────────────────────────────────
        self.add_widget(Label(text="7-DAY FORECAST", font_size=dp(10),
                              bold=True, color=DIM_COLOR,
                              size_hint_y=None, height=dp(18), halign="left"))

        # ── Forecast row ──────────────────────────────────────────────────────
        fc_row = GridLayout(cols=7, size_hint_y=None, height=dp(100), spacing=dp(4))
        self._fc = []
        for _ in range(7):
            c = ForecastCard(size_hint_x=1/7)
            fc_row.add_widget(c)
            self._fc.append(c)
        self.add_widget(fc_row)

        # ── Updated label ─────────────────────────────────────────────────────
        self.updated_lbl = Label(text="", color=DIM_COLOR, font_size=dp(10),
                                 size_hint_y=None, height=dp(18))
        self.add_widget(self.updated_lbl)

    # ── Search ─────────────────────────────────────────────────────────────────
    def _search(self):
        q = self.search_input.text.strip()
        if not q:
            return
        self._set_status("Searching…")
        threading.Thread(target=self._do_search, args=(q,), daemon=True).start()

    def _do_search(self, q):
        try:
            loc = geocode(q)
            if not loc:
                Clock.schedule_once(lambda _: self._set_status("City not found"))
                return
            self._loc = loc
            self._load()
        except Exception as e:
            Clock.schedule_once(lambda _: self._set_status(f"Error: {e}"))

    # ── Load ───────────────────────────────────────────────────────────────────
    def _load(self):
        self._set_status("Loading…")
        threading.Thread(target=self._do_load, daemon=True).start()

    def _do_load(self):
        try:
            data = fetch_weather(self._loc["lat"], self._loc["lon"], self._loc["tz"])
            Clock.schedule_once(lambda _: self._update(data))
        except Exception as e:
            Clock.schedule_once(lambda _: self._set_status(f"Update error: {e}"))
        finally:
            if self._refresh:
                self._refresh.cancel()
            self._refresh = Clock.schedule_once(lambda _: self._load(), REFRESH_SECS)

    # ── Update ─────────────────────────────────────────────────────────────────
    def _update(self, data):
        cur  = data["current"]
        wmo  = cur.get("weather_code", 0)
        label, emoji = WMO_CODES.get(wmo, ("Unknown", "🌡"))

        temp    = cur.get("temperature_2m", "—")
        feels   = cur.get("apparent_temperature", "—")
        hum     = cur.get("relative_humidity_2m", "—")
        wsp     = cur.get("wind_speed_10m", "—")
        wdg     = cur.get("wind_direction_10m", 0)
        vis_m   = cur.get("visibility")
        vis_str = f"{vis_m/1000:.1f}km" if vis_m else "—"

        self.city_lbl.text = self._loc["name"]
        self.temp_lbl.text = f"{temp}°C"
        self.cond_lbl.text = label
        self.icon_lbl.text = emoji

        self._det["hum"].text   = f"{hum}%"
        self._det["wind"].text  = f"{wsp}\n{wind_label(wdg)}"
        self._det["feels"].text = f"{feels}°C"
        self._det["vis"].text   = vis_str

        daily = data.get("daily", {})
        codes = daily.get("weather_code", [])
        highs = daily.get("temperature_2m_max", [])
        lows  = daily.get("temperature_2m_min", [])
        dates = daily.get("time", [])

        for i, card in enumerate(self._fc):
            if i < len(dates):
                dt       = datetime.strptime(dates[i], "%Y-%m-%d")
                day_name = "Today" if i == 0 else DAYS[dt.weekday()]
                _, em    = WMO_CODES.get(codes[i] if i < len(codes) else 0, ("","🌡"))
                card.day.text  = day_name
                card.icon.text = em
                card.hi.text   = f"{highs[i]}°" if i < len(highs) else "—"
                card.lo.text   = f"{lows[i]}°"  if i < len(lows)  else "—"

        now = datetime.now().strftime("%I:%M %p")
        self.updated_lbl.text = f"Updated: {now}  •  Refreshes every {REFRESH_SECS//60}min"
        self._set_status("✓ Live")

    def _set_status(self, msg):
        self.status_lbl.text = msg


# ── App Entry ──────────────────────────────────────────────────────────────────
class WeatherKivyApp(App):
    def build(self):
        Window.clearcolor = BG_COLOR
        return WeatherRoot()


if __name__ == "__main__":
    WeatherKivyApp().run()
