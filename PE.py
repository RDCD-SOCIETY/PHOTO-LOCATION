#!/usr/bin/env python3
# RDCS PHOTO FORENSIC ENGINE

import csv
import getpass
import html
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path

APP_NAME = "RDCS PHOTO FORENSIC ENGINE"
BRAND_NAME = "READ DRAGON CYBER SECURITY"
FACEBOOK_URL = "https://www.facebook.com/RDCSSOCIETY"

BASE = Path.home() / "RDCS_PHOTO_FORENSIC_ENGINE"
REPORTS = BASE / "reports"
CONFIG = BASE / "telegram_config.json"
USER_AGENT = "RDCS-Photo-Metadata-Tool/1.0"

BASE.mkdir(parents=True, exist_ok=True)
REPORTS.mkdir(parents=True, exist_ok=True)

GREEN = "\033[92m"
CYAN = "\033[96m"
BLUE = "\033[94m"
YELLOW = "\033[93m"
RED = "\033[91m"
BLOOD = "\033[38;5;124m"
RESET = "\033[0m"
BOLD = "\033[1m"


def open_rdcs_facebook():
    try:
        result = subprocess.run(
            ["termux-open-url", FACEBOOK_URL],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10
        )

        if result.returncode == 0:
            return

    except Exception:
        pass

    try:
        subprocess.run(
            [
                "am", "start",
                "-a", "android.intent.action.VIEW",
                "-d", FACEBOOK_URL
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10
        )

    except Exception:
        print(
            YELLOW
            + "Could not open RDCS Facebook page."
            + RESET
        )


def banner():
    os.system("clear")
    print(BLOOD + BOLD + r"""
██████╗ ██████╗  ██████╗███████╗
██╔══██╗██╔══██╗██╔════╝██╔════╝
██████╔╝██║  ██║██║     ███████╗
██╔══██╗██║  ██║██║     ╚════██║
██║  ██║██████╔╝╚██████╗███████║
╚═╝  ╚═╝╚═════╝  ╚═════╝╚══════╝
""" + RESET)

    print(BLOOD + BOLD + "       READ DRAGON CYBER SECURITY" + RESET)
    print(GREEN + "       PHOTO FORENSIC ENGINE" + RESET)
    print(BLUE + "       Single Photo Metadata Analyzer" + RESET)
    print("-" * 58)


def pause():
    input(f"\n{YELLOW}Press Enter to continue...{RESET}")


def load_config():
    if not CONFIG.exists():
        return {"bot_token": "", "chat_id": ""}

    try:
        data = json.loads(CONFIG.read_text(encoding="utf-8"))
        return {
            "bot_token": str(data.get("bot_token", "")),
            "chat_id": str(data.get("chat_id", ""))
        }
    except Exception:
        return {"bot_token": "", "chat_id": ""}


def save_config(config):
    CONFIG.write_text(
        json.dumps(config, indent=2),
        encoding="utf-8"
    )

    try:
        CONFIG.chmod(0o600)
    except OSError:
        pass


def check_exiftool():
    return shutil.which("exiftool")


def run_exiftool(photo_path):
    exiftool = check_exiftool()

    if not exiftool:
        raise RuntimeError(
            "ExifTool missing. Install: "
            "pkg install libimage-exiftool-perl -y"
        )

    command = [
        exiftool,
        "-json",
        "-G",
        "-a",
        "-s",
        "-n",
        "-charset",
        "filename=UTF8",
        str(photo_path)
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=90
    )

    if result.returncode not in (0, 1):
        raise RuntimeError(
            result.stderr.strip() or "ExifTool error."
        )

    try:
        rows = json.loads(result.stdout)

        if not rows:
            raise ValueError("No metadata found.")

        return rows[0], result.stderr.strip()

    except Exception as exc:
        raise RuntimeError(f"Metadata parsing error: {exc}")


def find_tag(metadata, names):
    wanted = {name.lower() for name in names}

    for key, value in metadata.items():
        short_key = key.split(":")[-1].lower()

        if short_key in wanted and value not in (None, ""):
            return value

    return None


def numeric_coordinate(value):
    if isinstance(value, (int, float)):
        return float(value)

    if isinstance(value, str):
        try:
            return float(value.strip().replace(",", "."))
        except ValueError:
            return None

    return None


def extract_gps(metadata):
    lat = find_tag(metadata, ["GPSLatitude"])
    lon = find_tag(metadata, ["GPSLongitude"])

    lat_ref = find_tag(metadata, ["GPSLatitudeRef"])
    lon_ref = find_tag(metadata, ["GPSLongitudeRef"])

    lat = numeric_coordinate(lat)
    lon = numeric_coordinate(lon)

    if lat is None or lon is None:
        return None

    if str(lat_ref).upper().startswith("S"):
        lat = -abs(lat)

    if str(lon_ref).upper().startswith("W"):
        lon = -abs(lon)

    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None

    return {
        "latitude": lat,
        "longitude": lon,
        "altitude": find_tag(metadata, ["GPSAltitude"]),
        "accuracy": find_tag(metadata, ["GPSHPositioningError"])
    }


def explicit_location_tags(metadata):
    names = [
        "Location",
        "LocationName",
        "City",
        "State",
        "Province",
        "Country",
        "CountryName",
        "Sub-location",
        "Sublocation",
        "LocationShown",
        "LocationCreated",
        "GPSPosition",
        "Province-State",
        "Country-PrimaryLocationName"
    ]

    found = []

    for name in names:
        value = find_tag(metadata, [name])

        if value not in (None, ""):
            found.append((name, value))

    return found


def reverse_geocode(lat, lon):
    url = (
        "https://nominatim.openstreetmap.org/reverse?"
        + urllib.parse.urlencode({
            "format": "jsonv2",
            "lat": f"{lat:.7f}",
            "lon": f"{lon:.7f}",
            "zoom": 16,
            "addressdetails": 1
        })
    )

    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT}
    )

    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = json.loads(
                response.read().decode("utf-8")
            )

        address = payload.get("address", {})
        parts = []

        for key in (
            "neighbourhood",
            "suburb",
            "village",
            "town",
            "city",
            "county",
            "state",
            "postcode",
            "country"
        ):
            value = address.get(key)

            if value and value not in parts:
                parts.append(value)

        return (
            ", ".join(parts)
            if parts
            else payload.get("display_name", "")
        )

    except Exception:
        return None


