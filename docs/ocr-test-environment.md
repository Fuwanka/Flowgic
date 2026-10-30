# Локальное окружение проверки OCR

Окружение изолировано от обычного Flowgic: отдельная Docker-сеть `flowgic-ocr-tests`, контейнеры с меткой `flowgic.local-purpose=ocr-tests`, новые роли и базы. Используются PostgreSQL 16/PostGIS 3.4 и Redis 7. SQLite не участвует в проверке.

Локальные скрипты и секреты находятся в игнорируемой папке `.local/ocr-tests/`. Они не входят в репозиторий и не заменяют `.env` основного приложения. Запускайте PowerShell из корня репозитория.

```powershell
.\.local\ocr-tests\bootstrap.ps1
.\.local\ocr-tests\run.ps1 manage check
.\.local\ocr-tests\run.ps1 manage makemigrations --check --dry-run
.\.local\ocr-tests\run.ps1 pytest --migrations --create-db --browser chromium --tb=short
```

`run.ps1` запускает текущий `backend/` в Linux-образе `flowgic-ocr-test:local`. Образ построен поверх существующего `flowgic-test:dev` с дополнительными Pillow 13.0.0 и pypdf 6.21.4. Переустановка зависимостей ML-окружения для тестов Django не нужна.

Если фронтенд изменён, перед браузерным прогоном выполните `npm run build --prefix frontend-web`: helper подключит актуальную папку `frontend-web/dist/` поверх встроенного SPA. Chromium уже установлен в тестовом образе.

Для реальной цепочки HTTP → Django → Celery → PaddleOCR:

```powershell
.\.local\ocr-tests\app.ps1 migrate
.\.local\ocr-tests\app.ps1 start
.\.local\ocr-tests\app.ps1 status
# После изменения Python-кода:
.\.local\ocr-tests\app.ps1 restart
# Остановка только backend/worker этого окружения:
.\.local\ocr-tests\app.ps1 stop
```

Адрес Django: `http://127.0.0.1:18081`; локальный OCR-сервис: порт `18082`, из Docker — `http://host.docker.internal:18082`. PostgreSQL опубликован только на `127.0.0.1:55439`, Redis — на `127.0.0.1:56389`. Worker слушает очередь `documents`. Redis для pytest использует отдельные индексы 8/9/10; реальный smoke использует 0/1/2, параллельный Chromium —11/12/13 и отдельную БД `test_flowgic_ocr_browser`.

`app.env` содержит `OCR_SERVICE_KEY` для обеих сторон. Загружайте его в окружение процесса OCR без вывода в консоль. Приватные оригиналы доступны backend и worker в общем `/ocr-private`, который соответствует `.local/ocr-tests/private/` на машине. Это отдельное хранилище теста.

Роль runtime `flowgic_ocr_app` не имеет SUPERUSER/CREATEDB/CREATEROLE. Роль pytest `flowgic_ocr_test` имеет CREATEDB, но не SUPERUSER/CREATEROLE. PostGIS заранее установлен администратором в новой тестовой основной БД и `template1`, поэтому disposable pytest-БД наследует расширение.

Проверки инфраструктуры на новой БД выполнены 29.10.2026: `tests/test_infrastructure.py` — **3 passed**, миграции включены; Django `check` — без ошибок; PostGIS сообщает версию 3.4.3, Redis отвечает PONG.
