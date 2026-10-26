# Тестирование Flowgic

Тесты используют PostgreSQL/PostGIS и Redis. Подмены на SQLite нет.
Приложение запускается от обычной роли; pytest использует отдельную роль с CREATEDB.

## Полный воспроизводимый прогон

Из корня, после подготовки `.env` по README:

```powershell
docker compose --profile test build test
docker compose run --rm test
```

Compose запускает зависимости; pytest создаёт отдельную БД `test_flowgic`,
применяет все существующие миграции и запускает модели, интеграционные сценарии,
изоляцию компаний, Django-client E2E и Playwright/Chromium.
Корневой и backend/pytest.ini включают миграции по умолчанию. `--create-db`
пересоздаёт только выделенную тестовую БД. Не указывайте имя рабочей БД в DB_TEST_NAME.

```powershell
# Только модели и изоляция компаний
docker compose run --rm test python -m pytest accounts/tests.py logistics/tests.py logistics/test_data_isolation.py --migrations --create-db --tb=short

# Все сценарии, которым не нужен браузер
docker compose run --rm test python -m pytest -m "not browser" --migrations --create-db --tb=short

# Только браузерные проверки
docker compose run --rm test python -m pytest -m browser --browser chromium --migrations --create-db --tb=short

# Проверка схемы и миграционного дрейфа
docker compose run --rm backend python manage.py check
docker compose run --rm backend python manage.py makemigrations --check --dry-run
```

`e2e` обозначает также Django-client сценарии, не требующие браузера; `browser`
помечает все тесты с Playwright. `slow` — длительные бизнес-сценарии.
Не исключайте `slow`, если нужен полный прогон.

## Состав

- `frontend-web/src/lib/*.test.ts`: единая ротация JWT, выход во время refresh,
  смена аккаунта, истечение сессии, сетевые/валидационные ошибки и HTTP 402.
- `backend/logistics/test_spa_api.py`: API карточки, списков/календаря,
  финансового предпросмотра и справочников; изоляция и транзакционный откат.
- `backend/tests/test_spa_browser.py`: production React SPA через живой Django API,
  создание заказа/клиента/водителя, финансовый расчёт, DOCX, квота, новый tenant,
  reload, мобильная навигация и ограничение водительской роли.

Docker test сам собирает SPA из исходников. Для pytest на хосте сначала выполните
`npm ci --prefix frontend-web`, `npm run build --prefix frontend-web` и установите
системные зависимости GeoDjango и Chromium. Путь к готовому бандлу можно указать
в `SPA_DIST`. Не подменяйте API в этих сквозных тестах фиктивными ответами.

- `backend/accounts/tests.py`: пользователи, роли, пароли, тема.
- `backend/accounts/test_api.py`: Ninja TestClient, JWT, профиль, регистрация,
  одноразовый сброс пароля, лимиты Redis, отзыв токенов и HTTP/OpenAPI.
- `backend/accounts/test_legacy_auth.py`: общие сервисы старых HTML-страниц,
  регистрация отдельной компании и изоляция панелей.
- `backend/logistics/tests.py`: заказы, клиенты, ТС, компании, события, расчёты Financial.
- `backend/logistics/test_data_isolation.py`: границы компаний и роли.
- `backend/logistics/test_tenant_regressions.py`: чужие заказы, ресурсы формы и календарь.
- `backend/logistics/test_views_integration.py`: статусы, финансы и события.
- `backend/logistics/test_*_e2e.py`: заказы, оплаты, панели и нагрузочные сценарии.
- `backend/logistics/test_client_management_browser.py`: браузерные сценарии клиентов.
- `backend/tests/test_workflow.py`: создание заказа через браузер.
- `backend/tests/test_infrastructure.py`: реальный PostGIS, Redis и настройки Celery.

Фикстуры двух компаний находятся в `backend/conftest.py`, фабрики — в
`backend/logistics/factories.py`. Браузерные тесты используют `live_server` и
транзакционную тестовую БД. Внешняя доставка почты тестам не нужна.

## Нативный запуск

Установите requirements и библиотеки GeoDjango по README, запустите `db redis`.
Загрузите `.env` и переопределите `DB_USER`/`DB_PASSWORD` значениями
`DB_TEST_USER`/`DB_TEST_PASSWORD` для процесса pytest; среда имеет приоритет над `.env`.

```powershell
python -m playwright install chromium
python -m pytest --migrations --create-db --tb=short
```

Ошибка GDAL/GEOS на Windows означает отсутствие нативных библиотек; используйте
тестовый Docker-образ. При проблемах схемы пересоздавайте выделенную тестовую БД
через `--create-db`, а не очищайте рабочую БД командой `flush`.

CI в `.github/workflows/tests.yml` выполняет аналогичный полный прогон на Python 3.11,
PostGIS 16-3.4 и Redis 7, после проверки Django и миграционного дрейфа.