def build_location_report(metadata, gps):
    lines = [
        "RDCS LOCATION REPORT",
        "=" * 42
    ]

    if gps:
        lat = gps["latitude"]
        lon = gps["longitude"]

        lines.append("Exact GPS coordinates: FOUND")
        lines.append(f"Latitude: {lat:.7f}")
        lines.append(f"Longitude: {lon:.7f}")

        lines.append(
            f"Map: https://maps.google.com/?q={lat:.7f},{lon:.7f}"
        )

        if gps.get("altitude") is not None:
            lines.append(f"Altitude: {gps['altitude']}")

        if gps.get("accuracy") is not None:
            lines.append(f"GPS positioning error: {gps['accuracy']}")

        approximate = reverse_geocode(lat, lon)

        lines.append(
            "Approximate area: "
            + (approximate or "Reverse geocoding unavailable")
        )

    else:
        lines.append("Exact GPS coordinates: NOT FOUND")
        lines.append("Approximate area from GPS: UNAVAILABLE")

    extra = explicit_location_tags(metadata)

    if extra:
        lines.append("")
        lines.append("Other embedded location tags:")

        for key, value in extra:
            lines.append(f"{key}: {value}")

    else:
        lines.append("Other embedded location tags: none found")

    lines.append("")
    lines.append(
        "Location is reported only from metadata embedded in the supplied file."
    )

    return "\n".join(lines)


def safe_filename(name):
    cleaned = "".join(
        c if c.isalnum() or c in "._-" else "_"
        for c in name
    )

    return cleaned[:100] or "photo"


def flatten_value(value):
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)

    return str(value)


def create_reports(photo_path, metadata, warning, location_text):
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    folder = REPORTS / (
        f"{stamp}_{safe_filename(photo_path.stem)}"
    )

    folder.mkdir(parents=True, exist_ok=True)

    data = {
        "tool": APP_NAME,
        "brand": BRAND_NAME,
        "created_at": datetime.now().astimezone().isoformat(),
        "source_file": str(photo_path),
        "metadata": metadata,
        "exiftool_warning": warning or None,
        "location_report": location_text
    }

    (folder / "metadata.json").write_text(
        json.dumps(
            data,
            indent=2,
            ensure_ascii=False,
            default=str
        ),
        encoding="utf-8"
    )

    txt_lines = [
        APP_NAME,
        BRAND_NAME,
        "=" * 58,
        f"Source file: {photo_path}",
        f"Report created: {data['created_at']}",
        "",
        location_text,
        "",
        "FULL METADATA",
        "=" * 58
    ]

    for key, value in metadata.items():
        txt_lines.append(
            f"{key}: {flatten_value(value)}"
        )

    if warning:
        txt_lines.extend([
            "",
            "EXIFTOOL WARNING",
            warning
        ])

    (folder / "metadata.txt").write_text(
        "\n".join(txt_lines),
        encoding="utf-8"
    )

    with (folder / "metadata.csv").open(
        "w",
        newline="",
        encoding="utf-8-sig"
    ) as file:

        writer = csv.writer(file)
        writer.writerow(["Metadata Field", "Value"])

        for key, value in metadata.items():
            writer.writerow([
                key,
                flatten_value(value)
            ])

    rows = "\n".join(
        "<tr><td>{}</td><td>{}</td></tr>".format(
            html.escape(str(key)),
            html.escape(flatten_value(value))
        )
        for key, value in metadata.items()
    )

    html_doc = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>RDCS Metadata Report</title>

