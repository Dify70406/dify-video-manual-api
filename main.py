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


# ✅ YouTubeダウンロード（軽量・ffmpeg不要）
def download_video(url, video_path):
    ydl_opts = {
        'format': 'worst[height<=360]',  # ✅ 軽量最優先
        'outtmpl': video_path,
        'quiet': True,
        'noplaylist': True
    }
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

        # ✅ ダウンロード処理
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

        # ✅ ファイル確認
        if not os.path.exists(video_path):
            raise Exception("動画ファイルが存在しません")

        size = os.path.getsize(video_path)
        print("Video size:", size)

        if size < 1024 * 100:
            raise Exception("動画が小さすぎる（ダウンロード失敗）")

        # ✅ フレーム抽出（軽量）
        frame_paths = extract_frames(
            video_path,
            work_id,
            interval_sec=10,
            max_frames=3
        )

        print("Frames:", len(frame_paths))

        image_urls = upload_frames(frame_paths, work_id)

        # ✅ Gemini処理
        print("Gemini upload start")
        uploaded_file = client.files.upload(file=video_path)

        while uploaded_file.state.name == "PROCESSING":
            time.sleep(5)
            uploaded_file = client.files.get(name=uploaded_file.name)

        if uploaded_file.state.name != "ACTIVE":
            raise Exception("Gemini動画処理失敗")

        print("Gemini ready")

        prompt = f"""
この動画を分析して、簡潔な操作手順を作成してください。

画像:
{json.dumps(image_urls, ensure_ascii=False)}

Markdown形式で出力。
画像URLを必ず使う。
"""

        response = client.models.generate_content(
            model="gemini-2.5-pro",
            contents=[uploaded_file, prompt]
        )

        print("=== SUCCESS ===")

        return jsonify({
            "manual": response.text,
            "images": image_urls
        })

    except Exception as e:
        # ✅ ← ここが今回の最重要修正ポイント
        print("ERROR:", str(e))

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
