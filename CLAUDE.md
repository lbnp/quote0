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
set ICAL_URL=<url>
set DEVICE_ID=<id>
set API_KEY=<key>
python generate_image.py
```

Priority order for each parameter: CLI arg → environment variable → interactive prompt.

No build step, test suite, or linter is configured.

## Dependencies

No `requirements.txt` exists. Install manually:

```bash
pip install requests Pillow
```

## Architecture

`generate_image.py` is structured as a linear pipeline inside `main()`:

1. **`parse_args()`** — argparse CLI + env var fallback + interactive prompt
2. **`get_calendar_events(ical_url)`** — fetches and parses iCal from Google Calendar; returns list of `(date_str, summary)` tuples (up to 5 events)
3. **`get_weather()`** — fetches 3-day forecast from Open-Meteo API (hardcoded to Tokyo 35.6762°N, 139.6503°E); returns list of `(date_str, weather_emoji, max_temp, min_temp)`
4. **`generate_image(events, weather)`** — renders a `296×152` PIL `Image` split into left (calendar) and right (weather) panels; converts to 1-bit dithered monochrome for e-ink; saves `output.png` locally as debug output
5. **`send_image(image, device_id, api_key)`** — base64-encodes the PNG and POSTs to the device API with Bearer auth

## Platform Notes

The image renderer uses Windows-specific font paths:
- `C:\Windows\Fonts\seguiemj.ttf` (Segoe UI Emoji) for weather icons
- `C:\Windows\Fonts\meiryo.ttc` (Meiryo) for Japanese text

Running on non-Windows systems requires adjusting the font paths in `generate_image()`.
