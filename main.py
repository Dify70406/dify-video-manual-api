from flask import Flask, request, jsonify
import re
from youtube_transcript_api import YouTubeTranscriptApi

app = Flask(__name__)

@app.route("/")
def hello():
    return "OK"


# ✅ YouTube ID抽出（Shorts対応）
def extract_video_id(url):
    match = re.search(r"(?:v=|youtu\.be/|shorts/)([^&?/]+)", url)
    return match.group(1) if match else None


# ✅ 字幕取得（安全版）
def get_transcript(video_id):
    try:
        transcripts = YouTubeTranscriptApi.list_transcripts(video_id)

        # 自動字幕も含めて1つ取得
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

        # ✅ fallback
        if not text:
            text = "字幕が取得できませんでした"

        # ✅ ここが重要（JSON返す）
        return jsonify({
            "text": text
        })

    except Exception as e:
        return jsonify({
            "error": str(e)
        }), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
