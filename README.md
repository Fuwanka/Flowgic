# Flowgic

B2B MiniCRM/TMS для логистических компаний. Текущий интерфейс работает на
Django Templates: вход и регистрация, роли диспетчера/руководителя/водителя,
заказы и статусы, календарь, клиенты, транспорт, водители и финансовые данные.

Этап 1 переводит инфраструктуру на Python 3.11, Django 5.2, PostgreSQL 16 +
PostGIS 3.4, Redis 7 и Celery. Модели и их миграционная история сохранены.
Архитектурные правила и последующие этапы описаны в [AGENTS.md](AGENTS.md).

## Быстрый запуск через Docker

Нужен запущенный Docker Desktop с Linux-контейнерами и Docker Compose v2.
Из корня репозитория:

```powershell
Copy-Item .env.example .env
# Замените SECRET_KEY и три пароля в .env случайными значениями.
docker compose up -d --build
```

Открыть http://localhost:8000. Сервис `migrate` сначала применяет существующие
миграции; `backend` и `celery` стартуют после него. Для просмотра журналов:

```powershell
docker compose logs backend celery migrate
```

В рабочем локальном checkout `.env` уже может быть подготовлен: не перезаписывайте
его, если он существует. Секреты не коммитятся. Значения окружения имеют приоритет
над `.env`. В контейнерах адреса БД и Redis автоматически меняются на `db` и `redis`.
Если порт 5432 занят, задайте одинаковый свободный порт в `DB_PUBLISHED_PORT` и
`DB_PORT` для локального Python; в контейнерах PostgreSQL продолжает слушать 5432.
В подготовленном локальном окружении используется 55432.

```powershell
docker compose exec backend python manage.py check
docker compose exec backend python manage.py makemigrations --check --dry-run
```

Это окружение разработки с Django runserver. Production-развёртывание требует
отдельной настройки web-сервера, TLS, static/media и секретов.

## Тесты

```powershell
docker compose --profile test build test
docker compose run --rm test
```

Тестовый образ включает Chromium и системные библиотеки GeoDjango. Все тесты,
включая браузерные, работают на настоящем PostGIS; миграции включены.
Подробные команды: [TESTING.md](TESTING.md).

## Accounts API

Этап 2 для accounts добавляет JWT API: регистрация отдельной компании, вход,
ротация refresh, выход, профиль, смена и восстановление пароля. Старые страницы
используют те же сервисы. Документация работающего API: http://localhost:8000/api/docs.
Контракт и правила: [docs/accounts-api.md](docs/accounts-api.md).
Типизированный клиент: [frontend-web/README.md](frontend-web/README.md).

## Структура

```text
backend/
  accounts/             пользователи, роли, профиль, восстановление пароля
  logistics/            компании, клиенты, заказы, ТС, финансы, события, документы
  billing/              тарифы и лимиты компаний, кеш использования Redis
  marketplace/          контекстные B2B-предложения и учёт кликов
  flowgic/              Django settings/URLs/ASGI/WSGI и Celery
  templates/ и static/  существующий веб-интерфейс
  tests/                общие и инфраструктурные проверки
  requirements.txt      зависимости приложения
  requirements-dev.txt  pytest и Playwright
infra/postgres/         первичная настройка ролей и PostGIS
.github/workflows/     полная проверка на Python 3.11 + PostGIS + Redis
```

Карта архитектуры, изменения тестов и границы этапа: [docs/architecture.md](docs/architecture.md).

Этап 3 добавляет Freemium-квоты, контекстные партнёрские офферы, скачивание
Договор-заявки и ТТН в DOCX и команду `python manage.py seed_demo_company`.
Запуск, API и правила повторного наполнения: [docs/stage-3.md](docs/stage-3.md).

## Локальный Python

Рекомендуется Docker: backend PostGIS требует GDAL/GEOS/PROJ даже без геополей.
Для нативного запуска установите эти библиотеки и настройте пути согласно
[GeoDjango](https://docs.djangoproject.com/en/5.2/ref/contrib/gis/install/).

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
docker compose up -d db redis
python backend/manage.py migrate
python backend/manage.py runserver
```

`venv/` остаётся локальным окружением, исключённым из Git и индексации ИИ.
Корневой `requirements.txt` ссылается на зависимости backend.

## Данные и роли PostgreSQL

`flowgic_admin` используется только при инициализации нового тома. Приложение
работает как `flowgic_app` без SUPERUSER/CREATEDB; тесты — как `flowgic_test` с
CREATEDB, без SUPERUSER. PostGIS заранее устанавливается в основную БД и template1,
поэтому тестовым подключениям не нужны повышенные права для расширения.
Имена и пароли задаются в `.env`; скрипт `infra/postgres/20-flowgic.sh` исполняется
только на пустом томе. Изменение `.env` не меняет роли в уже созданном томе.

PostgreSQL и Redis хранят данные в именованных томах. `docker compose down`
останавливает окружение с сохранением данных; не добавляйте `-v`, если данные нужны.

Старая SQLite-база при переносе сохранена локально в
`.local/backups/db-before-postgres.sqlite3` и исключена из Git. Переключение
инфраструктуры не импортирует её записи в PostgreSQL. Перенос пользовательских
данных выполняется отдельной проверяемой операцией после резервного копирования.

SMTP-параметры задаются через окружение; по умолчанию письма выводятся в консоль.
Ранее встроенный в settings SMTP-пароль удалён из кода, но остаётся в Git-истории:
его следует перевыпустить у почтового провайдера.
