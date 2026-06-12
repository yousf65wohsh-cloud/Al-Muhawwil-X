import os
import re
import uuid
import time
import threading
from pathlib import Path

import requests
from flask import Flask, request, jsonify, send_file, render_template, after_this_request

TEMP_DIR = Path("temp")
TEMP_DIR.mkdir(exist_ok=True)
STATIC_DIR = Path("static")
STATIC_DIR.mkdir(exist_ok=True)

TEMP_MAX_AGE = 300
CLEANUP_INTERVAL = 60

app = Flask(__name__)

SERVICES = [
    {
        "name": "yt1s",
        "search_url": "https://yt1s.com/api/ajaxSearch/index",
        "convert_url": "https://yt1s.com/api/ajaxConvert/convert",
        "origin": "https://yt1s.com",
        "referer": "https://yt1s.com/en1",
    },
    {
        "name": "savefrom",
        "search_url": "https://en.savefrom.net/19/download/",
        "convert_url": None,
        "origin": "https://en.savefrom.net",
        "referer": "https://en.savefrom.net/",
    },
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "X-Requested-With": "XMLHttpRequest",
}


def extract_video_id(url: str) -> str | None:
    patterns = [
        r"youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})",
        r"youtu\.be/([a-zA-Z0-9_-]{11})",
        r"youtube\.com/embed/([a-zA-Z0-9_-]{11})",
        r"youtube\.com/v/([a-zA-Z0-9_-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def sanitize_filename(name: str) -> str:
    sanitized = re.sub(r'[<>:"/\\|?*]', "_", name)
    sanitized = sanitized.strip().strip(".")
    return sanitized or "audio"


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


def try_service_yt1s(session: requests.Session, video_id: str) -> tuple[str, str]:
    session.headers.update({
        "Origin": SERVICES[0]["origin"],
        "Referer": SERVICES[0]["referer"],
    })

    search_resp = session.post(
        SERVICES[0]["search_url"],
        data={"q": f"https://www.youtube.com/watch?v={video_id}"},
        timeout=30,
    )
    search_data = search_resp.json()

    if search_data.get("status") != "ok":
        raise Exception(f"yt1s: {search_data.get('mess', 'فشل البحث')}")

    vid = search_data.get("vid", video_id)
    title = search_data.get("title", "audio")

    links = search_data.get("links", {})
    mp3 = links.get("mp3", {})
    if not mp3:
        raise Exception("yt1s: لا يوجد رابط MP3 متاح")

    first_key = list(mp3.keys())[0]
    k = mp3[first_key].get("k") or mp3[first_key].get("key", first_key)

    convert_resp = session.post(
        SERVICES[0]["convert_url"],
        data={"vid": vid, "k": k},
        timeout=30,
    )
    convert_data = convert_resp.json()

    if convert_data.get("status") != "ok":
        raise Exception(f"yt1s: {convert_data.get('mess', 'فشل التحويل')}")

    dlink = convert_data.get("dlink") or convert_data.get("downloadUrl")
    if not dlink:
        raise Exception("yt1s: لم يتم العثور على رابط التحميل")

    return dlink, title


def try_service_savefrom(session: requests.Session, video_id: str) -> tuple[str, str]:
    session.headers.update({
        "Origin": SERVICES[1]["origin"],
        "Referer": SERVICES[1]["referer"],
    })
    session.headers.pop("Content-Type", None)
    session.headers.pop("X-Requested-With", None)

    resp = session.post(
        SERVICES[1]["search_url"],
        data={
            "sf_url": f"https://www.youtube.com/watch?v={video_id}",
            "sf_submit": "Download",
        },
        timeout=30,
    )

    html = resp.text
    title_match = re.search(r'<div class="info-box">.*?<h4>(.*?)</h4>', html, re.DOTALL)
    title = title_match.group(1).strip() if title_match else "audio"

    link_match = re.search(r'href="(https?://[^"]+\.mp3[^"]*)"', html)
    if not link_match:
        link_match = re.search(r'<a[^>]*href="(https?://[^"]+)"[^>]*download[^>]*>', html, re.IGNORECASE)
    if not link_match:
        link_match = re.search(r'class="[^"]*download[^"]*"[^>]*href="(https?://[^"]+)"', html)

    if not link_match:
        raise Exception("savefrom: لم يتم العثور على رابط التحميل")

    return link_match.group(1), title


def download_file(session: requests.Session, url: str, file_path: str):
    resp = session.get(url, stream=True, timeout=60)
    resp.raise_for_status()
    with open(file_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)


def extract_audio(youtube_url: str) -> tuple[str, str]:
    video_id = extract_video_id(youtube_url)
    if not video_id:
        raise Exception("رابط يوتيوب غير صالح")

    session = requests.Session()
    session.headers.update(HEADERS)

    last_error = ""
    for service in SERVICES:
        try:
            if service["name"] == "yt1s":
                dlink, title = try_service_yt1s(session, video_id)
            elif service["name"] == "savefrom":
                dlink, title = try_service_savefrom(session, video_id)
            else:
                continue

            file_id = uuid.uuid4().hex
            file_path = str(TEMP_DIR / f"{file_id}.mp3")

            download_file(session, dlink, file_path)

            return file_path, title

        except Exception as e:
            last_error = str(e)
            continue

    raise Exception(f"فشلت جميع الخدمات: {last_error}")


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/extract", methods=["POST"])
def extract():
    url = request.form.get("url", "").strip()
    if not url:
        return jsonify(error="URL is required"), 400

    try:
        file_path, title = extract_audio(url)
    except Exception as e:
        cleanup_old_files()
        return jsonify(error=f"Extraction failed: {str(e)}"), 400

    filename = f"{sanitize_filename(title)}.mp3"

    @after_this_request
    def delete_after(response):
        force_cleanup(file_path)
        return response

    return send_file(
        file_path,
        as_attachment=True,
        download_name=filename,
        mimetype="audio/mpeg",
        headers={
            "X-Zero-Trace": "true",
            "X-Auto-Delete": "true",
        },
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "").lower() in ("1", "true")
    app.run(host="0.0.0.0", port=port, debug=debug)
