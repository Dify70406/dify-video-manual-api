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


# ✅ YouTubeダウンロード（最終版）
def download_video(url):
    ydl_opts = {
        'format': 'best[height<=360]',
        'outtmpl': '/tmp/%(id)s.%(ext)s',
        'quiet': True,
        'noplaylist': True
    }

    print("yt-dlp format:", ydl_opts['format'])

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)

    print("downloaded file:", filename)

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

    video_url = data.get("video_url")
    file_url = data.get("file_url")
    source_url = video_url or file_url

    if not source_url:
        return jsonify({
            "manual": "",
            "images": [],
            "error": "video_url or file_url is required"
        })

    try:
        print("=== START ===")
        print("URL:", source_url)

        # ✅ YouTube判定（最終）
        if "youtube" in source_url:
            print("YouTube download start")
            video_path = download_video(source_url)
            print("YouTube download finished")
        else:
            print("Normal download start")
            temp_path = f"/tmp/{int(time.time())}.mp4"

            r = requests.get(source_url, timeout=180)
            r.raise_for_status()

            with open(temp_path, "wb") as f:
                f.write(r.content)

            video_path = temp_path
            print("Normal download finished")

        # ✅ ファイル検証
        if not os.path.exists(video_path):
            raise Exception("動画ファイルが存在しません")

        size = os.path.getsize(video_path)
        print("size:", size)

        if size < 100000:
            raise Exception("動画サイズが小さすぎる")

        # ✅ フレーム抽出
        work_id = str(int(time.time()))

        frame_paths = extract_frames(
            video_path,
            work_id,
            interval_sec=10,
            max_frames=3
        )

        print("frames:", len(frame_paths))

        if not frame_paths:
            raise Exception("フレーム抽出失敗")

        image_urls = upload_frames(frame_paths, work_id)

        # ✅ Gemini
        print("Gemini upload...")
        uploaded_file = client.files.upload(file=video_path)

        while uploaded_file.state.name == "PROCESSING":
            print("processing...")
            time.sleep(3)
            uploaded_file = client.files.get(name=uploaded_file.name)

        if uploaded_file.state.name != "ACTIVE":
            raise Exception("Gemini処理失敗")

        print("Gemini ready")

        prompt = f"""
この動画の操作手順を作成してください。

画像:
{json.dumps(image_urls, ensure_ascii=False)}

Markdownで出力。
"""

        response = client.models.generate_content(
            model="gemini-2.5-pro",
            contents=[uploaded_file, prompt]
        )

        text = response.text if response.text else ""

        if not text.strip():
            raise Exception("Geminiの出力が空")

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


def extract_frames(video_path, work_id, interval_sec=10, max_frames=3):
    cap = cv2.VideoCapture(video_path)

    if not cap.isOpened():
        raise Exception("動画が開けません")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    frame_interval = int(fps * interval_sec)

    frame_paths = []
    frame_count = 0
    saved_count = 0

    while cap.isOpened() and saved_count < max_frames:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_count % frame_interval == 0:
            frame_path = f"/tmp/{work_id}_{saved_count}.jpg"
            cv2.imwrite(frame_path, frame)
            frame_paths.append(frame_path)
            saved_count += 1

        frame_count += 1

    cap.release()
    return frame_paths


def upload_frames(frame_paths, work_id):
    bucket = storage_client.bucket(BUCKET_NAME)
    urls = []

    for i, frame_path in enumerate(frame_paths):
        blob_name = f"frames/{work_id}_{i}.jpg"
        blob = bucket.blob(blob_name)
        blob.upload_from_filename(frame_path, content_type="image/jpeg")
        urls.append(blob.public_url)

    return urls
