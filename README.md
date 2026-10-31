# AI Local Support

WebUI phân tích tài liệu và code sử dụng **Ollama** (AI local) với hỗ trợ đa ngôn ngữ (Tiếng Việt/Tiếng Anh).

---

## 📖 Tài liệu hướng dẫn (Documentation)

- 🚀 **[Hướng dẫn Cài đặt & Khắc phục sự cố](INSTALLATION.md)**: Chi tiết cách cài đặt các thành phần phụ thuộc, tải model Ollama, thiết lập Redis và giải quyết các lỗi thường gặp trên macOS và Windows.
- 📐 **[Tài liệu Kiến trúc Hệ thống](ARCHITECTURE.md)**: Giải thích chi tiết về sơ đồ kiến trúc, các design pattern áp dụng, cấu trúc thư mục dự án, cấu trúc cơ sở dữ liệu và các API endpoints của hệ thống.
- 🤖 **[Đặc tả kỹ năng AI Engineering](AI_ENGINEERING.md)**: Bảng đối chiếu và giải thích chi tiết cách áp dụng 15 kỹ năng/kỹ thuật AI Engineering vào cấu trúc mã nguồn của hệ thống.
- ⚡ **[So sánh hiệu năng: CLI vs. App](OLLAMA_CLI_VS_APP.md)**: Giải thích tại sao chạy Ollama qua dòng lệnh nhanh hơn qua giao diện App/Web và cách tối ưu hóa.

---

## 🚀 Tính năng chính

### 📄 Phân tích Tài liệu
- **Upload file**: Hỗ trợ PDF, DOCX, TXT, MD, CSV, JSON, XML, YAML
- **Hình ảnh**: Hỗ trợ PNG, JPG, JPEG, GIF, BMP, TIFF, WEBP
- **Vision Model**: Phân tích ảnh trực tiếp với qwen2.5-vl, llava, moondream
- **OCR Fallback**: Tesseract OCR cho model không hỗ trợ vision
- 💬 **Chat với tài liệu**: Đặt câu hỏi về nội dung, AI trả lời dựa trên tài liệu
- 🎯 **Câu hỏi gợi ý**: Tóm tắt, điểm chính, kết luận
- 🔍 **Hybrid RAG Search**: Kết hợp vector similarity (fastembed) + keyword BM25 search với Reciprocal Rank Fusion
- 📝 **Code-aware Chunking**: Tự động nhận diện và phân mảnh code theo ranh giới function/class

### 💻 Phân tích Code
- **Paste code**: Hỗ trợ mọi ngôn ngữ lập trình
- 🔍 **Phân tích cú pháp**: Ngôn ngữ, mục đích, thành phần chính
- ⚠️ **Phát hiện lỗi**: Vấn đề tiềm ẩn và cải tiến
- ⚡ **Đề xuất tối ưu**: Cải thiện performance và chất lượng
- 💬 **Chat về code**: Đặt câu hỏi chi tiết về logic

### 📁 Dự án (Project Workspace Agent)
- 🤖 **AI Coding Agent**: Hoạt động như một Software Engineer thực thụ dựa trên mô hình **ReAct (Reasoning and Action)**.
- ⚙️ **Tự động hóa hoàn toàn (Auto-planning)**: AI tự động lên kế hoạch và thực thi công việc mà không cần người dùng chọn file thủ công.
- 🛠️ **Hệ thống 12 Công cụ cục bộ**:
  - `READ_FILE` / `WRITE_FILE` / `EDIT_FILE` — Đọc, ghi, chỉnh sửa file
  - `LIST_DIR` / `SEARCH_FILES` / `REGEX_SEARCH` — Duyệt và tìm kiếm
  - `RUN_COMMAND` / `RUN_TESTS` / `LINT_CODE` — Chạy lệnh, test, lint
  - `GIT_DIFF` / `GIT_LOG` — Xem thay đổi Git
  - `FINISH` — Kết thúc tác vụ
- 📊 **File Importance Scoring**: Tự động sắp xếp file theo mức độ quan trọng trong cây thư mục.
- 🔄 **Realtime Interactive UI**: Timeline hiển thị chi tiết các bước suy nghĩ (thoughts), tool gọi và logs, kèm theo khả năng cập nhật code tự động lên Editor Monaco.

### 💬 Trò chuyện tự do
- **Hỏi đáp đa năng**: Trò chuyện tự do với AI không cần ngữ cảnh tài liệu hoặc mã nguồn
- 🎯 **Câu hỏi gợi ý**: Gợi ý nhanh các chủ đề công nghệ, viết lách, kế hoạch du lịch
- 🔄 **Lưu trữ lịch sử**: Lưu trữ lịch sử hội thoại tự động vào SQLite

