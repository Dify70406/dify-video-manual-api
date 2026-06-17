from flask import Flask, request, send_file, jsonify
from docx import Document
import uuid

app = Flask(__name__)

@app.route("/")
def hello():
    return "OK"

@app.route("/manual", methods=["GET", "POST"])
def manual():
    try:
        data = request.get_json(silent=True)

        text = ""
        if data and "text" in data:
            text = data.get("text", "")

        if not text:
            text = "1. サンプル手順\n説明文です"

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
