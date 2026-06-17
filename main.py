from flask import Flask, request, jsonify, send_file
from docx import Document
import uuid
from youtube_transcript_api import YouTubeTranscriptApi
import re

app = Flask(__name__)

@app.route("/")
def hello():
    return "OK"


# ✅ YouTube URL → transcript取得
def extract_video_id(url):
    match = re.search(r"(?:v=|youtu\.be/)([^&]+)", url)
    return match.group(1) if match else None


def get_transcript(video_id):
    transcript = YouTubeTranscriptApi.get_transcript(video_id)
    text = "\n".join([t["text"] for t in transcript])
    return text


@app.route("/manual", methods=["GET", "POST"])
def manual():
    try:
        data = request.get_json(silent=True)

        text = ""

        if data:
            # ✅ ケース①：YouTube URL
            if "youtube_url" in data:
                video_id = extract_video_id(data["youtube_url"])
                if video_id:
                    text = get_transcript(video_id)

            # ✅ ケース②：通常テキスト
            elif "text" in data:
                text = data.get("text", "")

        if not text:
            text = "1. サンプル手順\n説明文です"

        # ✅ Word作成
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