<style>
body{{
    font-family:Arial,sans-serif;
    background:#08111d;
    color:#eaf2ff;
    margin:0;
    padding:20px;
}}

main{{
    max-width:1000px;
    margin:auto;
}}

.brand{{
    text-align:center;
    margin-bottom:28px;
}}

.brand h1{{
    color:#8B0000;
    font-size:38px;
    font-weight:900;
    letter-spacing:5px;
    margin:0;
}}

.brand p{{
    color:#b9c3d0;
    font-size:11px;
    letter-spacing:2px;
    margin-top:5px;
}}

h2{{
    color:#83dcca;
}}

pre{{
    white-space:pre-wrap;
    overflow-wrap:anywhere;
    background:#101e30;
    padding:15px;
    border-radius:10px;
}}

table{{
    width:100%;
    border-collapse:collapse;
    background:#101e30;
}}

td,th{{
    padding:9px;
    border:1px solid #2a3b50;
    text-align:left;
    vertical-align:top;
    overflow-wrap:anywhere;
}}

td:first-child{{
    width:34%;
    color:#8fe8d5;
}}
</style>
</head>

<body>
<main>

<div class="brand">
    <h1>RDCS</h1>
    <p>READ DRAGON CYBER SECURITY</p>
</div>

<h2>PHOTO METADATA REPORT</h2>

<h2>Location Report</h2>
<pre>{html.escape(location_text)}</pre>

<h2>Full Metadata</h2>

<table>
<tr>
<th>Field</th>
<th>Value</th>
</tr>
{rows}
</table>

