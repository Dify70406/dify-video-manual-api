@app.route("/manual", methods=["POST"])
def manual():
    return {
        "file_url": "https://example.com/test.docx"
    }
