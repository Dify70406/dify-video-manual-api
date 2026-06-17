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


# ✅ YouTube ID抽出
def extract_video_id(url):
    match = re.search(r"(?:v=|youtu\.be/)([^&]+)", url)
    return match.group(1) if match else None


# ✅ 安全な字幕取得
def get_transcript(video_id):
    try:
        transcript = YouTubeTranscriptApi.get_transcript(video_id)
        return "\n".join([t["text"] for t in transcript])
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
            # ✅ YouTube URL対応（両方OK）
            url = data.get("youtube_url") or data.get("video_url")

            if url:
                video_id = extract_video_id(url)

            # ✅ 字幕取得
            if video_id:
                text = get_transcript(video_id)

            # ✅ fallback（テキスト）
            if not text and data.get("text"):
                text = data.get("text")

        # ✅ 最終fallback
        if not text:
            text = "1. サンプル手順\n説明文です"

        # ✅ Word作成
        doc = Document()

        # --- テキスト ---
        for line in text.split("\n"):
            line = line.strip()
            if not line:
                continue
            doc.add_paragraph(line)

        # ✅ 画像追加（ここ今回のポイント）
        image_path = "/app/sample.png"

        if os.path.exists(image_path):
            doc.add_paragraph("")  # 空行
            doc.add_picture(image_path)

        # ✅ ファイル保存
        filename = f"{uuid.uuid4()}.docx"
        file_path = f"/tmp/{filename}"
        doc.save(file_path)

        # ✅ ダウンロード返却
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
