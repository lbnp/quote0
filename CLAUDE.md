# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

A single-file Python utility that generates a 296×152 monochrome PNG image from Google Calendar events and a 3-day weather forecast, then uploads it to an e-ink display device via a REST API (`dot.mindreset.tech`).

## Running the Script

```bash
# Interactive mode (prompts for missing values)
python generate_image.py

# With CLI arguments
python generate_image.py --ical-url <URL> --device-id <ID> --api-key <KEY>

# With environment variables
ICAL_URL=<url> DEVICE_ID=<id> API_KEY=<key> python generate_image.py

# With a config file (default: config.json)
python generate_image.py --config config.json

# Dry run (generate image but do not send to device)
python generate_image.py --dry-run

# Debug mode (dump raw iCal and API request/response to stdout, save output.png)
python generate_image.py --debug
```

Priority order for each parameter: CLI arg → environment variable → config.json → interactive prompt.

No build step, test suite, or linter is configured.

## Dependencies

```bash
pip install -r requirements.txt
```

`requirements.txt` contains: `requests`, `Pillow`, `icalendar`, `recurring-ical-events`.

## Architecture

`generate_image.py` is structured as a linear pipeline inside `main()`:

1. **`parse_args()`** — argparse CLI; supports `--ical-url`, `--device-id`, `--api-key`, `--timezone` (default: `Asia/Tokyo`), `--config` (default: `config.json`), `--dry-run`, `--debug`
2. **`load_config(path)`** — loads settings from a JSON config file (`ical_url`, `device_id`, `api_key`, `timezone`); returns empty dict if file is absent
3. **`get_calendar_events(ical_url, tz, debug=False)`** — fetches and parses iCal from Google Calendar; expands recurring events via `recurring_ical_events`; returns list of `{"summary": str, "dtstart": datetime}` dicts for the next 90 days, sorted by start time
4. **`get_weather(latitude, longitude, days, timezone)`** — fetches forecast from Open-Meteo API; defaults to Tokyo (35.6762°N, 139.6503°E), 3 days, `Asia/Tokyo`; returns the `daily` dict from the API response
5. **`generate_image(events, weather_data, debug=False)`** — renders a `296×152` PIL `Image` split into left (calendar, up to 5 events) and right (weather) panels; converts to 1-bit monochrome without dithering (`Image.Dither.NONE`) for e-ink
6. **`send_image(device_id, api_key, image, debug=False)`** — base64-encodes the PNG and POSTs to the device API with Bearer auth

`output.png` is saved locally only when `--debug` or `--dry-run` is passed.

## Platform Notes

Font loading is cross-platform. `_load_font()` iterates `_EMOJI_FONT_CANDIDATES` and `_JP_FONT_CANDIDATES` (defined at module level) and returns the first match, so adding support for a new OS means appending to those lists.

- **Japanese**: macOS uses Hiragino Sans W6 (built-in); Windows uses Meiryo (built-in); Linux tries fonts in this priority order for best e-ink legibility:
  1. `NotoSansCJK-Black.ttc` (heaviest weight) — requires `fonts-noto-cjk-extra` on Ubuntu/Debian
  2. `NotoSansJP-Bold.ttf/.otf` (Japan-only subset, Bold)
  3. `NotoSansCJK-Bold.ttc` — included in `fonts-noto-cjk`
  4. `NotoSansCJK-Regular.ttc` — fallback
- **Emoji**: Linux tries `NotoEmoji-Regular.ttf` first, then Symbola (`fonts-symbola`). On macOS, `NotoEmoji-Regular.ttf` must be installed manually. On Windows, Segoe UI Emoji is used as the fallback.

### Linux font install (Ubuntu/Debian)

```bash
# Minimum (Bold weight)
sudo apt install fonts-noto-cjk

# For Black (heaviest) weight
sudo apt install fonts-noto-cjk-extra

# For NotoEmoji monochrome
sudo apt install fonts-noto
```
