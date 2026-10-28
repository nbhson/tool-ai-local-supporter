from app_factory import create_app

app = create_app()

if __name__ == '__main__':
    print("🚀 Starting AI Local Support")
    print("📁 Modules: Document Analysis + Code Analysis")
    print("🌐 Open http://127.0.0.1:5001")
    app.run(host='0.0.0.0', port=5001, debug=False)
