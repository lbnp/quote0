#!/usr/bin/env python3
"""Script to generate a PNG image from iCal calendar events and weather forecast, then send it to an API."""

import argparse
import base64
import io
import json
import os
import sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import recurring_ical_events
import requests
from icalendar import Calendar
from PIL import Image, ImageDraw, ImageFont

# Candidate font paths tried in order; first match wins.
_EMOJI_FONT_CANDIDATES = [
    # Linux — NotoEmoji monochrome (fonts-noto or manually installed)
    "/usr/share/fonts/truetype/noto/NotoEmoji-Regular.ttf",
    "/usr/share/fonts/noto/NotoEmoji-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoEmoji[wght].ttf",
    # Ubuntu/Debian — Symbola (fonts-symbola package, fallback)
    "/usr/share/fonts/truetype/ancient-scripts/Symbola_hint.ttf",
    # macOS — NotoEmoji[wght].ttf (current monochrome outline font)
    os.path.expanduser("~/Library/Fonts/NotoEmoji[wght].ttf"),
    "/Library/Fonts/NotoEmoji[wght].ttf",
    # macOS legacy filename
    os.path.expanduser("~/Library/Fonts/NotoEmoji-Regular.ttf"),
    "/Library/Fonts/NotoEmoji-Regular.ttf",
    # Windows built-in
    "C:/Windows/Fonts/seguiemj.ttf",
    "C:/Windows/Fonts/NotoEmoji[wght].ttf",
    "C:/Windows/Fonts/NotoEmoji-Regular.ttf",
]

_JP_FONT_CANDIDATES = [
    # macOS built-in (Hiragino Sans) — W6 for better legibility on e-ink
    "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
    "/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
    "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
    "/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
    # Windows built-in
    "C:/Windows/Fonts/meiryo.ttc",
    # Linux — Black (heaviest) > Bold > Regular for best e-ink legibility
    # Black weight requires fonts-noto-cjk-extra (Ubuntu/Debian) or equivalent
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Black.ttc",      # Ubuntu/Debian
    "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Black.ttc",    # Fedora/RHEL
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Black.ttc",           # Arch
    # NotoSansJP (Japan-only subset, fonts-noto-cjk or noto-fonts-cjk package)
    "/usr/share/fonts/truetype/noto/NotoSansJP-Bold.ttf",        # Ubuntu/Debian
    "/usr/share/fonts/opentype/noto/NotoSansJP-Bold.otf",        # Ubuntu/Debian alt
    "/usr/share/fonts/google-noto/NotoSansJP-Bold.ttf",          # Fedora/RHEL
    "/usr/share/fonts/noto/NotoSansJP-Bold.ttf",                 # Arch
    # Bold weight (fonts-noto-cjk package)
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",       # Ubuntu/Debian
    "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Bold.ttc",     # Fedora/RHEL
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc",            # Arch
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",    # Ubuntu/Debian fallback
    "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc",  # Fedora/RHEL fallback
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",         # Arch fallback
]


def _load_font(candidates, size, debug=False):
    for path in candidates:
        try:
            font = ImageFont.truetype(path, size)
            if debug:
                print(f"  [font] loaded: {path}", file=sys.stderr)
            return font
        except Exception as e:
            if debug:
                print(f"  [font] failed {path}: {e}", file=sys.stderr)
            continue
    return None


# Weather code -> emoji mapping
WEATHER_EMOJI = {
    0: "☀️", 1: "☀️",  # Clear
    2: "⛅", 3: "☁️",  # Cloudy
    45: "🌫️", 48: "🌫️",  # Fog
    51: "🌦️", 53: "🌦️", 55: "🌧️",  # Drizzle
    56: "🌧️", 57: "🌧️",  # Freezing drizzle
    61: "🌧️", 63: "🌧️", 65: "🌧️",  # Rain
    66: "🌧️", 67: "🌧️",  # Freezing rain
    71: "🌨️", 73: "🌨️", 75: "🌨️",  # Snow
    77: "🌨️",  # Snow grains
    80: "🌦️", 81: "🌧️", 82: "🌧️",  # Rain showers
    85: "🌨️", 86: "🌨️",  # Snow showers
    95: "⛈️", 96: "⛈️", 99: "⛈️",  # Thunderstorm
}

