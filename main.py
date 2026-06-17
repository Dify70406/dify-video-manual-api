from flask import Flask, request, send_file, jsonify
from docx import Document
import uuid
import re
import os
from youtube_transcript_api import YouTubeTranscriptApi

app = Flask(__name__)

@app.route("/")
def hello():
    return "OK"


# ✅ YouTube ID抽出（修正版：amp削除）
def extract_video_id(url):
    match = re.search(r"(?:v=|youtu\.be/|shorts/)([^&?/]+)", url)
    return match.group(1) if match else None


# ✅ 字幕取得
def get_transcript(video_id):
    try:
        transcripts = YouTubeTranscriptApi.list_transcripts(video_id)

        # 最初に取れる字幕を取得
        for t in transcripts:
            data = t.fetch()
            return "\n".join([x["text"] for x in data])

    except Exception as e:
        print(f"字幕取得エラー: {e}")
        return None


@app.route("/manual", methods=["GET", "POST"])
def manual():
    try:
        data = request.get_json(silent=True)

        text = None
        video_id = None

        if data:
            url = data.get("youtube_url") or data.get("video_url")

            if url:
                video_id = extract_video_id(url)

            # ✅ 字幕取得
            if video_id:
                text = get_transcript(video_id)

            # ✅ fallback（LLMの結果を使う）
            if not text and data.get("text"):
                text = data.get("text")

        # ✅ 最終fallback
        if not text:
            text = "手順を生成できませんでした"

        # ✅ Word作成
        doc = Document()

        for line in text.split("\n"):
            line = line.strip()
            if line:
                doc.add_paragraph(line)

        # ✅ 画像追加（あれば）
        image_path = "/app/sample.png"
        if os.path.exists(image_path):
            doc.add_paragraph("")
            doc.add_picture(image_path)

        # ✅ ファイル保存
        filename = f"{uuid.uuid4()}.docx"
        file_path = f"/tmp/{filename}"
        doc.save(file_path)

        # ✅ ★これが一番重要（Word返す）
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
