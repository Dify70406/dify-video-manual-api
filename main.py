import os
import time
import requests
import traceback
import subprocess
import re
import glob
import base64

from flask import Flask, request, jsonify, send_file
from google import genai
from docx import Document
from docx.shared import Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH

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
    file_name = data.get("file_name")
    content_b64 = data.get("content")

    print("[manual] request received")
    print(f"[manual] video_url exists={bool(video_url)}")
    print(f"[manual] file_name={file_name}")
    print(f"[manual] content exists={content_b64 is not None}")
    print(f"[manual] content length={len(content_b64) if content_b64 else 0}")

    try:
        # ① 従来どおり video_url が来た場合
        if video_url:
            print("[manual] path=video_url")

            if is_youtube_url(video_url):
                print("[manual] detected youtube url")
                subtitle_text = get_youtube_subtitle(video_url)

                prompt = f"""
以下はYouTube動画の字幕です。
この字幕をもとに、操作手順書を作成してください。

必ず以下の形式だけで出力してください。
前置き、あいさつ、補足説明は禁止です。
「承知しました」「以下に示します」などの文章は出力しないでください。

字幕:
{subtitle_text}

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

条件:
- Markdown形式で出力してください
- 上記の見出し以外は出力しないでください
- 前置きや会話文は禁止です
- 字幕から分かる内容だけを使ってください
- 推測しすぎないでください
"""

                response = client.models.generate_content(
                    model="gemini-2.5-pro",
                    contents=prompt
                )

                manual_text = normalize_manual_text(response.text)
                print(f"[manual] generated manual length={len(manual_text)}")

                return jsonify({
                    "manual": manual_text,
                    "source": "youtube_subtitle"
                })

            else:
                print("[manual] downloading video from url")
                work_id = str(int(time.time()))
                video_path = f"/tmp/{work_id}.mp4"

                r = requests.get(video_url, timeout=300)
                r.raise_for_status()

                with open(video_path, "wb") as f:
                    f.write(r.content)

                print(f"[manual] downloaded video_path={video_path}")
                print(f"[manual] downloaded video_size={os.path.getsize(video_path)}")

                manual_text = analyze_video_file(video_path)
                manual_text = normalize_manual_text(manual_text)
                print(f"[manual] generated manual length={len(manual_text)}")

                return jsonify({
                    "manual": manual_text,
                    "source": "video_url"
                })

        # ② Power Automate から Base64 動画が来た場合
        elif file_name and content_b64:
            print("[manual] path=sharepoint_file")
            ext = os.path.splitext(file_name)[1].lower()
            if not ext:
                ext = ".mp4"

            work_id = str(int(time.time()))
            video_path = f"/tmp/{work_id}{ext}"

            # data:video/...;base64,... のような形式にも対応
            if "," in content_b64:
                content_b64 = content_b64.split(",", 1)[1]

            video_bytes = base64.b64decode(content_b64)

            with open(video_path, "wb") as f:
                f.write(video_bytes)

            print(f"[manual] saved video_path={video_path}")
            print(f"[manual] saved video_size={os.path.getsize(video_path)}")

            manual_text = analyze_video_file(video_path)
            manual_text = normalize_manual_text(manual_text)
            print(f"[manual] generated manual length={len(manual_text)}")

            return jsonify({
                "manual": manual_text,
                "source": "sharepoint_file",
                "file_name": file_name
            })

        else:
            print("[manual] invalid request: missing video_url or file_name+content")
            return jsonify({
                "error": "video_url または file_name + content が必要です"
            }), 400

    except Exception as e:
        print("[manual] exception occurred")
        print(traceback.format_exc())
        return jsonify({
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


def analyze_video_file(video_path: str) -> str:
    print(f"[analyze_video_file] uploading video_path={video_path}")

    uploaded_file = client.files.upload(file=video_path)
    print(f"[analyze_video_file] uploaded name={uploaded_file.name}")
    print(f"[analyze_video_file] initial state={uploaded_file.state.name}")

    while uploaded_file.state.name == "PROCESSING":
        print("[analyze_video_file] file still processing...")
        time.sleep(5)
        uploaded_file = client.files.get(name=uploaded_file.name)
        print(f"[analyze_video_file] current state={uploaded_file.state.name}")

    if uploaded_file.state.name != "ACTIVE":
        raise Exception("Gemini video processing failed")

    prompt = """
この動画を分析して操作手順書を作成してください。

必ず以下の形式だけで出力してください。
前置き、あいさつ、補足説明は禁止です。
「承知しました」「以下に示します」などの文章は出力しないでください。

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

条件:
- Markdown形式で出力してください
- 上記の見出し以外は出力しないでください
- 前置きや会話文は禁止です
- 動画に具体的な操作手順が含まれていない場合は、その旨を簡潔に記載してください
"""

    response = client.models.generate_content(
        model="gemini-2.5-pro",
        contents=[
            uploaded_file,
            prompt
        ]
    )

    print(f"[analyze_video_file] response length={len(response.text) if response.text else 0}")
    return response.text


@app.route("/word", methods=["POST"])
def word():
    try:
        data = request.get_json(silent=True) or {}

        text = data.get("text", "")
        file_name = data.get("file_name")
        content_b64 = data.get("content")

        print("[word] request received")
        print(f"[word] file_name={file_name}")
        print(f"[word] text_length={len(text) if text else 0}")
        print(f"[word] content_exists={content_b64 is not None}")
        print(f"[word] content_length={len(content_b64) if content_b64 else 0}")

        if not text:
            text = "手順を生成できませんでした"

        text = normalize_manual_text(text)
        print(f"[word] normalized_text_length={len(text)}")

        doc_path = f"/tmp/manual_{int(time.time())}.docx"
        screenshot_paths = []

        # 動画が渡されていればスクリーンショットを抽出
        if file_name and content_b64:
            ext = os.path.splitext(file_name)[1].lower()
            if not ext:
                ext = ".mp4"

            work_id = str(int(time.time()))
            video_path = f"/tmp/word_src_{work_id}{ext}"

            if "," in content_b64:
                content_b64 = content_b64.split(",", 1)[1]

            video_bytes = base64.b64decode(content_b64)

            with open(video_path, "wb") as f:
                f.write(video_bytes)

            print(f"[word] saved video_path={video_path}")
            print(f"[word] video_size={os.path.getsize(video_path)}")

            screenshot_paths = extract_screenshots(
                video_path=video_path,
                work_id=work_id,
                max_shots=4,
            )

        print(f"[word] screenshot_count={len(screenshot_paths)}")
        print(f"[word] screenshot_paths={screenshot_paths}")

        doc = build_manual_doc(text, screenshot_paths)
        doc.save(doc_path)
        print(f"[word] doc saved: {doc_path}, size={os.path.getsize(doc_path)}")

        return send_file(
            doc_path,
            as_attachment=True,
            download_name="manual.docx",
            mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )

    except Exception as e:
        print("[word] exception occurred")
        print(traceback.format_exc())
        return jsonify({
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


def build_manual_doc(text: str, screenshot_paths: list[str]) -> Document:
    print("[build_manual_doc] start")
    print(f"[build_manual_doc] screenshot_count={len(screenshot_paths)}")

    doc = Document()
    doc.add_heading("操作手順書", level=1)

    lines = [line.rstrip() for line in text.splitlines()]
    blocks = parse_manual_blocks(lines)

    print(f"[build_manual_doc] block_count={len(blocks)}")
    for i, block in enumerate(blocks, start=1):
        print(
            f"[build_manual_doc] block{i}: "
            f"type={block['type']}, title={block['title']}, body_lines={len(block['body'])}"
        )

    shot_index = 0
