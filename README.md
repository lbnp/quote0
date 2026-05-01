# quote0

Generates a 296×152 monochrome PNG image from Google Calendar events and a 3-day weather forecast, then uploads it to an e-ink display device via REST API.

## Requirements

- Python 3
- Works on Windows, macOS, and Linux

```bash
pip install -r requirements.txt
```

### Fonts

**Japanese text** is rendered with the first available font from this priority list:

| Platform | Font |
|---|---|
| macOS | Hiragino Sans (built-in) |
| Windows | Meiryo (built-in) |
| Linux | Noto Sans CJK (`fonts-noto-cjk` package) |

**Emoji** requires [Noto Emoji](https://fonts.google.com/noto/specimen/Noto+Emoji) (`NotoEmoji[wght].ttf`), which is not bundled with any OS:

```bash
# macOS
curl -L -o ~/Library/Fonts/"NotoEmoji[wght].ttf" \
  "https://github.com/google/fonts/raw/main/ofl/notoemoji/NotoEmoji%5Bwght%5D.ttf"

# Linux
sudo curl -L -o /usr/share/fonts/truetype/noto/"NotoEmoji[wght].ttf" \
  "https://github.com/google/fonts/raw/main/ofl/notoemoji/NotoEmoji%5Bwght%5D.ttf"
```

On Windows, place `NotoEmoji[wght].ttf` in `C:\Windows\Fonts\` or use the built-in Segoe UI Emoji (already detected automatically).

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
