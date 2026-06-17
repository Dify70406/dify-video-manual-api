# ✅ 動画取得をスキップ
video_path = None

# ✅ 画像スキップ（テスト時）
image_urls = []

# ✅ テスト用transcript（そのまま）
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
    "images": image_urls
})
