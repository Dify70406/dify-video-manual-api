@app.route("/manual", methods=["POST"])
def manual():
    try:
        data = request.get_json(silent=True)

        text = ""
        if data and "text" in data and data["text"]:
            text = data["text"]
        else:
            # fallback（超重要）
            text = "テスト\n1. サンプル手順"

        from docx import Document
        doc = Document()

        for line in text.split("\n"):
            line = line.strip()
            if not line:
                continue
            doc.add_paragraph(line)

        import uuid
        filename = f"{uuid.uuid4()}.docx"
        file_path = f"/tmp/{filename}"
        doc.save(file_path)

        from flask import send_file

        return send_file(
            file_path,
            as_attachment=True,
            download_name="manual.docx",
            mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )

    except Exception as e:
        return {
            "error": str(e)
        }, 500
