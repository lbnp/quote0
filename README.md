# quote0

Generates a 296×152 monochrome PNG image from Google Calendar events and a 3-day weather forecast, then uploads it to an e-ink display device via REST API.

## Requirements

- Python 3
- Windows (uses Segoe UI Emoji and Meiryo fonts; adjust font paths in `generate_image.py` for other platforms)

```bash
pip install -r requirements.txt
```

## Usage

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

Priority order: CLI argument → environment variable → interactive prompt.

A debug copy of the generated image is saved as `output.png`.

## Parameters

| Parameter | CLI flag | Environment variable |
|---|---|---|
| Google Calendar iCal URL | `--ical-url` | `ICAL_URL` |
| Device ID | `--device-id` | `DEVICE_ID` |
| API key | `--api-key` | `API_KEY` |