# Weather code -> display text (Japanese)
WEATHER_TEXT = {
    0: "晴れ", 1: "晴れ",
    2: "曇り晴れ", 3: "曇り",
    45: "霧", 48: "霧",
    51: "霧雨弱", 53: "霧雨", 55: "霧雨強",
    56: "凍雨弱", 57: "凍雨強",
    61: "雨弱", 63: "雨", 65: "雨強",
    66: "凍雨弱", 67: "凍雨強",
    71: "雪弱", 73: "雪", 75: "雪強",
    77: "雪粒",
    80: "驟雨弱", 81: "驟雨", 82: "驟雨強",
    85: "驟雪弱", 86: "驟雪強",
    95: "雷雨", 96: "雷雨ひょう", 99: "雷雨強",
}


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Generate a PNG image from iCal calendar events and weather forecast, then send it to an API"
    )
    parser.add_argument(
        "--ical-url",
        type=str,
        help="Google Calendar iCal URL"
    )
    parser.add_argument(
        "--device-id",
        type=str,
        help="Device unique ID"
    )
    parser.add_argument(
        "--api-key",
        type=str,
        help="API key"
    )
    parser.add_argument(
        "--timezone",
        type=str,
        help="Timezone name, e.g. Asia/Tokyo (default: Asia/Tokyo)"
    )
    parser.add_argument(
        "--config",
        type=str,
        default="config.json",
        help="Path to JSON config file (default: config.json)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build the image but do not send it to the device"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Dump raw iCal response and parsed events to stdout"
    )
    return parser.parse_args()


def load_config(path):
    """Load settings from a JSON config file. Returns an empty dict if the file doesn't exist."""
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except Exception as e:
        print(f"Warning: could not read config file {path!r}: {e}", file=sys.stderr)
        return {}


def get_calendar_events(ical_url, tz, debug=False):
    """Fetch calendar events from an iCal URL, including recurring events."""
    try:
        response = requests.get(ical_url, timeout=10)
        response.raise_for_status()
        ical_data = response.content
    except requests.RequestException as e:
        print(f"Failed to fetch calendar: {e}", file=sys.stderr)
        return []

    if debug:
        print("\n========== iCal Raw Response ==========")
        print(f"Status: {response.status_code}")
        print(f"Content-Type: {response.headers.get('Content-Type', 'unknown')}")
        print(f"Length: {len(ical_data)} bytes")
        print("-------- Body (first 2000 chars) --------")
        print(ical_data[:2000].decode("utf-8", errors="replace"))
        if len(ical_data) > 2000:
            print(f"... ({len(ical_data) - 2000} more bytes)")
        print("=======================================\n")

    try:
        cal = Calendar.from_ical(ical_data)
    except Exception as e:
        print(f"Failed to parse iCal data: {e}", file=sys.stderr)
        return []

    today = datetime.now(tz=tz).replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    end_date = today + timedelta(days=90)

    try:
        occurrences = recurring_ical_events.of(cal).between(today, end_date)
    except Exception as e:
        print(f"Failed to expand recurring events: {e}", file=sys.stderr)
        return []

    events = []
    for component in occurrences:
        if component.name != "VEVENT":
            continue
        summary = str(component.get("SUMMARY", "(無題)"))
        dtstart_prop = component.get("DTSTART")
        if not dtstart_prop:
            continue
        dt = dtstart_prop.dt
        if isinstance(dt, date) and not isinstance(dt, datetime):
            dt = datetime(dt.year, dt.month, dt.day)
        elif dt.tzinfo is not None:
            dt = dt.astimezone(tz).replace(tzinfo=None)
        events.append({"summary": summary, "dtstart": dt})

    events.sort(key=lambda e: e["dtstart"])

    if debug:
        print(f"Parsed {len(events)} upcoming VEVENT(s) (incl. recurrences):")
        for i, ev in enumerate(events):
            print(f"  [{i}] dtstart={ev.get('dtstart')} summary={ev.get('summary')!r}")
        print()

    return events


