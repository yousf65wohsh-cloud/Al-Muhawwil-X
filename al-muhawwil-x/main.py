import os
import time
import threading
from pathlib import Path
from flask import Flask, render_template, jsonify, request

# تحديد المسارات
TEMP_DIR = Path("temp")
TEMP_DIR.mkdir(exist_ok=True)

# 🛠️ التعديل الذكي والآمن لمنع تضارب المجلد والانهيار (FileExistsError)
STATIC_DIR = Path("static")
if not STATIC_DIR.exists():
    STATIC_DIR.mkdir(parents=True, exist_ok=True)

TEMP_MAX_AGE = 300
CLEANUP_INTERVAL = 60

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

# تشغيل نظام التنظيف التلقائي في الخلفية
cleanup_old_files()
cleanup_thread = threading.Thread(target=_periodic_cleanup_loop, daemon=True)
cleanup_thread.start()

@app.route("/")
def index():
    # عرض الواجهة الفخمة والحديثة للمستخدم
    return render_template("index.html")

# مسار احتياطي صامت لمنع أي تعليق في الـ Frontend
@app.route("/extract", methods=["POST"])
def extract():
    return jsonify({"status": "redirected_to_frontend"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    debug = os.environ.get("FLASK_DEBUG", "").lower() in ("1", "true")
    app.run(host="0.0.0.0", port=port, debug=debug)
