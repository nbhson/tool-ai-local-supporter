# Hướng dẫn Cài đặt & Cấu hình (macOS & Windows)

Tài liệu này hướng dẫn chi tiết cách cài đặt các thành phần phụ thuộc, cấu hình và khởi chạy ứng dụng **AI Local Support** trên hệ điều hành **macOS** và **Windows**, cũng như cách khắc phục các sự cố thường gặp.

---

## 📋 Yêu cầu chung
Trước khi bắt đầu, hãy đảm bảo hệ thống của bạn đã cài đặt các công cụ sau:
- **Python 3.10 - 3.14**
- **Ollama** (Đã chạy ở máy local) -> Tải tại [ollama.com](https://ollama.com)
- **Tesseract OCR** (Tùy chọn, để hỗ trợ nhận diện text trên hình ảnh đối với model không hỗ trợ vision)
  - macOS: `brew install tesseract`
  - Windows: Tải bộ cài đặt `.exe` từ [UB-Mannheim](https://github.com/UB-Mannheim/tesseract/wiki) và thêm đường dẫn `C:\Program Files\Tesseract-OCR` vào biến môi trường `PATH`.

---

## 🍎 Hướng dẫn cài đặt trên macOS

### Bước 1: Clone dự án và khởi tạo môi trường ảo
Mở Terminal và chạy các lệnh sau:
```bash
# Di chuyển vào thư mục dự án
cd ai-local-support

# Khởi tạo môi trường ảo Python
python3 -m venv .venv

# Kích hoạt môi trường ảo
source .venv/bin/activate

# Nâng cấp pip và cài đặt dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

### Bước 2: Tải các model Ollama
Đảm bảo ứng dụng Ollama đang chạy, sau đó kéo model LLM về:
```bash
# Tải model LLM chính để chat & phân tích (ví dụ: qwen2.5-coder)
ollama pull qwen2.5-coder:14b
```
*(Lưu ý: Ứng dụng mặc định sử dụng thư viện **fastembed** để sinh vector embedding trực tiếp trên CPU thông qua ONNX. Thư viện này tự động tải mô hình siêu nhẹ `BAAI/bge-small-en-v1.5` về ở lần chạy đầu tiên, giúp giải phóng GPU và tránh xung đột/tráo đổi model trong VRAM. Bạn không cần tải `nomic-embed-text` qua Ollama nữa trừ khi muốn dùng làm cấu hình dự phòng).*

### Bước 3: Cài đặt và khởi chạy Redis Server
Redis được dùng làm message broker cho Celery. Trên macOS, bạn có hai lựa chọn:

*   **Cách 1: Sử dụng Homebrew (Khuyên dùng)**
    ```bash
    brew install redis
    brew services start redis
    ```
*   **Cách 2: Sử dụng Docker**
    ```bash
    docker run -d -p 6379:6379 --name redis-broker redis:alpine
    ```

### Bước 4: Khởi chạy ứng dụng
Mở **2 tab Terminal** song song (cả 2 đều cần kích hoạt `.venv` trước khi chạy):

- **Terminal 1 (Celery Worker):**
  ```bash
  source .venv/bin/activate
  celery -A tasks.celery worker --loglevel=info --pool=solo
  ```
- **Terminal 2 (Flask Server):**
  ```bash
  source .venv/bin/activate
  python3 app.py
  ```
- **Terminal 3 (Redis Server):**
  ```bash
  source .venv/bin/activate
  redis-cli monitor
  ```
  
Mở trình duyệt truy cập: **http://127.0.0.1:5001**

---

## 💻 Hướng dẫn cài đặt trên Windows

### Bước 1: Khởi tạo môi trường ảo và cài đặt thư viện
Mở **PowerShell** hoặc **Command Prompt (CMD)** dưới quyền Admin và di chuyển vào thư mục dự án:
```powershell
# Di chuyển vào thư mục dự án
cd ai-local-support

# Khởi tạo môi trường ảo Python
python -m venv .venv
```

Kích hoạt môi trường ảo dựa trên trình thông dịch bạn sử dụng:
*   **Trên PowerShell:**
    ```powershell
    # Nếu gặp lỗi Execution Policy, hãy cấp quyền chạy script:
    Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process
    
    # Kích hoạt venv
    .\.venv\Scripts\Activate.ps1
    ```
*   **Trên CMD:**
    ```cmd
    .venv\Scripts\activate.bat
    ```

Sau đó tiến hành cài đặt thư viện:
```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### Bước 2: Tải các model Ollama
Đảm bảo ứng dụng Ollama đang chạy dưới Taskbar, sau đó tải model cần thiết:
```powershell
ollama pull qwen2.5-coder:14b
```
*(Lưu ý: Mô hình nhúng vector embedding hiện tại được chạy trực tiếp bằng **fastembed** trên CPU qua ONNX mà không cần chạy qua Ollama, giúp tăng tốc độ đáng kể).*

### Bước 3: Cài đặt và Khởi chạy Redis Server
Có hai cách thiết lập Redis trên Windows:

*   **Cách 1: Sử dụng WSL 2 (Windows Subsystem for Linux - Khuyên dùng nếu không có Docker)**
    Nếu bạn sử dụng WSL 2 (Ví dụ: Ubuntu), bạn có thể chạy Redis trực tiếp bên trong Linux và kết nối từ Windows:
    
    1. Mở Ubuntu terminal trong WSL và chạy lệnh cài đặt Redis:
       ```bash
       sudo apt update
       sudo apt install redis-server
       ```
    2. **Quan trọng (Cấu hình cho phép kết nối từ Windows):** Do WSL 2 coi kết nối từ Windows host là kết nối từ xa, bạn cần tắt chế độ bảo vệ của Redis.
       
       Mở file cấu hình bằng quyền root:
       ```bash
       sudo nano /etc/redis/redis.conf
       ```
       Tìm dòng `protected-mode yes` (thường ở dòng 111) và sửa thành:
       ```conf
       protected-mode no
       ```
       Lưu file lại (`Ctrl+O` -> `Enter` -> `Ctrl+X`).
       
     3. Khởi động lại dịch vụ Redis trong WSL:
       ```bash
       sudo service redis-server restart
       ```
     4. Để chạy Redis tự động sau này mà không cần đăng nhập Ubuntu, bạn có thể khởi động nhanh từ Windows CMD/PowerShell bằng lệnh:
       ```powershell
       wsl -d Ubuntu redis-server --daemonize yes
       ```

*   **Cách 2: Sử dụng Docker Desktop**
    Nếu đã cài đặt Docker Desktop trên Windows, mở PowerShell và chạy:
    ```powershell
    docker run -d -p 6379:6379 --name redis-broker redis:alpine
    ```

### Bước 4: Khởi chạy ứng dụng
Mở **2 cửa sổ Terminal (CMD hoặc PowerShell)** song song (đảm bảo cả 2 đều đã kích hoạt `.venv`):

- **Terminal 1 (Celery Worker):**
  *Lưu ý quan trọng:* Trên Windows, Celery cần chạy với pool `solo` để tránh xung đột đa tiến trình (prefork):
  ```powershell
  celery -A tasks.celery worker --loglevel=info --pool=solo
  ```
- **Terminal 2 (Flask Server):**
  ```powershell
  python app.py
  ```

Mở trình duyệt truy cập: **http://127.0.0.1:5001**

---

## ⚙️ Cấu hình (Tùy chọn)

Bạn có thể thay đổi các cấu hình như Model mặc định, URL cổng kết nối, Redis Broker URL bằng cách truyền các biến môi trường hoặc sửa trực tiếp trong file [config.py](config.py):

| Biến môi trường | Ý nghĩa | Giá trị mặc định |
|---|---|---|
| `OLLAMA_URL` | URL kết nối tới Ollama | `http://localhost:11434/api` |
| `DEFAULT_MODEL` | Model LLM mặc định phân tích và chat | `qwen2.5-coder:14b` |
| `EMBEDDING_MODEL` | Model nhúng vector cho cơ sở dữ liệu RAG | `nomic-embed-text` |
| `DATABASE_URL` | URI kết nối cơ sở dữ liệu SQLite | `sqlite:///ai_local_support.db` |
| `CELERY_BROKER_URL` | URL của Redis Broker dành cho Celery | `redis://localhost:6379/0` |

---

## 🛠 Hướng dẫn Khắc phục sự cố (Troubleshooting)

### 1. Celery báo lỗi: `Error 10061 connecting to 127.0.0.1:6379` hoặc `ConnectionRefusedError`
- **Nguyên nhân**: Redis chưa được khởi chạy hoặc cổng mạng bị chặn.
- **Giải pháp**:
  - Đảm bảo Redis service đang chạy (`wsl redis-cli ping` trả về `PONG` hoặc `docker ps` hiển thị container đang chạy).
  - Nếu sử dụng WSL 2, hãy kiểm tra lại file `/etc/redis/redis.conf` đã đổi thành `protected-mode no` chưa và restart lại dịch vụ. 
  - File cấu hình [config.py](config.py) mặc định tự động dò tìm IP ảo của WSL (`172.20.xxx.xxx`) và kết nối trực tiếp đến nó nếu loopback `127.0.0.1` bị Windows Firewall chặn.

### 2. Gặp lỗi build `chroma-hnswlib` khi cài đặt thư viện
- **Nguyên nhân**: Thiếu Microsoft Visual C++ compiler trên Windows.
- **Giải pháp**: Đảm bảo file `requirements.txt` sử dụng phiên bản `chromadb>=0.5.3` để pip tự tải bản precompiled binary (.whl) mà không cần build từ mã nguồn.

### 3. Lỗi liên quan đến thư viện `python-magic` trên Windows
- **Giải pháp**: Không cần cài đặt `python-magic` — thư viện này đã bị loại khỏi `requirements.txt` (không còn được sử dụng). Việc nhận diện loại file tải lên dựa trên phần mở rộng đã được whitelist trong `config.py`.

### 4. Celery báo lỗi: `Connection closed by server` hoặc ngắt kết nối liên tục khi sử dụng Redis trên WSL 2
- **Nguyên nhân**: Trên Windows 11, WSL 2 có cơ chế tự động tạm dừng hoặc tắt máy ảo (auto-pause/auto-shutdown) sau 15–60 giây không hoạt động để tiết kiệm pin/RAM. Do kết nối chạy nền từ Windows Host của Celery không được tính là hoạt động trực tiếp trên WSL, máy ảo WSL 2 sẽ tự động đi ngủ và ngắt kết nối socket của Redis.
- **Giải pháp**:
  Tắt tính năng tự động tạm dừng của WSL 2 bằng cách tạo hoặc cập nhật cấu hình WSL toàn cục:
  1. Tạo file `.wslconfig` trong thư mục User Profile của Windows (đường dẫn: `C:\Users\<Tên_User>\.wslconfig`).
  2. Thêm nội dung sau vào file và lưu lại:
     ```ini
     [general]
     instanceIdleTimeout=-1

     [wsl2]
     vmIdleTimeout=-1
     ```
  3. Mở PowerShell hoặc CMD và chạy lệnh sau để tắt hoàn toàn WSL (WSL sẽ tự khởi chạy lại kèm cấu hình mới ở lần kết nối tiếp theo):
     ```powershell
     wsl --shutdown
     ```

### 5. AI phản hồi chậm khi chạy ứng dụng Web so với Commandline / Trễ phân giải kết nối
> [!NOTE]
> Xem tài liệu chi tiết giải thích kỹ thuật và các cách khắc phục tại đây: **[So sánh hiệu năng: CLI vs. App](OLLAMA_CLI_VS_APP.md)**.

- **Nguyên nhân**:
  1. **Lỗi phân giải tên miền (macOS):** Python khi gửi request tới URL dạng `http://localhost:11434` sẽ bị trễ ~1.0 giây mỗi lần kết nối do cơ chế tìm kiếm IPv6. Với các luồng lặp của Agent (3-5 lần gọi API), độ trễ này cộng dồn làm ứng dụng rất chậm.
  2. **Tranh chấp bộ nhớ VRAM (Model Thrashing) đã được giải quyết:** Trước đây, khi chạy cả Chat và Embedding trên Ollama, VRAM bị tranh chấp liên tục gây chậm trễ. Hiện tại hệ thống đã tối ưu hóa bằng cách chuyển phần Embedding chạy trực tiếp trên Python CPU bằng thư viện **fastembed** (ONNX), loại bỏ hoàn toàn hiện tượng tráo đổi model trong VRAM.
- **Giải pháp**:
  - **Khắc phục lỗi trễ kết nối:** Đảm bảo cấu hình biến `OLLAMA_URL` kết nối tới địa chỉ IP trực tiếp `http://127.0.0.1:11434/api` thay vì dùng chữ `localhost`.
  - **Song song hóa tác vụ (Parallel Tool Calling):** Agent hiện tại hỗ trợ chạy nhiều công cụ song song trong cùng một lượt (ví dụ: đọc nhiều file hoặc chạy test đồng thời), giảm số lượng lượt gọi LLM xuống.
  - **Khuyến nghị lựa chọn kích thước Model dựa trên cấu hình RAM/VRAM máy tính:**
    - **Máy tính cấu hình thấp (RAM/VRAM < 16GB):** Ưu tiên sử dụng mô hình chat nhỏ gọn, hiệu quả cao như `qwen2.5-coder:7b`, `llama3:8b`, hoặc `deepseek-r1:8b`. Tránh dùng các bản 14B trở lên để không bị hiện tượng tràn VRAM swap sang ổ đĩa.
    - **Máy tính cấu hình tốt (RAM/VRAM >= 16GB trở lên hoặc Apple Silicon Mac M1/M2/M3 với Unified Memory lớn):** Có thể chạy mượt mà mô hình `qwen2.5-coder:14b` hoặc `deepseek-r1:14b` mặc định.

### 6. Tài liệu cứ hiển thị "Đang phân tích..." (processing) mãi không đổi trạng thái?
- **Giải pháp**:
  - Đảm bảo bạn đã khởi chạy Redis Server thành công (`docker ps` hoặc `brew services list`).
  - Kiểm tra kết nối tới Redis bằng cách chạy lệnh: `redis-cli ping` (phản hồi `PONG` là hoạt động tốt).
  - Bạn có thể xem các task đang chuyển tải qua Redis theo thời gian thực bằng lệnh: `redis-cli monitor`.
  - Đảm bảo bạn đã khởi chạy Celery worker bằng lệnh: `celery -A tasks.celery worker --loglevel=info --pool=solo` trong môi trường ảo `.venv` đã kích hoạt.
  - Kiểm tra log của Celery worker để xem có lỗi gì khi import thư viện hoặc lỗi kết nối Redis/Ollama không.

### 6b. Celery worker crash với `SIGTRAP` hoặc `WorkerLostError`?
- **Nguyên nhân**: Trên Python 3.14+ với macOS, Celery worker sử dụng `prefork` pool gặp xung đột khi fork process cùng lúc với các native C/C++ extensions (fastembed, chromadb, numpy) dẫn đến crash `signal 5 (SIGTRAP)`.
- **Giải pháp**: Luôn chạy worker với `--pool=solo`:
  ```bash
  celery -A tasks.celery worker --loglevel=info --pool=solo
  ```
  Solo pool chạy mỗi task trong 1 process riêng, tránh hoàn toàn lỗi fork. Cấu hình này đã được đặt mặc định trong `celery_app.py`.

### 7. Port 5001 đã được sử dụng?
- **Giải pháp**: Kiểm tra và giải phóng cổng 5001 (thường bị chiếm bởi dịch vụ AirPlay Receiver trên macOS):
  ```bash
  # Kiểm tra process đang dùng port
  lsof -i :5001

  # Kill process đang chiếm dụng port
  kill -9 <PID>
  ```

### 8. Ollama không kết nối được hoặc cần khởi động lại?
- **Giải pháp**:
  - Kiểm tra dịch vụ Ollama có phản hồi danh sách model không:
    ```bash
    ollama list
    ```
  - Tắt hoàn toàn dịch vụ/tiến trình Ollama nếu bị treo:
    ```bash
    pkill ollama
    ```
  - Khởi động lại ứng dụng Ollama Desktop hoặc chạy lệnh sau để khởi động service:
    ```bash
    ollama serve
    ```

### 9. OCR không hoạt động khi upload ảnh với model thường?
- **Giải pháp**: Đảm bảo bạn đã cài đặt thư viện hệ thống Tesseract OCR:
  - **macOS:** `brew install tesseract tesseract-lang` (cần cài bản `-lang` để hỗ trợ tiếng Việt)
  - **Ubuntu:** `sudo apt-get install tesseract-ocr tesseract-ocr-vie`
  - **Windows:** Tải file cài đặt (installer `.exe`) từ [UB Mannheim Tesseract Wiki](https://github.com/UB-Mannheim/tesseract/wiki). Trong quá trình cài đặt, chọn tải thêm gói ngôn ngữ **Vietnamese** (tiếng Việt). Sau khi cài đặt hoàn tất, bạn cần thêm đường dẫn của thư mục cài đặt (mặc định là `C:\Program Files\Tesseract-OCR`) vào biến môi trường hệ thống **PATH** và khởi động lại terminal.
  - Kiểm tra xem Tesseract đã hoạt động trong Terminal:
    ```bash
    # Kiểm tra phiên bản
    tesseract --version

    # Kiểm tra các ngôn ngữ OCR được hỗ trợ (cần thấy 'vie' và 'eng')
    tesseract --list-langs
    ```

### 10. Vision model không nhận diện được ảnh?
- **Giải pháp**:
  - Đảm bảo model bạn chọn nằm trong tập hợp các vision model hỗ trợ (ví dụ: `qwen2.5-vl`, `llava`, `moondream`).
  - Kiểm tra xem GPU của máy có bị quá tải VRAM dẫn đến model bị tắt (killed) giữa chừng không.
  - Thử chuyển sang dùng model không phải vision (như `qwen2.5-coder`) để kích hoạt tính năng **OCR fallback** sử dụng Tesseract.