</main>
</body>
</html>
"""

    (folder / "metadata.html").write_text(
        html_doc,
        encoding="utf-8"
    )

    return folder


def telegram_api(token, method, fields=None, file_path=None):
    url = f"https://api.telegram.org/bot{token}/{method}"
    fields = fields or {}

    if file_path:
        boundary = "----RDCS" + uuid.uuid4().hex
        body = bytearray()

        for key, value in fields.items():
            body.extend(f"--{boundary}\r\n".encode())

            body.extend(
                f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode()
            )

            body.extend(str(value).encode())
            body.extend(b"\r\n")

        filename = file_path.name

        body.extend(f"--{boundary}\r\n".encode())

        body.extend(
            f'Content-Disposition: form-data; name="document"; filename="{filename}"\r\n'.encode()
        )

        body.extend(
            b"Content-Type: application/octet-stream\r\n\r\n"
        )

        body.extend(file_path.read_bytes())
        body.extend(b"\r\n")
        body.extend(f"--{boundary}--\r\n".encode())

        request = urllib.request.Request(
            url,
            data=bytes(body),
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}"
            }
        )

    else:
        encoded = urllib.parse.urlencode(fields).encode()

        request = urllib.request.Request(
            url,
            data=encoded,
            headers={
                "Content-Type": "application/x-www-form-urlencoded"
            }
        )

    with urllib.request.urlopen(request, timeout=45) as response:
        result = json.loads(
            response.read().decode("utf-8")
        )

    if not result.get("ok"):
        raise RuntimeError(
            result.get("description", "Telegram API error")
        )

    return result


def send_to_telegram(location_text, html_file):
    config = load_config()

    token = config.get("bot_token", "")
    chat_id = config.get("chat_id", "")

    if not token or not chat_id:
        print(RED + "Telegram bot token / chat ID not configured." + RESET)
        return

    print(
        YELLOW
        + "\nSend location text and HTML report to Telegram?"
        + RESET
    )

    choice = input("Send now? [y/N]: ").strip().lower()

    if choice != "y":
        print("Telegram sending skipped.")
        return

    try:
        telegram_api(
            token,
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": location_text,
                "disable_web_page_preview": "true"
            }
        )

        telegram_api(
            token,
            "sendDocument",
            {
                "chat_id": chat_id,
                "caption": "RDCS Photo Metadata Report"
            },
            html_file
        )

        print(
            GREEN
            + "Telegram: location text + HTML report sent."
            + RESET
        )

    except Exception as exc:
        print(RED + f"Telegram send failed: {exc}" + RESET)


def analyze_single_photo():
    print(CYAN + "\nSINGLE PHOTO ANALYSIS" + RESET)

    raw_path = input("Paste photo file path: ").strip()
    raw_path = raw_path.strip('"').strip("'")

    if not raw_path:
        print(RED + "No file path entered." + RESET)
        return

    photo_path = Path(os.path.expanduser(raw_path))

    if not photo_path.is_file():
        print(RED + "File not found. Check the path." + RESET)
        return

    try:
        metadata, warning = run_exiftool(photo_path)

        gps = extract_gps(metadata)

        location_text = build_location_report(
            metadata,
            gps
        )

        report_folder = create_reports(
            photo_path,
            metadata,
            warning,
            location_text
        )

        print(GREEN + "\nAnalysis completed." + RESET)

        print(f"File: {photo_path.name}")
        print(f"Metadata fields: {len(metadata)}")
        print(f"GPS: {'FOUND' if gps else 'NOT FOUND'}")
        print(f"Reports: {report_folder}")

        print("\n" + location_text)

        send_to_telegram(
            location_text,
            report_folder / "metadata.html"
        )

    except Exception as exc:
        print(RED + f"\nAnalysis error: {exc}" + RESET)


def telegram_settings():
    config = load_config()

    while True:
        print(CYAN + "\nTELEGRAM BOT SETTINGS" + RESET)

        print("1. Set / Change Bot Token")
        print("2. Set / Change Chat ID")
        print("3. Test Bot Connection")
        print("4. Show Current Settings Status")
        print("5. Back")

        choice = input("\nSelect: ").strip()

        if choice == "1":
            token = getpass.getpass(
                "Enter bot token (input hidden): "
            ).strip()

            if token:
                config["bot_token"] = token
                save_config(config)
                print(GREEN + "Bot token saved." + RESET)

        elif choice == "2":
            chat_id = input("Enter chat ID: ").strip()

            if chat_id:
                config["chat_id"] = chat_id
                save_config(config)
                print(GREEN + "Chat ID saved." + RESET)

        elif choice == "3":
            config = load_config()

            if not config["bot_token"]:
                print(RED + "Set bot token first." + RESET)
                continue

            try:
                result = telegram_api(
                    config["bot_token"],
                    "getMe"
                )

                bot = result.get("result", {})

                print(
                    GREEN
                    + f"Connected: @{bot.get('username', 'unknown')}"
                    + RESET
                )

            except Exception as exc:
                print(RED + f"Connection test failed: {exc}" + RESET)

        elif choice == "4":
            config = load_config()

            print(
                "Bot token:",
                "SET" if config["bot_token"] else "NOT SET"
            )

            print(
                "Chat ID:",
                "SET" if config["chat_id"] else "NOT SET"
            )

            print("Config file:", CONFIG)

        elif choice == "5":
            return

        else:
            print(RED + "Invalid option." + RESET)


def open_reports_location():
    print(f"\nReports folder: {REPORTS}")

    try:
        os.startfile(str(REPORTS))
    except Exception:
        pass


def main():
    # Open RDCS Facebook Page on startup
    open_rdcs_facebook()

    if not check_exiftool():
        print(RED + "ExifTool is not installed." + RESET)
        print("Run: pkg install libimage-exiftool-perl -y")
        pause()
        return

    while True:
        banner()

        print(f"{GREEN}[01]{RESET} SINGLE PHOTO ANALYSIS")
        print(f"{GREEN}[02]{RESET} TELEGRAM BOT SETTINGS")
        print(f"{GREEN}[03]{RESET} OPEN REPORTS LOCATION")
        print(f"{GREEN}[04]{RESET} EXIT")

        choice = input(
            f"\n{CYAN}RDCS Select Option: {RESET}"
        ).strip()

        if choice == "1":
            analyze_single_photo()
            pause()

        elif choice == "2":
            telegram_settings()

        elif choice == "3":
            open_reports_location()
            pause()

        elif choice == "4":
            print(
                GREEN
                + "RDCS Photo Forensic Engine closed."
                + RESET
            )
            break

        else:
            print(RED + "Invalid option." + RESET)
            time.sleep(1)


if __name__ == "__main__":
    try:
        main()

    except KeyboardInterrupt:
        print("\nRDCS stopped.")
        sys.exit(0)