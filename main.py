import os
import time
import json
import cv2
import requests
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


@app.route("/manual", methods=["POST"])
def manual():
    data = request.get_json()
    video_url = data.get("video_url")

    if not video_url:
        return jsonify({"error": "video_url is required"}), 400

    work_id = str(int(time.time()))
    video_path = f"/tmp/{work_id}.mp4"

    # 動画をダウンロード
    r = requests.get(video_url, timeout=180)
    r.raise_for_status()

    with open(video_path, "wb") as f:
        f.write(r.content)

    # スクショ抽出
    frame_paths = extract_frames(video_path, work_id, interval_sec=5, max_frames=10)

    # Cloud Storageへアップロード
    image_urls = upload_frames(frame_paths, work_id)

    # Geminiへ動画アップロード
    uploaded_file = client.files.upload(file=video_path)

    while uploaded_file.state.name == "PROCESSING":
        time.sleep(5)
        uploaded_file = client.files.get(name=uploaded_file.name)

    if uploaded_file.state.name != "ACTIVE":
        return jsonify({"error": "Gemini video processing failed"}), 500

    prompt = f"""
この動画を分析して、スクリーンショット付きの操作手順書を作成してください。

以下の画像URLは、動画から自動抽出したスクリーンショットです。
適切な手順の位置に Markdown 形式で画像を挿入してください。

画像URL一覧:
{json.dumps(image_urls, ensure_ascii=False, indent=2)}

出力形式:

# 概要

# 操作手順

## 手順1：〇〇する
![手順1](画像URL)
説明文

## 手順2：〇〇する
![手順2](画像URL)
説明文

# 注意事項

条件:
- Markdown形式で出力してください
- 画面から分かる内容を中心にしてください
- 推測しすぎないでください
- 画像URLは必ず本文内に使ってください
"""

    response = client.models.generate_content(
        model="gemini-2.5-pro",
        contents=[uploaded_file, prompt]
    )

    return jsonify({
        "manual": response.text,
        "images": image_urls
    })


def extract_frames(video_path, work_id, interval_sec=5, max_frames=10):
    cap = cv2.VideoCapture(video_path)

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

        # 公開URLとして使う
        blob.make_public()

        urls.append(blob.public_url)

    return urls
