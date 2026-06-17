from flask import Flask, request, send_file, jsonify
from docx import Document
import uuid
from youtube_transcript_api import YouTubeTranscriptApi
import re

app = Flask(__name__)

@app.route("/")
def hello():
    return "OK"


# ✅ YouTube URLからID抽出
def extract_video_id(url):
    match = re.search(r"(?:v=|youtu\.be/)([^&]+)", url)
    return match.group(1) if match else None


# ✅ 字幕取得（安全版）
def get_transcript(video_id):
    try:
        transcript = YouTubeTranscriptApi.get_transcript(video_id)
        text = "\n".join([t["text"] for t in transcript])
        return text
    except Exception:
        return "字幕が取得できませんでした"


@app.route("/manual", methods=["GET", "POST"])
def manual():
    try:
        data = request.get_json(silent=True)

        text = ""
        video_id = None

        if data:
            # ✅ YouTube対応（両対応）
            if data.get("youtube_url"):
                video_id = extract_video_id(data["youtube_url"])
            elif data.get("video_url"):
                video_id = extract_video_id(data["video_url"])

            if video_id:
                text = get_transcript(video_id)

            # ✅ フォールバック（テキスト）
            if not text and data.get("text"):
                text = data.get("text")

        if not text:
            text = "1. サンプル手順\n説明文です"

        # ✅ Word生成
        doc = Document()

        for line in text.split("\n"):
            line = line.strip()
            if not line:
                continue
            doc.add_paragraph(line)

        filename = f"{uuid.uuid4()}.docx"
        file_path = f"/tmp/{filename}"
        doc.save(file_path)

        return send_file(
            file_path,
            as_attachment=True,
            download_name="manual.docx",
            mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
