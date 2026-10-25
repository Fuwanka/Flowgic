# Проверка этапа 2: accounts

Проверено локально 25 октября 2026 года.

## Результаты

- Новый набор API/HTML-регрессий accounts: **60 passed**, 45.88 секунды.
- Полный набор проекта: **198 passed, 0 failed**, без предупреждений,
  276.34 секунды. Включены прежние 138 тестов, slow и Playwright/Chromium.
- Реальные PostgreSQL 16/PostGIS 3.4 и Redis; миграции включены, отдельная
  тестовая база пересоздана. SQLite и подмена БД не применялись.
- `manage.py check`: 0 issues; `makemigrations --check --dry-run`: No changes detected.
- Образы backend/test собраны с Django Ninja 1.7.1, django-ninja-jwt 5.4.5,
  django-ninja-extra 0.31.7 и Pydantic 2.14.1.
- Доменные models.py accounts/logistics не изменены; новых миграций моделей
  проекта нет. Штатные миграции blacklist-приложения проверены на тестовой БД
  и применены при запуске локального backend.
- Чистый `npm ci --ignore-scripts`, `generate-api`, `typecheck`: успешно.
  Повторная генерация сохраняет SHA-256 снимка OpenAPI и всех 16 TypeScript-файлов.
- Работающая схема `/api/openapi.json` совпадает с сохранённым снимком:
  9 путей, 10 операций. `/api/docs` отвечает HTTP 200; анонимный профиль —
  HTTP 401 с `WWW-Authenticate: Bearer`.
- Celery обнаруживает `accounts.tasks.send_password_reset_email`; задача
  реально выполнена через Redis с результатом 1. Проверка использовала строго
  console email backend и тестовый адрес, без внешней доставки почты.
- Синтаксис Python и `git diff --check`: успешно. В accounts/api.py и views.py
  нет обращений `.objects`, `.save()` и `.delete()`.

## Фактические команды

Из `C:\repository\Flowgic`, с актуальными исходниками, подключёнными к /app:

```powershell
docker compose run --rm --volume 'C:\repository\Flowgic\backend:/app' test python -m pytest accounts/test_api.py accounts/test_legacy_auth.py --migrations --create-db --tb=short
docker compose run --rm --volume 'C:\repository\Flowgic\backend:/app' test
```

Команда полного тестового контейнера:

```text
python -m pytest --migrations --create-db --tb=short
```

Проверки артефактов и работающего backend:

```powershell
docker compose --profile test build backend test
docker compose up -d backend celery
docker compose exec backend python manage.py check
docker compose exec backend python manage.py makemigrations --check --dry-run
npm ci --prefix frontend-web --ignore-scripts --no-audit --no-fund
npm run generate-api --prefix frontend-web
npm run typecheck --prefix frontend-web
```

Локальные журналы исключены из Git: `.local/accounts-focused.log`,
`.local/accounts-full.log`, `.local/accounts-build-final.log`.
Результат удалённого CI относится к конкретному коммиту и отображается в PR.

Контракт, ограничения и правила: [accounts-api.md](accounts-api.md).