### 🎨 Giao diện
- 🌐 **Đa ngôn ngữ**: Tiếng Việt / Tiếng Anh
- 🎯 **Đa model**: Chọn bất kỳ model Ollama nào đã cài
- 🎨 **Dark mode**: Giao diện tối, responsive
- 📱 **Drag & drop**: Upload file dễ dàng
- 🧩 **Modular Frontend**: CSS/JS phân theo từng tính năng (chat, doc, project)
- 📊 **Structured Logging**: Hệ thống log màu sắc, chi tiết cho debugging

---

## 🎮 Cách sử dụng nhanh

1. **Phân tích Tài liệu**: Chọn tab "Tài liệu", chọn model/ngôn ngữ, upload file và bắt đầu chat với tài liệu.
2. **Phân tích Code**: Chọn tab "Code", dán đoạn mã nguồn cần phân tích, chọn ngôn ngữ và bấm nút phân tích, sau đó chat để hỏi sâu hơn.
3. **Trò chuyện tự do**: Chọn tab "Trò chuyện", chọn model/ngôn ngữ ở sidebar và bắt đầu trò chuyện trực tiếp không cần ngữ cảnh.
4. **Dự án (Project Workspace)**: Chọn tab "Dự án", nhập đường dẫn tuyệt đối tới thư mục dự án và bắt đầu ra lệnh cho Coding Agent (ví dụ: *"Thêm logging vào file server.py và chạy thử"*).

---

## 🛠 Công nghệ sử dụng

- **Backend**: Python Flask, Celery
- **Frontend**: HTML, CSS, JavaScript (thuần, modular)
- **AI / LLM**: Ollama (Local LLM), FastEmbed (Local CPU-based Embedding)
- **Database**: SQLite (Session history), ChromaDB (Vector DB)
- **Message Broker**: Redis (Celery task queue)
- **OCR Engine**: Tesseract OCR (Fallback)
- **RAG**: Hybrid Search (Vector + BM25 Keyword), Reciprocal Rank Fusion, Code-aware Chunking

---

## 📁 Cấu trúc dự án (Tóm tắt)

```
ai-local-support/
├── app.py                  # Khởi chạy ứng dụng Flask
├── app_factory.py          # Application Factory & Blueprints registration
├── celery_app.py           # Celery App configuration
├── tasks.py                # Celery background tasks
├── config.py               # System configuration (models, RAG, tools...)
├── pyproject.toml          # Cấu hình ruff (lint) & pytest
├── requirements.txt        # Dependencies production
├── requirements-dev.txt    # Dependencies phát triển (pytest, ruff)
├── blueprints/             # API endpoint modules (Controller Layer)
│   ├── doc.py              # Document APIs (upload, RAG chat, status)
│   ├── chat.py             # Code analysis & Free chat APIs
│   └── project.py          # Project workspace & Agent APIs
├── services/               # Business logic & data layers
│   ├── agent_service.py    # ReAct Agent loop engine
│   ├── agent_tool_service.py # 12 Agent tools (Command Pattern)
│   ├── rag_service.py      # Hybrid RAG (Vector + BM25 + fastembed)
│   ├── ollama_service.py   # Ollama API integration
│   ├── extractor_service.py # Document extraction (Strategy & Factory)
│   ├── document_service.py # PDF, Word, OCR processing
│   ├── helper_service.py   # SSE, chat history, path safety utilities
│   ├── logger.py           # Structured colored logger (AILogger)
│   ├── repositories.py     # Database access layer (Repository Pattern)
│   ├── models.py           # SQLAlchemy models (5 tables)
│   ├── database.py         # SQLAlchemy instance
│   └── errors.py           # Custom exceptions
├── static/                 # Frontend assets (modular)
│   ├── css/                # base.css, chat.css, components.css, project.css
│   └── js/                 # chat.js, doc.js, project.js, state.js, diff.min.js
├── templates/
│   └── index.html          # Single Page Application
└── tests/
    ├── test_basic.py       # Pytest regression tests
    ├── test_security.py    # Security tests (command whitelist, upload guard)
    └── test_services.py    # Unit tests cho service layer (RAG, agent tools, tasks)
```

---

## 🧪 Kiểm thử (Testing)

```bash
python3 -m pip install -r requirements-dev.txt

# Chạy toàn bộ test
python3 -m pytest tests/ -q

# Kiểm tra lint
python3 -m ruff check .
```

---

## 📄 License

MIT License

## 👨‍💻 Author

AI Local Support - Powered by Ollama + Flask