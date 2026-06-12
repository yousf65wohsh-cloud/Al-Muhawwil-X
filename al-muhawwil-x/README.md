# المحول X — Al-Muhawwil X

محرك استخراج صوتي فائق السرعة · Xtreme Speed · Zero-Trace

---

## المتطلبات

- Python 3.9+
- FFmpeg (يتم تثبيته تلقائياً عبر winget)

## التثبيت والتشغيل

```bash
# 1. الانتقال إلى مجلد المشروع
cd al-muhawwil-x

# 2. تثبيت الحزم
pip install -r requirements.txt

# 3. تشغيل السيرفر
python main.py
# أو: uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

ثم افتح المتصفح على: `http://localhost:8000`

## البنية التقنية

```
al-muhawwil-x/
├── main.py              # FastAPI backend (نقطة الدخول)
├── requirements.txt     # الاعتماديات
├── templates/
│   └── index.html       # واجهة المستخدم (SPA)
├── static/              # ملفات ثابتة (إن وجدت)
└── temp/                # مجلد مؤقت - يُمسح تلقائياً
```

## آلية الخصوصية (Zero-Trace)

1. يتم استخراج الصوت إلى مجلد `temp/` مؤقت
2. يُستخدم `BackgroundTasks` لمسح الملف فور انتهاء الاستجابة
3. لا توجد قاعدة بيانات — لا سجلات — لا تتبع
4. عند بدء التشغيل، يُمسح كل ملفات `temp/` تلقائياً
5. الموقع يرسل هيدر `X-Zero-Trace: true` مع كل استجابة

## API

### `GET /`
يعرض الواجهة الرئيسية (HTML).

### `POST /extract`
استخراج الصوت من رابط YouTube.

**Body:** `url=https://youtube.com/watch?v=...`

**Response:** ملف m4a (audio/mp4) مع هيدرات الخصوصية.
