#!/usr/bin/env python3
"""iCalカレンダーと天気予報からPNG画像を生成しAPIに送信するスクリプト"""

import argparse
import base64
import io
import os
import re
import sys
from datetime import datetime, timedelta

import requests
from PIL import Image, ImageDraw, ImageFont


# 天気コード -> 絵文字 マッピング
WEATHER_EMOJI = {
    0: "☀️", 1: "☀️",  # 晴れ
    2: "⛅", 3: "☁️",  # 曇り
    45: "🌫️", 48: "🌫️",  # 霧
    51: "🌦️", 53: "🌦️", 55: "🌧️",  # 霧雨
    56: "🌧️", 57: "🌧️",  # 凍雨
    61: "🌧️", 63: "🌧️", 65: "🌧️",  # 雨
    66: "🌧️", 67: "🌧️",  # 凍雨
    71: "🌨️", 73: "🌨️", 75: "🌨️",  # 雪
    77: "🌨️",  # 雪粒
    80: "🌦️", 81: "🌧️", 82: "🌧️",  # 驟雨
    85: "🌨️", 86: "🌨️",  # 驟雪
    95: "⛈️", 96: "⛈️", 99: "⛈️",  # 雷雨
}

# 天気コード -> 日本語テキスト
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
    """コマンドライン引数をパースする"""
    parser = argparse.ArgumentParser(
        description="iCalカレンダーと天気予報からPNG画像を生成しAPIに送信する"
    )
    parser.add_argument(
        "--ical-url",
        type=str,
        help="Google CalendarのiCal URL"
    )
    parser.add_argument(
        "--device-id",
        type=str,
        help="デバイス固有ID"
    )
    parser.add_argument(
        "--api-key",
        type=str,
        help="APIキー"
    )
    return parser.parse_args()


def get_calendar_events(ical_url):
    """iCal URLからカレンダーイベントを取得する"""
    try:
        response = requests.get(ical_url, timeout=10)
        response.raise_for_status()
        ical_data = response.text
    except requests.RequestException as e:
        print(f"カレンダーの取得に失敗しました: {e}", file=sys.stderr)
        return []

    events = []
    lines = ical_data.split("\n")
    
    in_event = False
    current_event = {}
    
    # iCalのVEVENTから情報を抽出
    for line in lines:
        # 行継続の処理 (RFC 5545)
        if line.startswith("\t") or line.startswith(" "):
            current_line = line.lstrip("\t ").lstrip(" ")
            if current_line and "summary" in current_event:
                current_event["summary"] += current_line
            continue
        
        if line.startswith("BEGIN:VEVENT"):
            in_event = True
            current_event = {}
            continue
        
        if line.startswith("END:VEVENT"):
            in_event = False
            if current_event.get("summary") and current_event.get("dtstart"):
                events.append(current_event)
            continue
        
        if in_event:
            if line.startswith("SUMMARY:"):
                current_event["summary"] = line[len("SUMMARY:"):]
            elif line.startswith("DTSTART"):
                # DTSTART;VALUE=DATE:20260501 または DTSTART:20260501T100000Z
                dt_start = line.split(":")[-1]
                current_event["dtstart"] = parse_ical_datetime(dt_start)
            elif line.startswith("DTEND"):
                dt_end = line.split(":")[-1]
                current_event["dtend"] = parse_ical_datetime(dt_end)
            elif line.startswith("DESCRIPTION:"):
                current_event["description"] = line[len("DESCRIPTION:"):]
    
    return events


def parse_ical_datetime(dt_str):
    """iCal形式の日時文字列をパースする"""
    # 日時形式: 20260501T100000
    if "T" in dt_str:
        dt_str_clean = dt_str.replace("Z", "").replace("U", "")
        try:
            return datetime.strptime(dt_str_clean, "%Y%m%dT%H%M%S")
        except ValueError:
            pass
    
    # 日付のみ形式: 20260501
    if len(dt_str) == 8:
        try:
            return datetime.strptime(dt_str, "%Y%m%d")
        except ValueError:
            pass
    
    return None


