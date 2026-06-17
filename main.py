import os
import time
import requests
import traceback
import subprocess

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

        # -----------------------------
        # YouTube動画
        # -----------------------------
        if (
            "youtube.com" in video_url
            or "youtu.be" in video_url
        ):

            cmd = [
                "yt-dlp",
                "-f",
                "mp4",
                "-o",
                video_path,
                video_url,
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True
            )

            if result.returncode != 0:
                return jsonify({
                    "error": "YouTube download failed",
                    "detail": result.stderr
                }), 500

        # -----------------------------
        # 通常MP4
        # -----------------------------
        else:

            r = requests.get(video_url, timeout=300)
            r.raise_for_status()

            with open(video_path, "wb") as f:
                f.write(r.content)

        # -----------------------------
        # Geminiへアップロード
        # -----------------------------
        uploaded_file = client.files.upload(
            file=video_path
        )

        while uploaded_file.state.name == "PROCESSING":
            time.sleep(5)

            uploaded_file = client.files.get(
                name=uploaded_file.name
            )

        if uploaded_file.state.name != "ACTIVE":
            return jsonify({
                "error": "Gemini video processing failed"
            }), 500

        prompt = """
この動画を分析して操作手順書を作成してください。

出力形式:

# 概要

概要説明

# 操作手順

## 手順1
説明

## 手順2
説明

## 手順3
説明

# 注意事項

Markdown形式で出力してください。
"""

        response = client.models.generate_content(
            model="gemini-2.5-pro",
            contents=[
                uploaded_file,
                prompt
            ]
        )

        return jsonify({
            "manual": response.text
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

        doc.add_heading(
            "操作手順書",
            level=1
        )

        for line in text.splitlines():

            line = line.strip()

            if not line:
                continue

            if line.startswith("# "):
                doc.add_heading(
                    line.replace("# ", ""),
                    level=1
                )

            elif line.startswith("## "):
                doc.add_heading(
                    line.replace("## ", ""),
                    level=2
                )

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
