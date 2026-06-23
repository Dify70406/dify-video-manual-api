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

    try:
        # ① 従来どおり video_url が来た場合
        if video_url:
            if is_youtube_url(video_url):
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

                return jsonify({
                    "manual": normalize_manual_text(response.text),
                    "source": "youtube_subtitle"
                })

            else:
                work_id = str(int(time.time()))
                video_path = f"/tmp/{work_id}.mp4"

                r = requests.get(video_url, timeout=300)
                r.raise_for_status()

                with open(video_path, "wb") as f:
                    f.write(r.content)

                manual_text = analyze_video_file(video_path)

                return jsonify({
                    "manual": normalize_manual_text(manual_text),
                    "source": "video_url"
                })

        # ② Power Automate から Base64 動画が来た場合
        elif file_name and content_b64:
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

            manual_text = analyze_video_file(video_path)

            return jsonify({
                "manual": normalize_manual_text(manual_text),
                "source": "sharepoint_file",
                "file_name": file_name
            })

        else:
            return jsonify({
                "error": "video_url または file_name + content が必要です"
            }), 400

    except Exception as e:
        return jsonify({
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


def analyze_video_file(video_path: str) -> str:
    uploaded_file = client.files.upload(file=video_path)

    while uploaded_file.state.name == "PROCESSING":
        time.sleep(5)
        uploaded_file = client.files.get(name=uploaded_file.name)

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

    return response.text


@app.route("/word", methods=["POST"])
def word():
    try:
        data = request.get_json(silent=True) or {}
        text = data.get("text", "")

        if not text:
            text = "手順を生成できませんでした"

        text = normalize_manual_text(text)

        doc_path = f"/tmp/manual_{int(time.time())}.docx"

        doc = Document()
        doc.add_heading("操作手順書", level=1)

        for line in text.splitlines():
            line = line.strip()

            if not line:
                continue

            if line.startswith("# "):
                doc.add_heading(line.replace("# ", "").strip(), level=1)
            elif line.startswith("## "):
                doc.add_heading(line.replace("## ", "").strip(), level=2)
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


def normalize_manual_text(text: str) -> str:
    """
    AIが前置き文を返した場合に、
    最初の # 概要 / # 操作手順 / # 注意事項 / ## 手順1 から始まるように整形する。
    """
    if not text:
        return ""

    text = text.strip()

    # ```markdown ... ``` や ``` ... ``` を除去
    text = text.replace("```markdown", "").replace("```md", "").replace("```", "").strip()

    lines = text.splitlines()

    start_index = None
    heading_patterns = (
        "# 概要",
        "#操作手順",
        "# 操作手順",
        "# 注意事項",
        "## 手順1",
    )

    for i, line in enumerate(lines):
        line = line.strip()
        if any(line.startswith(pattern) for pattern in heading_patterns):
            start_index = i
            break

    if start_index is not None:
        text = "\n".join(lines[start_index:]).strip()

    return text


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

    files = glob.glob("/tmp/youtube_subtitle*.v*t")

   *if not fi*es:
*       re*urn "字幕*ァイルが見*かりません*した。"

   *subtitle_*ext = ""
**   for fi*e in*files:
  *     with*open(file* "r", enc*ding="*tf-8",*errors="i*nore")*as f:
   *       *subtitle_*ext += "\*" + v*t_to_text*f*read())

*   if not*subtitle_*ext.strip*):
      * return "*幕が空でした。"
*    retur* subtitle*text


de* cleanup_*ubtitle_f*les():
  * for file*in glob.g*ob("/tmp/youtube_subtitle*"):
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