def get_weather(latitude=35.6762, longitude=139.6503, days=3, timezone="Asia/Tokyo"):
    """Fetch weather forecast data from the Open-Meteo API."""
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "daily": "weather_code,temperature_2m_max,temperature_2m_min",
        "forecast_days": days,
        "timezone": timezone,
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        return data.get("daily", {})
    except requests.RequestException as e:
        print(f"Failed to fetch weather data: {e}", file=sys.stderr)
        return {}


def generate_image(events, weather_data, debug=False):
    """Generate a PNG image from calendar events and weather data."""
    width, height = 296, 152

    # Create a white-background image
    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)

    # Load fonts
    emoji_font = _load_font(_EMOJI_FONT_CANDIDATES, 14, debug=debug)
    if emoji_font is None:
        tried = "\n  ".join(_EMOJI_FONT_CANDIDATES)
        print(f"Warning: no emoji font found. Paths tried:\n  {tried}", file=sys.stderr)

    jp_font = _load_font(_JP_FONT_CANDIDATES, 11, debug=debug)
    if jp_font is None:
        jp_font = ImageFont.load_default()
        tried = "\n  ".join(_JP_FONT_CANDIDATES)
        print(f"Warning: no Japanese font found, using default. Paths tried:\n  {tried}", file=sys.stderr)
    jp_font_bold = _load_font(_JP_FONT_CANDIDATES, 12, debug=debug) or jp_font

    # Black
    black = (0, 0, 0)

    # Starting draw position
    y_pos = 4

    # Header row
    header = "スケジュール                 天気予報"
    try:
        draw.text((4, y_pos), header, font=jp_font_bold, fill=black)
        y_pos += 16
    except Exception:
        y_pos += 14

    # Divider line
    draw.line([(4, y_pos), (width - 4, y_pos)], fill=black, width=1)
    y_pos += 4

    # Right panel: 3-day weather forecast
    daily = weather_data
    weather_x = 150  # Right panel position
    weather_y = 20   # Below the header divider

    if daily and "time" in daily:
        for i in range(min(3, len(daily["time"]))):
            date_str = daily["time"][i]
            try:
                date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                display_date = f"{date_obj.month}/{date_obj.day}({date_obj.strftime('%a')})"
            except ValueError:
                display_date = date_str

            weather_code = daily["weather_code"][i] if i < len(daily["weather_code"]) else 3
            emoji = WEATHER_EMOJI.get(weather_code, "☁️")
            weather_name = WEATHER_TEXT.get(weather_code, "不明")

            max_temp = daily["temperature_2m_max"][i] if i < len(daily["temperature_2m_max"]) else "?"
            min_temp = daily["temperature_2m_min"][i] if i < len(daily["temperature_2m_min"]) else "?"

            # Draw weather info
            try:
                # Emoji icon
                if emoji_font:
                    draw.text((weather_x, weather_y), emoji, font=emoji_font, fill=black)
                    # Measure emoji width to offset the text start
                    try:
                        emoji_bbox = draw.textbbox((0, 0), emoji, font=emoji_font)
                        text_start_x = weather_x + int((emoji_bbox[2] - emoji_bbox[0]) * 0.6) + 2
                    except Exception:
                        text_start_x = weather_x + 18
                else:
                    text_start_x = weather_x + 2

                # Date label (to the right of the emoji)
                draw.text((text_start_x, weather_y), display_date, font=jp_font, fill=black)
                weather_y += 16

                # Weather label with temperatures
                weather_line = f"{weather_name} {max_temp}/{min_temp}°C"
                draw.text((weather_x, weather_y), weather_line, font=jp_font, fill=black)
                weather_y += 16
            except Exception as e:
                print(f"Weather rendering error: {e}", file=sys.stderr)

    # Left panel: calendar events (up to 5)
    left_x = 4
    left_y_start = 20  # Aligned with the weather panel

    # Render upcoming events (up to 5)
    event_count = 0
    y_pos = left_y_start
    for event in events:
        if event_count >= 5:
            break

        dt_start = event.get("dtstart")
        summary = event.get("summary", "(無題)")

        if dt_start:
            # Format date
            date_str = dt_start.strftime("%m/%d")
            time_str = ""
            if dt_start.hour != 0 or dt_start.minute != 0:
                time_str = dt_start.strftime("%H:%M")

            # Build the display line
            if time_str:
                line = f"{date_str} {time_str} {summary}"
            else:
                line = f"{date_str} {summary}"

            # Word-wrap when line exceeds max width
            max_line_width = 130  # Leave space for the right-side weather panel
            wrapped_lines = []
            current_line = ""

            for char in line:
                test_line = current_line + char
                try:
                    bbox = draw.textbbox((0, 0), test_line, font=jp_font)
                    if bbox[2] - bbox[0] <= max_line_width:
                        current_line = test_line
                    else:
                        if current_line:
                            wrapped_lines.append(current_line)
                        current_line = char
                except Exception:
                    current_line += char

            if current_line:
                wrapped_lines.append(current_line)

            for wrapped_line in wrapped_lines[:2]:  # Up to 2 wrapped lines per event
                if y_pos > height - 10:
                    break
                try:
                    draw.text((left_x, y_pos), wrapped_line, font=jp_font, fill=black)
                except Exception:
                    pass
                y_pos += 13
                if y_pos > height - 10:
                    break

        event_count += 1

    # Convert to 1-bit monochrome for e-ink
    img_mono = img.convert("1", dither=Image.Dither.NONE)

    return img_mono


