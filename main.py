from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route("/")
def hello():
    return "OK"

@app.route("/manual", methods=["POST"])
def manual():
    return jsonify({
        "file_url": "https://example.com/test.docx"
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
