# Этап 2: accounts и JWT API

Существующие HTML-маршруты сохранены. Они и новый API используют один набор правил
в `backend/accounts/services.py`; чтение профиля и данных панелей находится в
`selectors.py`. В `accounts/api.py` и `accounts/views.py` нет ORM-запросов и записи
моделей. Новый API смонтирован под `/api/`, документация — `/api/docs`, схема —
`/api/openapi.json`.

## Контракт

| Метод и путь | Действие |
| --- | --- |
| POST `/api/accounts/register` | Создать новую компанию и пользователя, вернуть профиль и пару JWT; HTTP 201 |
| POST `/api/accounts/token` | Войти по email/password, получить access/refresh |
| POST `/api/accounts/token/refresh` | Однократно обменять refresh на новую пару |
| POST `/api/accounts/token/verify` | Проверить подпись, срок, пользователя и отзыв токена |
| POST `/api/accounts/logout` | Отозвать refresh и доступ этой сессии; нужен Bearer access той же пары |
| GET `/api/accounts/me` | Профиль текущего пользователя |
| PATCH `/api/accounts/me` | Изменить только full_name, phone, theme |
| POST `/api/accounts/password/change` | Изменить пароль с проверкой current_password |
| POST `/api/accounts/password/reset` | Запросить код по email; одинаковый HTTP 202 для существующего и отсутствующего аккаунта |
| POST `/api/accounts/password/reset/confirm` | Подтвердить email/code/new_password |

Защищённые операции принимают `Authorization: Bearer <access>`. Cookie-сессия
сама по себе не авторизует API. Ошибки приложения имеют поля `detail` и `code`:
400 — ошибка бизнес-валидации, 401 — отказ авторизации, 403 — чужая сессия,
409 — занятый email, 422 — неверная схема ввода, 429 — лимит попыток входа.
Валидационные ошибки не возвращают значения паролей и JWT.

Пример регистрации:

```json
{
  "email": "owner@example.com",
  "password": "a-strong-unique-password",
  "full_name": "Иван Иванов",
  "company_name": "Логистика",
  "company_type": "logistics",
  "role": "manager"
}
```

company_type по умолчанию logistics, role — manager. Допускаются существующие
роли dispatcher/manager/driver, но всегда внутри новой компании. Совпадение
названий компаний никогда не даёт членство в существующей компании. Приглашение
в существующий tenant требует отдельного будущего процесса. Передача company_id,
is_staff, is_superuser и неизвестных полей отклоняется. Email нормализуется в
нижний регистр; проверка существующих адресов не зависит от регистра.

## Границы и безопасность

- User и PasswordResetCode и их миграции сохранены. Company пока принадлежит
  logistics, поэтому onboarding вызывает публичный `logistics.services.create_company`.
  Создание клиентов и ТС из старых accounts views также передано публичным сервисам
  logistics, доступным dispatcher/manager своей компании.
- Транзакции охватывают регистрацию компании/пользователя/токенов, ротацию,
  смену пароля и потребление кода. Ротация и смена пароля сериализуются блокировкой
  пользователя; повторное использование refresh запрещено blacklist-приложением
  django-ninja-jwt.
- Access живёт 5 минут, refresh — 1 день. Оба токена содержат HMAC-отпечаток
  текущего хеша пароля; смена пароля через API, HTML или Django admin автоматически
  прекращает действие прежних JWT. Права, компания и статус читаются из БД при
  каждом запросе, а не из клиентских role/company claims. Неактивные, blocked,
  invited и пользователи без компании не авторизуются.
- При logout идентификатор сессии отзывается в Redis до конца жизни refresh,
  а refresh заносится в PostgreSQL blacklist. Другие сессии пользователя остаются
  доступны. Для уже ротированной пары logout вызывайте с актуальными токенами.
- После 10 неудачных входов по email за 5 минут вход ограничивается на остаток
  окна. Сброс пароля отправляет не более одного письма на email в минуту; код
  действует 10 минут, допускает до 5 неверных попыток за 10 минут и потребляется
  только один раз. Новый код отменяет предыдущий; запрос нового кода не обнуляет
  счётчик неверных попыток. Применяются штатные Django password validators.
- Письмо ставится в Celery только после commit. Используется DEFAULT_FROM_EMAIL,
  с повторами при ошибках SMTP. При ошибке постановки в очередь callback пишет
  ошибку в журнал; публичный ответ остаётся одинаковым, чтобы не раскрывать email.
- Панели используют `logistics.selectors.get_user_orders`: tenant определяется
  через client.company, а водитель видит только свои заказы. Отсутствие создателя
  заказа не лишает компанию доступа к своему заказу.

## Запуск и проверки

```powershell
docker compose up -d --build
docker compose --profile test build test
docker compose run --rm test
docker compose run --rm test python -m pytest accounts --migrations --create-db --tb=short
docker compose exec backend python manage.py check
docker compose exec backend python manage.py makemigrations --check --dry-run
```

При запуске применяются штатные миграции `ninja_jwt.token_blacklist`. Настройка
`JWT_SIGNING_KEY` в `.env` позволяет отделить ключ JWT от SECRET_KEY; пустое
значение использует SECRET_KEY. При смене ключа прежние JWT прекращают действие.
Redis и Celery обязательны для ограничений, отзыва сессий и доставки кодов.
Для уборки истёкших записей blacklist предусмотрена команда библиотеки
`python manage.py flushexpiredtokens`; частоту её запуска выбирает эксплуатация.

OpenAPI и клиент обновляются вместе с API. Команды и пример использования:
[frontend-web/README.md](../frontend-web/README.md). CI проверяет миграционный
дрейф, совпадение схемы/клиента, TypeScript и полный pytest с браузером.
