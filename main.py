from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route("/")
def hello():
    return "OK"


@app.route("/manual", methods=["POST"])
def manual():
    data = request.get_json(silent=True)

    if not data:
        return jsonify({"error": "no input"})

    # ✅ 完全ダミー（ここ重要）
    transcript = """
ログイン画面を開きます。
ユーザーIDを入力します。
パスワードを入力します。
ログインボタンをクリックします。
設定画面を開きます。
保存ボタンをクリックします。
"""

    return jsonify({
        "transcript": transcript,
        "images": []
    })
