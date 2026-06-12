import os
import re
import uuid
import threading
import time
from pathlib import Path
from flask import Flask, request, jsonify, send_file, render_template, after_this_request

import yt_dlp

TEMP_DIR = Path("temp")
TEMP_DIR.mkdir(exist_ok=True)
STATIC_DIR = Path("static")
STATIC_DIR.mkdir(exist_ok=True)

TEMP_MAX_AGE = 300
CLEANUP_INTERVAL = 60

app = Flask(__name__)


def sanitize_filename(name: str) -> str:
    sanitized = re.sub(r'[<>:"/\\|?*]', "_", name)
    sanitized = sanitized.strip().strip(".")
    if not sanitized:
        sanitized = "audio"
    return sanitized


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


def extract_audio(url: str):
    file_id = uuid.uuid4().hex
    output_path = str(TEMP_DIR / f"%(id)s_{file_id}.%(ext)s")

    ydl_opts = {
        "format": "bestaudio/best",
        "cookiefile": "cookies.txt",
        "noplaylist": True,
        "playlist_items": "1",
        "ignoreerrors": False,
        "prefer_ffmpeg": True,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
        "outtmpl": output_path,
        "quiet": True,
        "no_warnings": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info_dict = ydl.extract_info(url, download=True)

    if info_dict is None:
        raise Exception("لم يتم العثور على بيانات الفيديو")

    if "entries" in info_dict:
        video_data = info_dict["entries"][0]
    else:
        video_data = info_dict

    video_id = video_data.get("id", "unknown")
    title = video_data.get("title", "audio")

    candidates = list(TEMP_DIR.glob(f"{video_id}_{file_id}.*"))
    if not candidates:
        raise FileNotFoundError(f"Extracted file not found (prefix: {video_id}_{file_id})")

    actual_file = candidates[0]
    ext = actual_file.suffix.lstrip(".")
    return str(actual_file), title, ext


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/extract", methods=["POST"])
def extract():
    url = request.form.get("url", "").strip()
    if not url:
        return jsonify(error="URL is required"), 400

    try:
        file_path, title, ext = extract_audio(url)
    except Exception as e:
        cleanup_old_files()
        return jsonify(error=f"Extraction failed: {str(e)}"), 400

    filename = f"{sanitize_filename(title)}.{ext}"
    media_type = "audio/mpeg" if ext == "mp3" else "audio/mp4"

    @after_this_request
    def delete_after(response):
        force_cleanup(file_path)
        return response

    return send_file(
        file_path,
        as_attachment=True,
        download_name=filename,
        mimetype=media_type,
        headers={
            "X-Zero-Trace": "true",
            "X-Auto-Delete": "true",
        },
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "").lower() in ("1", "true")
    app.run(host="0.0.0.0", port=port, debug=debug)
