import io
import os
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image
from google import genai

app = FastAPI(title="VisionPod Camera Test")

HTML = r"""<!doctype html>
<html lang="ar" dir="rtl">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>VisionPod — اختبار كاميرا الهاتف</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 760px; margin: 0 auto; padding: 16px; line-height: 1.6; background: #f6f7f8; color: #17202a; }
    main { background: white; padding: 18px; border-radius: 16px; box-shadow: 0 2px 14px #0001; }
    h1 { margin-top: 0; font-size: 1.5rem; }
    video, canvas { width: 100%; max-height: 55vh; background: #111; border-radius: 12px; }
    canvas { display: none; }
    button { border: 0; border-radius: 10px; padding: 12px 16px; font-size: 1rem; margin: 6px 3px 6px 0; background: #185adb; color: white; }
    button.secondary { background: #4b5563; }
    button:disabled { opacity: .5; }
    textarea { width: 100%; box-sizing: border-box; min-height: 74px; padding: 10px; border-radius: 10px; border: 1px solid #ccd1d8; font: inherit; }
    #status, #answer { white-space: pre-wrap; background: #f0f3f7; padding: 12px; border-radius: 10px; margin-top: 12px; }
    .note { font-size: .92rem; color: #4b5563; }
  </style>
</head>
<body>
<main>
  <h1>VisionPod — أول اختبار للكاميرا 📷</h1>
  <p>افتح الكاميرا، صوّر غرضًا، واكتب سؤالًا. الصورة لا تُرسل إلا عندما تضغط زر التحليل.</p>
  <p class="note"><b>الخصوصية:</b> عند التحليل، تُرسل الصورة إلى خادم الاختبار ثم إلى Google Gemini API إذا أضفت مفتاح API. لا تصوّر أشخاصًا أو معلومات خاصة. لا تضع مفتاح API في هذه الصفحة.</p>
  <video id="video" autoplay playsinline></video>
  <canvas id="canvas"></canvas>
  <div>
    <button id="start">تشغيل الكاميرا</button>
    <button id="capture" class="secondary" disabled>التقاط صورة</button>
  </div>
  <label for="question"><b>سؤالك عن الصورة</b></label>
  <textarea id="question">صف لي ما تراه في الصورة، واذكر ما أنت متأكد منه وما قد يحتاج إلى تحقق.</textarea>
  <div><button id="analyze" disabled>إرسال الصورة وتحليلها</button></div>
  <div id="status">الحالة: بانتظار تشغيل الكاميرا.</div>
  <h3>النتيجة</h3>
  <div id="answer">لم يتم التحليل بعد.</div>
</main>
<script>
const video = document.getElementById('video');
const canvas = document.getElementById('canvas');
const startBtn = document.getElementById('start');
const captureBtn = document.getElementById('capture');
const analyzeBtn = document.getElementById('analyze');
const statusBox = document.getElementById('status');
const answerBox = document.getElementById('answer');
let stream = null;
let photoBlob = null;

startBtn.onclick = async () => {
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: "environment" } }, audio: false
    });
    video.srcObject = stream;
    await video.play();
    captureBtn.disabled = false;
    statusBox.textContent = "الحالة: الكاميرا تعمل. اضغط «التقاط صورة».";
  } catch (e) {
    statusBox.textContent = "تعذر تشغيل الكاميرا: " + e.message +
      "\\nتأكد من السماح للمتصفح باستخدام الكاميرا، وافتح الرابط عبر HTTPS.";
  }
};

captureBtn.onclick = () => {
  if (!video.videoWidth) {
    statusBox.textContent = "انتظر حتى تشتغل الكاميرا.";
    return;
  }
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  canvas.getContext('2d').drawImage(video, 0, 0);
  canvas.toBlob(blob => {
    photoBlob = blob;
    analyzeBtn.disabled = !photoBlob;
    statusBox.textContent = "تم التقاط الصورة محليًا. لم تُرسل بعد.";
    answerBox.textContent = "الصورة جاهزة للتحليل.";
  }, "image/jpeg", 0.82);
};

analyzeBtn.onclick = async () => {
  if (!photoBlob) return;
  analyzeBtn.disabled = true;
  statusBox.textContent = "جارٍ إرسال الصورة وتحليلها...";
  answerBox.textContent = "";
  const data = new FormData();
  data.append("image", photoBlob, "camera.jpg");
  data.append("question", document.getElementById('question').value);
  try {
    const res = await fetch("/analyze", { method: "POST", body: data });
    const result = await res.json();
    if (!res.ok) throw new Error(result.detail || "حدث خطأ غير معروف");
    answerBox.textContent = result.answer;
    statusBox.textContent = "نجح الاتصال والتحليل.";
  } catch (e) {
    statusBox.textContent = "فشل التحليل: " + e.message;
  } finally {
    analyzeBtn.disabled = false;
  }
};
window.addEventListener("pagehide", () => {
  if (stream) stream.getTracks().forEach(track => track.stop());
});
</script>
</body>
</html>"""

@app.get("/", response_class=HTMLResponse)
def home():
    return HTML

@app.get("/health")
def health():
    return {"ok": True, "service": "VisionPod Camera Test"}

@app.post("/analyze")
async def analyze(image: UploadFile = File(...), question: str = Form("Describe this image.")):
    api_key = os.getenv("GEMINI_API_KEY")
    if image.content_type not in ("image/jpeg", "image/png", "image/webp"):
        raise HTTPException(status_code=415, detail="نوع الصورة غير مدعوم. استخدم JPEG أو PNG أو WEBP.")
    raw = await image.read()
    if len(raw) > 8 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="الصورة كبيرة جدًا؛ الحد الأقصى 8MB.")
    try:
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        # Camera-to-container smoke test works without any model/API key.
        if not api_key:
            return {
                "answer": (
                    "نجح الاختبار الأول! وصلت الصورة إلى حاوية Linux.\\n"
                    f"الأبعاد: {img.width} × {img.height}\\n"
                    f"حجم الملف: {len(raw)} بايت\\n"
                    "لم يتم تحليل محتوى الصورة بعد لأن مفتاح نموذج الرؤية غير مضاف. "
                    "الخطوة التالية: إضافة مفتاح Gemini API اختياريًا لتفعيل التحليل."
                )
            }
        client = genai.Client(api_key=api_key)
        prompt = (
            "أجب باللغة العربية وبشكل واضح ومختصر. حلل الصورة فقط، "
            "واذكر ما لا تستطيع التأكد منه بدل التخمين. سؤال المستخدم: " + question
        )
        response = client.models.generate_content(
            model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            contents=[prompt, img],
        )
        return {"answer": response.text or "لم يرجع النموذج نصًا."}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"تعذر تحليل الصورة عبر النموذج: {type(exc).__name__}: {exc}")
