import os
import re
import time
import threading
from pathlib import Path

import requests
from flask import Flask, request, jsonify, redirect, render_template

TEMP_DIR = Path("temp")
TEMP_DIR.mkdir(exist_ok=True)
STATIC_DIR = Path("static")
STATIC_DIR.mkdir(exist_ok=True)

TEMP_MAX_AGE = 300
CLEANUP_INTERVAL = 60

COBALT_API = "https://api.cobalt.tools/api/json"
COBALT_HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
}

app = Flask(__name__)


def force_cleanup(file_path: str):
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
    except Exception:
        pass


def cleanup_old_files():
    now = time.time()
    for f in TEMP_DIR.iterdir():
        if f.is_file():
            age = now - f.stat().st_mtime
            if age > TEMP_MAX_AGE:
                force_cleanup(str(f))


def _periodic_cleanup_loop():
    while True:
        time.sleep(CLEANUP_INTERVAL)
        cleanup_old_files()


cleanup_old_files()
cleanup_thread = threading.Thread(target=_periodic_cleanup_loop, daemon=True)
cleanup_thread.start()


def extract_audio(youtube_url: str) -> tuple[str, str]:
    payload = {
        "url": youtube_url,
        "downloadMode": "audio",
        "audioFormat": "mp3",
        "audioBitrate": "192",
    }

    resp = requests.post(
        COBALT_API,
        json=payload,
        headers=COBALT_HEADERS,
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    if data.get("status") == "error":
        raise Exception(data.get("error", "فشل Cobalt في المعالجة"))

    download_url = data.get("url")
    if not download_url:
        raise Exception("Cobalt: لم يتم العثور على رابط التحميل")

    title = data.get("filename", "audio")
    title = re.sub(r"\.mp3$", "", title)

    return download_url, title


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/extract", methods=["POST"])
def extract():
    url = request.form.get("url", "").strip()
    if not url:
        return jsonify(error="URL is required"), 400

    try:
        download_url, title = extract_audio(url)
    except Exception as e:
        return jsonify(error=f"Extraction failed: {str(e)}"), 400

    return jsonify({"url": download_url, "title": title})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "").lower() in ("1", "true")
    app.run(host="0.0.0.0", port=port, debug=debug)
