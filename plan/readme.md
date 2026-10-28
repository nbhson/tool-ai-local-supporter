# Plan — tool-ai-local-supporter

App hỗ trợ AI cục bộ: Flask + Celery + Ollama, blueprints/services/tasks, pytest.

## Baseline audit (00:44, 28-10-2026)
- Tests: ✅ **9 pass** (chỉ chạy được với `.venv` — system Python thiếu pypdf)
- Tài liệu sẵn: ARCHITECTURE.md, AI_ENGINEERING.md, INSTALLATION.md — cần đối chiếu với code
- Commit gần nhất: whitelist allowed commands cho agent shell tools (security)

## Roadmap
### P0
- [ ] Xác nhận mọi tính năng chính chạy được (app factory, celery task định nghĩa hợp lệ)
- [ ] Audit tiếp security: command whitelist, path traversal, CORS

### P1 (chất lượng)
- [ ] Audit blueprints/services: error handling, validation, logging
- [ ] Bổ sung tests cho services quan trọng (đang mỏng: 9 tests)
- [ ] requirements.txt: pin phiên bản, tách dev deps

### P2 (hardening)
- [ ] CI workflow
- [ ] INSTALLATION.md sync thực tế

## Self-review log
- _0:44_ Audit lần 1: 9/9 pass với .venv.
