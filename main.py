from flask import Flask, request, jsonify
from docx import Document
import uuid
import os

app = Flask(__name__)

# デバッグ用
@app.route("/")
def hello():
    return "OK"


@app.route("/manual", methods=["POST"])
def manual():
    data = request.get_json(silent=True)

    if not data:
        return jsonify({"error": "no input"})

    text = data.get("text", "")

    # Word生成
    doc = Document()

    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue

        if line[0].isdigit() and "." in line:
            p = doc.add_paragraph()
