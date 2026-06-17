from flask import Flask, request, send_file, jsonify
from docx import Document
import uuid
import re
import os
from youtube_transcript_api import YouTubeTranscriptApi
import yt_dlp
from openai import OpenAI

app = Flask(__name__)

client = OpenAI()  # APIキーは環境変数


@app.route("/")
def hello():
    return "OK"


# ✅ YouTube ID抽出
def extract_video_id(url):
    match = re.search(r"(?:v=|youtu\.be/)([^&]+)", url)
    return match.group(1) if match else None


# ✅ 字幕取得
def get_transcript(video_id):
    try:
        transcript = YouTubeTranscriptApi.get_transcript(video_id)
        return "\n".join([t["text"] for t in transcript])
    except:
        return None


# ✅ 音声ダウンロード
def download_audio(url, output_path):
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': output_path,
        'quiet': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])


# ✅ Whisper API
def speech_to_text(file_path):
    with open(file_path, "rb") as f:
        transcript = client.audio.transcriptions.create(
            file=f,
            model="gpt-4o-mini-transcribe"
        )
    return transcript.text


@app.route("/manual", methods=["GET", "POST"])
def manual():
    try:
        data = request.get_json(silent=True)

        text = None

        if data:
            url = data.get("youtube_url") or data.get("video_url")

            # ✅ YouTube処理
            if url:
                video_id = extract_video_id(url)

                # ① 字幕取得
                text = get_transcript(video_id)

                # ② 字幕ダメなら音声解析
                if not text:
                    audio_path = "/tmp/audio.%(ext)s"
                    download_audio(url, audio_path)

                    # 実ファイル探す
                    for file in os.listdir("/tmp"):
                        if file.startswith("audio"):
                            full_path = f"/tmp/{file}"
                            text = speech_to_text(full_path)
                            break

            # ✅ テキスト fallback
            if not text and data.get("text"):
                text = data.get("text")

        if not text:
            text = "文字起こしできませんでした"

        # ✅ Word生成
        doc = Document()
        for line in text.split("\n"):
            if line.strip():
                doc.add_paragraph(line)

        filename = f"{uuid.uuid4()}.docx"
        file_path = f"/tmp/{filename}"
        doc.save(file_path)

        return send_file(
            file_path,
            as_attachment=True,
            download_name="manual.docx"
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
