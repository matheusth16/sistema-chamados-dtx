from app import create_app

app = create_app()
app.run(debug=True, host="127.0.0.1", port=5000, use_reloader=False)
