import os
import time
import json
import cv2
import requests
import traceback
from flask import Flask, request, jsonify, send_file
from google import genai
from docx import Document

app = Flask(__name__)

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

client = genai.Client(api_key=GEMINI_API_KEY)


@app.route("/")
def hello():
    return "Video Manual API OK"


@app.route("/manual", methods=["POST"])
def manual():
    data = request.get_json(silent=True) or {}
    video_url = data.get("video_url")

    if not video_url:
        return jsonify({"error": "video_url is required"}), 400

    work_id = str(int(time.time()))
    video_path = f"/tmp/{work_id}.mp4"

    try:
        # 動画をダウンロード
        r = requests.get(video_url, timeout=180)
        r.raise_for_status()

        with open(video_path, "wb") as f:
            f.write(r.content)

        # 切り分けのため、Cloud Storageへの画像アップロードは一時停止
        # frame_paths = extract_frames(video_path, work_id)
        # image_urls = upload_frames(frame_paths, work_id)

        frame_paths = []
        image_urls = []

        uploaded_file = client.files.upload(file=video_path)

        while uploaded_file.state.name == "PROCESSING":
            time.sleep(5)
            uploaded_file = client.files.get(name=uploaded_file.name)

        if uploaded_file.state.name != "ACTIVE":
            return jsonify({"error": "Gemini video processing failed"}), 500

        prompt = f"""
この動画を分析して、操作手順書を作成してください。

出力形式:
# 概要

# 操作手順

## 手順1：〇〇する
説明文

## 手順2：〇〇する
説明文

# 注意事項

条件:
- Markdown形式で出力してください
- 画面から分かる内容を中心にしてください
- 推測しすぎないでください
"""

        response = client.models.generate_content(
            model="gemini-2.5-pro",
            contents=[uploaded_file, prompt]
        )

        return jsonify({
            "manual": response.text,
            "images": image_urls
        })

    except Exception as e:
        return jsonify({
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@app.route("/word", methods=["POST"])
def word():
    try:
        data = request.get_json(silent=True) or {}
        text = data.get("text", "")

        if not text:
            text = "手順を生成できませんでした"

        doc_path = f"/tmp/manual_{int(time.time())}.docx"

        doc = Document()
        doc.add_heading("操作手順書", level=1)

        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue

            if line.startswith("# "):
                doc.add_heading(line.replace("# ", ""), level=1)
            elif line.startswith("## "):
                doc.add_heading(line.replace("## ", ""), level=2)
            elif line.startswith("### "):
                doc.add_heading(line.replace("### ", ""), level=3)
            else:
                doc.add_paragraph(line)

        doc.save(doc_path)

        return send_file(
            doc_path,
            as_attachment=True,
            download_name="manual.docx",
            mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )

    except Exception as e:
        return jsonify({
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


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
