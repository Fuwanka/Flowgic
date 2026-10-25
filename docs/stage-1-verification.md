# Этап 1: результат проверки

Проверено локально 25 октября 2026 года. Рабочий checkout: `C:\repository\Flowgic`.

## Результат

**138 passed, 0 failed, без предупреждений; 261.77 секунды.**

Команда из корня репозитория:

```powershell
docker compose --profile test build test
docker compose run --rm test
```

Команда контейнера:

```text
python -m pytest --migrations --create-db --tb=short
```

Выполнены все 138 собранных тестов: модели, Django-client интеграционные/E2E
сценарии, slow, изоляция компаний, новые регрессии, инфраструктура и Playwright
с Chromium Headless. Никакие категории не исключались в итоговом прогоне.
Использовались настоящий PostgreSQL 16.4 + PostGIS 3.4.3, Redis 7,
Python 3.11 и Django 5.2.18. Тестовая БД пересоздана с существующими миграциями;
SQLite и `--nomigrations` не использовались.

Полный локальный журнал: `.local/pytest-postgis-full.log` (исключён из Git).
Предварительный небраузерный прогон: 114 passed. В исходном состоянии проекта
тот же небраузерный набор дал 86 passed / 19 failed; причины и исправления
описаны в [architecture.md](architecture.md).

## Дополнительные проверки

| Проверка | Результат |
| --- | --- |
| `docker compose config --quiet` | Успешно |
| Сборка backend и test образов | Успешно |
| `python manage.py check` в backend | 0 issues |
| `python manage.py makemigrations --check --dry-run` | No changes detected |
| `migrate` в новой локальной БД | Все миграции применены |
| Сравнение моделей с исходным HEAD | Оба models.py сохранены |
| Сравнение прежних миграций с HEAD | Все 13 файлов сохранены |
| SQL `PostGIS_Version()` и создание POINT/SRID 4326 | Успешно |
| Права PostgreSQL | app: без SUPERUSER/CREATEDB; test: CREATEDB, без SUPERUSER |
| Redis | PONG и проверка cache round-trip |
| Celery | Worker ping и выполнение встроенной задачи с результатом через Redis |
| Пользователь runtime-контейнера | UID 1000 |
| HTTP `/login/` | 200 |
| Shell syntax provisioning-скрипта, Python syntax, `git diff --check` | Успешно |
| Git-индекс: venv, SQLite, кэши | Не отслеживаются |

CI обновлён на аналогичный полный прогон. Результаты выше относятся к локальной
проверке; результат удалённого GitHub Actions проверяется отдельно в pull request.

## Локальное окружение и данные

Приложение: http://localhost:8000. PostgreSQL опубликован на `127.0.0.1:55432`,
поскольку 5432 занят существующим процессом. Внутри Compose БД использует 5432.
Redis опубликован на `127.0.0.1:6379`.

Старая SQLite сохранена в `.local/backups/db-before-postgres.sqlite3`;
SHA-256 копии проверен до удаления исходного файла из src. Её бизнес-данные
не импортировались в PostgreSQL. Все новые тесты использовали отдельную БД.

SMTP-пароль, ранее находившийся в settings.py, убран из текущего кода;
его перевыпуск у провайдера нужен, поскольку прежнее значение осталось в Git-истории.