def get_weather(latitude=35.6762, longitude=139.6503, days=3):
    """天気予報APIから情報を取得する"""
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "daily": "weather_code,temperature_2m_max,temperature_2m_min",
        "forecast_days": days,
        "timezone": "Asia/Tokyo"
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        return data.get("daily", {})
    except requests.RequestException as e:
        print(f"天気情報の取得に失敗しました: {e}", file=sys.stderr)
        return {}


def generate_image(events, weather_data):
    """カレンダーイベントと天気データからPNG画像を生成する"""
    width, height = 296, 152
    
    # 白背景の画像を作成
    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)
    
    # フォントの読み込み
    # 絵文字用フォント (WindowsのSegoe UI Emoji)
    emoji_font = None
    try:
        emoji_font = ImageFont.truetype("C:/Windows/Fonts/seguiemj.ttf", 14)
    except (FileNotFoundError, OSError):
        print("警告: 絵文字フォントが見つかりません。代わりにデフォルトフォントを使用します。", file=sys.stderr)
    
    # 日本語用フォント (WindowsのMeiryo)
    jp_font = None
    try:
        jp_font = ImageFont.truetype("C:/Windows/Fonts/meiryo.ttc", 11)
        jp_font_bold = ImageFont.truetype("C:/Windows/Fonts/meiryo.ttc", 12)
    except (FileNotFoundError, OSError):
        # フォントがない場合はデフォルトフォントにフォールバック
        jp_font = ImageFont.load_default()
        jp_font_bold = jp_font
        print("警告: Meiryoフォントが見つかりません。デフォルトフォントを使用します。", file=sys.stderr)
    
    # 黒色
    black = (0, 0, 0)
    
    # 描画開始位置
    y_pos = 4
    
    # ヘッダー: "スケジュール  天気予報"
    header = "スケジュール                 天気予報"
    try:
        draw.text((4, y_pos), header, font=jp_font_bold, fill=black)
        y_pos += 16
    except Exception:
        y_pos += 14
    
    # 区切り線
    draw.line([(4, y_pos), (width - 4, y_pos)], fill=black, width=1)
    y_pos += 4
    
    # 右側: 天気予報（3日分） - 右端に配置
    daily = weather_data
    weather_x = 150  # 右側に配置
    weather_y = 20   # ヘッダーの区切り線の後
    
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
            
            # 天気情報を描画
            try:
                # 絵文字アイコン（絵文字フォントで描画）
                if emoji_font:
                    draw.text((weather_x, weather_y), emoji, font=emoji_font, fill=black)
                    # 絵文字の幅を取得してテキストの開始位置を調整
                    try:
                        emoji_bbox = draw.textbbox((0, 0), emoji, font=emoji_font)
                        text_start_x = weather_x + int((emoji_bbox[2] - emoji_bbox[0]) * 0.6) + 2
                    except Exception:
                        text_start_x = weather_x + 18
                else:
                    text_start_x = weather_x + 2
                
                # 日付（絵文字の右側）
                draw.text((text_start_x, weather_y), display_date, font=jp_font, fill=black)
                weather_y += 16
                
                # 天気テキスト（気温）
                weather_line = f"{weather_name} {max_temp}/{min_temp}°C"
                draw.text((weather_x, weather_y), weather_line, font=jp_font, fill=black)
                weather_y += 16
            except Exception as e:
                print(f"天気描画エラー: {e}", file=sys.stderr)
    
    # 左側: カレンダーイベント（最大5件）
    left_x = 4
    left_y_start = 20  # 天気情報と同じ高さに
    
    # イベントの表示（直近5件）
    event_count = 0
    y_pos = left_y_start
    for event in events:
        if event_count >= 5:
            break
        
        dt_start = event.get("dtstart")
        summary = event.get("summary", "(無題)")
        
        if dt_start:
            # 日付フォーマット
            date_str = dt_start.strftime("%m/%d")
            time_str = ""
            if dt_start.hour != 0 or dt_start.minute != 0:
                time_str = dt_start.strftime("%H:%M")
            
            # 行の構成
            if time_str:
                line = f"{date_str} {time_str} {summary}"
            else:
                line = f"{date_str} {summary}"
            
            # 改行処理（行長が制限を超えたら折り返し）
            max_line_width = 130  # 右側の天気情報用スペースを確保
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
            
            for wrapped_line in wrapped_lines[:2]:  # 最大2行まで
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
    
    # モノクロ化（2値化）
    img_mono = img.convert("1", dither=Image.Dither.NONE)
    
    return img_mono


