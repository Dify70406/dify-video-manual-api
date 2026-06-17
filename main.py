from flask import Flask, request, jsonify

app = Flask(__name__)

# 動作確認用（ブラウザで開く）
@app.route("/")
def hello():
    return "OK"


# ★ difyから叩くAPI
@app.route("/manual", methods=["GET", "POST"])
def manual():
    try:
        # JSON取得（失敗しても落ちない）
        data = request.get_json(silent=True)

        text = ""
        if data and "text" in data:
            text = data.get("text", "")

        # とりあえずダミー返す
        return jsonify({
            "file_url": "https://example.com/test.docx",
            "received_text_length": len(text)
        })

    except Exception as e:
        return jsonify({
            "error": str(e)
        }), 500


if __name__ == "__main__":
    # Cloud Runはこのポート必須
    app.run(host="0.0.0.0", port=8080)
