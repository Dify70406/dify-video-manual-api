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


# ✅ YouTube動画ダウンロード（修正済み）
def download_video(url, video_path):
    ydl_opts = {
        'format': 'best[height<=360]',  # ✅ ← 修正済み（これ超重要）
        'outtmpl': video_path,
        'quiet': True,
        'noplaylist': True
    }
    print("yt-dlp format:", ydl_opts['format'])

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])


@app.route("/manual", methods=["POST"])
def manual():
    data = request.get_json(silent=True)

    if not data:
        return jsonify({
            "manual": "",
            "images": [],
            "error": "JSON body is required"
        })

    video_url = data.get("video_url")
    file_url = data.get("file_url")

    source_url = video_url or file_url

    if not source_url:
        return jsonify({
            "manual": "",
            "images": [],
            "error": "video_url or file_url is required"
        })

    work_id = str(int(time.time()))
    video_path = f"/tmp/{work_id}.mp4"

    try:
        print("=== START ===")

        # ✅ 動画ダウンロード
        if "youtube.com" in source_url or "youtu.be" in source_url:
            print("YouTube download start")
            download_video(source_url, video_path)
            print("YouTube download finished")
        else:
            print("Normal download start")
            r = requests.get(source_url, timeout=180)
            r.raise_for_status()

            with open(video_path, "wb") as f:
                f.write(r.content)

            print("Normal download finished")

        # ✅ ファイルチェック（重要）
        exists = os.path.exists(video_path)
        size = os.path.getsize(video_path) if exists else 0

        print("file exists:", exists)
        print("file size:", size)

        if not exists:
            raise Exception("動画ファイルが存在しません")

        if size < 1024 * 100:
            raise Exception("動画が小さすぎる（ダウンロード失敗）")

        # ✅ フレーム抽出
        frame_paths = extract_frames(
            video_path,
            work_id,
            interval_sec=10,
            max_frames=3
        )

        print("frames:", len(frame_paths))

        if len(frame_paths) == 0:
            raise Exception("フレーム抽出できません")

        image_urls = upload_frames(frame_paths, work_id)

        # ✅ Gemini
        print("Gemini upload start")
        uploaded_file = client.files.upload(file=video_path)

        while uploaded_file.state.name == "PROCESSING":
            time.sleep(5)
            uploaded_file = client.files.get(name=uploaded_file.name)

        if uploaded_file.state.name != "ACTIVE":
            raise Exception("Gemini動画処理失敗")

        print("Gemini ready")

        prompt = f"""
この動画を分析して簡潔な操作マニュアルを作成してください。

画像一覧:
{json.dumps(image_urls, ensure_ascii=False)}

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
- 画像URLを必ず使う
"""

        print("Generating...")

        response = client.models.generate_content(
            model="gemini-2.5-pro",
            contents=[uploaded_file, prompt]
        )

        text = response.text if response.text else ""

        if text.strip() == "":
            raise Exception("Geminiの出力が空です")

        print("=== SUCCESS ===")

        return jsonify({
            "manual": text,
            "images": image_urls
        })

    except Exception as e:
        print("ERROR:", str(e))

        # ✅ Dify対応：200で返す
        return jsonify({
            "manual": "",
            "images": [],
            "error": str(e)
        })


def extract_frames(video_path, work_id, interval_sec=10, max_frames=3):
    cap = cv2.VideoCapture(video_path)

    if not cap.isOpened():
        raise Exception("動画が開けません")

    fps = cap.get(cv2.CAP_PROP_FPS)
    if not fps or fps <= 0:
        fps = 30

    frame_interval = int(fps * interval_sec)

    frame_paths = []
    frame_count = 0
    saved_count = 0

    while cap.isOpened() and saved_count < max_frames:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_count % frame_interval == 0:
            frame_path = f"/tmp/{work_id}_frame_{saved_count + 1}.jpg"
            cv2.imwrite(frame_path, frame)
            frame_paths.append(frame_path)
            saved_count += 1

        frame_count += 1

    cap.release()
    return frame_paths


def upload_frames(frame_paths, work_id):
    bucket = storage_client.bucket(BUCKET_NAME)

    urls = []

    for i, frame_path in enumerate(frame_paths, start=1):
        blob_name = f"manual_frames/{work_id}/frame_{i}.jpg"
        blob = bucket.blob(blob_name)
        blob.upload_from_filename(frame_path, content_type="image/jpeg")
        urls.append(blob.public_url)

    return urls