def send_image(device_id, api_key, image, debug=False):
    """Base64-encode the PNG image and send it to the device API."""
    img_bytes = io.BytesIO()
    image.save(img_bytes, format="PNG")
    img_bytes.seek(0)

    image_b64 = base64.b64encode(img_bytes.read()).decode("utf-8")

    url = f"https://dot.mindreset.tech/api/authV2/open/device/{device_id}/image"

    payload = {
        "image": image_b64,
        "border": 0,
        "ditherType": "NONE",
        "refreshNow": True
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    if debug:
        print("\n========== API Request ==========")
        print(f"POST {url}")
        print("-------- Headers --------")
        for key, value in headers.items():
            print(f"  {key}: {value}")
        print("-------- Body --------")
        print(f'  {{"image": "{image_b64[:100]}...", "border": {payload["border"]}, "ditherType": "{payload["ditherType"]}", "refreshNow": {"true" if payload["refreshNow"] else "false"}}}')
        print("=================================\n")

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)

        if debug:
            print("\n========== API Response ==========")
            print(f"Status: {response.status_code}")
            print("-------- Response Headers --------")
            for key, value in response.headers.items():
                print(f"  {key}: {value}")
            print("-------- Response Body --------")
            try:
                print(f"  {response.json()}")
            except Exception:
                print(f"  {response.text}")
            print("==================================\n")

        response.raise_for_status()
        return response
    except requests.RequestException as e:
        print(f"Failed to send image: {e}", file=sys.stderr)
        return None


def main():
    args = parse_args()
    config = load_config(args.config)

    interactive = sys.stdin.isatty()

    def resolve(value, env_key, config_key, prompt):
        result = value or os.environ.get(env_key) or config.get(config_key)
        if not result:
            if interactive:
                result = input(f"{prompt}: ").strip()
            if not result:
                print(
                    f"Error: {prompt} is required. "
                    f"Use --{prompt.lower().replace(' ', '-')}, "
                    f"{env_key} env var, or config.json.",
                    file=sys.stderr,
                )
                sys.exit(1)
        return result

    ical_url = resolve(args.ical_url, "ICAL_URL", "ical_url", "iCal URL")
    device_id = resolve(args.device_id, "DEVICE_ID", "device_id", "Device ID")
    api_key = resolve(args.api_key, "API_KEY", "api_key", "API Key")

    tz_name = args.timezone or os.environ.get("TIMEZONE") or config.get("timezone", "Asia/Tokyo")
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        print(f"Error: unknown timezone {tz_name!r}.", file=sys.stderr)
        sys.exit(1)

    events = get_calendar_events(ical_url, tz=tz, debug=args.debug)
    weather_data = get_weather(timezone=tz_name)
    image = generate_image(events, weather_data, debug=args.debug)

    if args.debug or args.dry_run:
        image.save("output.png")
        print("Image saved: output.png")

    if args.dry_run:
        return

    result = send_image(device_id, api_key, image, debug=args.debug)

    if not result:
        print("Failed to send image.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
