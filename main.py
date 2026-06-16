import os
import time
import json
import cv2
import requests
import yt_dlp
from flask import Flask, request, jsonify
from google import genai
from google.cloud import storage

app = Flask(__name__)

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
BUCKET_NAME = os.environ.get("BUCKET_NAME", "dify-video-manual-images")

client = genai.Client(api_key=GEMINI_API_KEY)
storage_client = storage.Client()


@app.route("/")
def hello():
    return "Video Manual API OK"


# ✅ YouTubeダウンロード
def download_video(url):
    ydl_opts = {
        'format': 'best[height<=360]',
        'outtmpl': '/tmp/%(id)s.%(ext)s',
        'quiet': True,
        'noplaylist': True
    }

    print("Downloading video...")

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)

    print("Downloaded:", filename)
    return filename


@app.route("/manual", methods=["POST"])
def manual():
    data = request.get_json(silent=True)

    if not data:
        return jsonify({
            "manual": "",
            "images": [],
            "error": "JSON body is required"
        })

    source_url = data.get("video_url") or data.get("file_url")

    if not source_url:
        return jsonify({
            "manual": "",
            "images": [],
            "error": "URLがありません"
        })

    try:
        print("=== START ===")
        print("URL:", source_url)

        # ✅ YouTube or 通常
        if "youtube" in source_url:
            video_path = download_video(source_url)
        else:
            video_path = f"/tmp/{int(time.time())}.mp4"

            r = requests.get(source_url, timeout=180)
            r.raise_for_status()

            with open(video_path, "wb") as f:
                f.write(r.content)

        # ✅ ファイルチェック
        if not os.path.exists(video_path):
            raise Exception("動画が存在しません")

        size = os.path.getsize(video_path)
        print("size:", size)

        if size < 100000:
            raise Exception("動画が小さすぎる")

        # ✅ フレーム抽出
        work_id = str(int(time.time()))

        frame_paths = extract_frames(video_path, work_id)

        if not frame_paths:
            raise Exception("フレーム抽出失敗")

        image_urls = upload_frames(frame_paths, work_id)

        print("frames:", len(frame_paths))

        # ✅ ⭐ 重要：Geminiは画像URLだけで生成
        prompt = f"""
以下の画像は動画から抽出した操作画面です。

これを元に操作マニュアルを作成してください。

画像一覧:
{json.dumps(image_urls, ensure_ascii=False, indent=2)}

出力形式：

# 操作手順

## 手順1
![image](URL)
説明

## 手順2
![image](URL)
説明

条件：
- Markdown形式
- 必ず画像URLを使う
"""

        print("Generating manual...")

        response = client.models.generate_content(
            model="gemini-2.5-pro",
            contents=prompt   # ✅ ここが最重要（動画渡さない）
        )

        text = response.text if response.text else ""

        if not text.strip():
            raise Exception("Gemini出力が空")

        print("=== SUCCESS ===")

        return jsonify({
            "manual": text,
            "images": image_urls
        })

    except Exception as e:
        print("ERROR:", str(e))

        return jsonify({
            "manual": "",
            "images": [],
            "error": str(e)
        })


def extract_frames(video_path, work_id):
    cap = cv2.VideoCapture(video_path)

    if not cap.isOpened():
        raise Exception("動画が開けません")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    interval = int(fps * 10)

    frame_paths = []
    frame_count = 0
    saved = 0

    while cap.isOpened() and saved < 3:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_count % interval == 0:
            path = f"/tmp/{work_id}_{saved}.jpg"
            cv2.imwrite(path, frame)
            frame_paths.append(path)
            saved += 1

        frame_count += 1

    cap.release()
    return frame_paths


def upload_frames(frame_paths, work_id):
    bucket = storage_client.bucket(BUCKET_NAME)

    urls = []

    for i, path in enumerate(frame_paths):
        name = f"frames/{work_id}_{i}.jpg"
        blob = bucket.blob(name)
        blob.upload_from_filename(path, content_type="image/jpeg")
        urls.append(blob.public_url)

    return urls
