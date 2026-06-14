import os
import time
import requests
from flask import Flask, request, jsonify
from google import genai

app = Flask(__name__)

client = genai.Client(
    api_key=os.environ["GEMINI_API_KEY"]
)

@app.route("/")
def hello():
    return "Video Manual API OK"

@app.route("/manual", methods=["POST"])
def manual():

    data = request.get_json()

    video_url = data.get("video_url")

    if not video_url:
        return jsonify({"error":"video_url is required"}),400

    video_file = "/tmp/video.mp4"

    r = requests.get(video_url)

    with open(video_file,"wb") as f:
        f.write(r.content)

    uploaded_file = client.files.upload(
        file=video_file
    )

    while uploaded_file.state.name == "PROCESSING":
        time.sleep(5)
        uploaded_file = client.files.get(
            name=uploaded_file.name
        )

    response = client.models.generate_content(
        model="gemini-2.5-pro",
        contents=[
            uploaded_file,
            """
動画を分析して手順書を作成してください。

出力形式

# 概要

# 操作手順

1.
2.
3.

# 注意事項
"""
        ]
    )

    return jsonify({
        "manual": response.text
    })
