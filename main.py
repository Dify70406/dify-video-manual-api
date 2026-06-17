@app.route("/manual", methods=["POST"])
def manual():
    return jsonify({
        "file_url": "https://example.com/test.docx"
    })