def send_image(device_id, api_key, image):
    """PNG画像をbase64エンコーディングしてAPIに送信する"""
    # PNGとしてバイト列にエクスポート
    img_bytes = io.BytesIO()
    image.save(img_bytes, format="PNG")
    img_bytes.seek(0)
    
    # base64エンコーディング
    image_b64 = base64.b64encode(img_bytes.read()).decode("utf-8")
    
    # APIエンドポイント
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
    
    # ヘッダとボディの内容を表示
    print("\n========== API リクエスト ==========")
    print(f"POST {url}")
    print("-------- ヘッダ --------")
    for key, value in headers.items():
        print(f"  {key}: {value}")
    print("-------- ボディ --------")
    print(f'  {{"image": "{image_b64[:100]}...", "border": {payload["border"]}, "ditherType": "{payload["ditherType"]}", "refreshNow": {"true" if payload["refreshNow"] else "false"}}}')
    print("====================================\n")
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        print(response.text)    
        # レスポンスを表示
        print("\n========== API レスポンス ==========")
        print(f"Status: {response.status_code}")
        print("-------- レスポンスヘッダ --------")
        for key, value in response.headers.items():
            print(f"  {key}: {value}")
        print("-------- レスポンスボディ --------")
        try:
            print(f"  {response.json()}")
        except Exception:
            print(f"  {response.text}")
        print("====================================\n")
        
        response.raise_for_status()
        print(f"画像送信成功: HTTP {response.status_code}")
        return response
    except requests.RequestException as e:
        print(f"画像送信に失敗しました: {e}", file=sys.stderr)
        return None


def main():
    args = parse_args()
    
    # 引数または環境変数から値を取得
    ical_url = args.ical_url or os.environ.get("ICAL_URL")
    if not ical_url:
        ical_url = input("iCal URL: ").strip()
        if not ical_url:
            print("エラー: iCal URLが指定されていません。", file=sys.stderr)
            sys.exit(1)
    
    device_id = args.device_id or os.environ.get("DEVICE_ID")
    if not device_id:
        device_id = input("Device ID: ").strip()
        if not device_id:
            print("エラー: Device IDが指定されていません。", file=sys.stderr)
            sys.exit(1)
    
    api_key = args.api_key or os.environ.get("API_KEY")
    if not api_key:
        api_key = input("API Key: ").strip()
        if not api_key:
            print("エラー: API Keyが指定されていません。", file=sys.stderr)
            sys.exit(1)
    
    print("カレンダーイベントを取得中...")
    events = get_calendar_events(ical_url)
    print(f"イベント数: {len(events)}")
    
    print("天気予報を取得中...")
    weather_data = get_weather()
    print(f"予報日数: {len(weather_data.get('time', []))}")
    
    print("画像を生成中...")
    image = generate_image(events, weather_data)
    
    # 画像を保存（デバッグ用）
    image.save("output.png")
    print("画像を保存しました: output.png")
    
    print("画像を送信中...")
    result = send_image(device_id, api_key, image)
    
    if result:
        print("完了しました！")
    else:
        print("画像送信に失敗しました。", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()