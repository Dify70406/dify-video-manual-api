import os
import time
import requests
import traceback
import subprocess
import re
import glob

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

    try:
        if is_youtube_url(video_url):
            subtitle_text = get_youtube_subtitle(video_url)

            prompt = f"""
以下はYouTube動画の字幕です。
この字幕をもとに、操作手順書を作成してください。

字幕:
{subtitle_text}

出力形式:

# 概要

# 操作手順

## 手順1
説明

## 手順2
説明

## 手順3
説明

# 注意事項

条件:
- Markdown形式で出力してください
- 字幕から分かる内容だけを使ってください
- 推測しすぎないでください
"""

            response = client.models.generate_content(
                model="gemini-2.5-pro",
                contents=prompt
            )

            return jsonify({
                "manual": response.text,
                "source": "youtube_subtitle"
            })

        else:
            work_id = str(int(time.time()))
            video_path = f"/tmp/{work_id}.mp4"

            r = requests.get(video_url, timeout=300)
            r.raise_for_status()

            with open(video_path, "wb") as f:
                f.write(r.content)

            uploaded_file = client.files.upload(file=video_path)

            while uploaded_file.state.name == "PROCESSING":
                time.sleep(5)
                uploaded_file = client.files.get(name=uploaded_file.name)

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
                "manual": response.text,
                "source": "video"
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


def is_youtube_url(url):
    return "youtube.com" in url or "youtu.be" in url


def get_youtube_subtitle(url):
    cleanup_subtitle_files()

    outtmpl = "/tmp/youtube_subtitle"

    cmd = [
        "yt-dlp",
        "--skip-download",
        "--write-subs",
        "--write-auto-subs",
        "--sub-langs",
        "ja,en",
        "--sub-format",
        "vtt",
        "-o",
        outtmpl,
        url
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=120
    )

    if result.returncode != 0:
        return f"""
字幕取得に失敗しました。

yt-dlp error:
{result.stderr}
"""

    files = glob.glob("/tmp/youtube_subtitle*.vtt")

    if not files:
        return "字幕ファイルが見つかりませんでした。"

    subtitle_text = ""

    for file in files:
        with open(file, "r", encoding="utf-8", errors="ignore") as f:
            subtitle_text += "\n" + vtt_to_text(f.read())

    if not subtitle_text.strip():
        return "字幕が空でした。"

    return subtitle_text


def cleanup_subtitle_files():
    for file in glob.glob("/tmp/youtube_subtitle*"):
        try:
            os.remove(file)
        except Exception:
            pass


def vtt_to_text(vtt):
    lines = vtt.splitlines()
    texts = []

    for line in lines:
        line = line.strip()

        if not line:
            continue

        if line == "WEBVTT":
            continue

        if "-->" in line:
            continue

        if re.match(r"^\d+$", line):
            continue

        line = re.sub(r"<[^>]+>", "", line)
        line = line.strip()

        if line:
            texts.append(line)

    return "\n".join(texts)
