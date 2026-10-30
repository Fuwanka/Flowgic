# Локальный OCR для Flowgic

Изолированный внутренний CPU сервис: PaddleOCR 3.7.0, `PP-OCRv5_mobile_det`
и `eslav_PP-OCRv5_mobile_rec`. Он возвращает текст и координаты; бизнес-поля
извлекает `backend/document_processing/extraction.py`. Это первый рабочий
эвристический модуль. Предложения проверяет человек. Неудачный эксперимент
дообучения удалён; его выводы сохранены в `docs/document-kie-training.md`.

## Подготовка и запуск на Windows

Модели подготавливаются администратором отдельно. Используются уже проверенные
локальные каталоги из `.local/paddle-eval/models-mobile`; сервис сам их не скачивает.
В обоих каталогах обязательны `inference.json`, `inference.pdiparams`, `inference.yml`.
Модели закреплены ревизиями и SHA-256 в `models.lock.json`; runtime проверяет весь bundle.
Подготовка администратором: `python ocr-service/prepare_models.py --root .local/paddle-eval/models-mobile --download`.
Для проверки уже скачанных файлов выполните эту команду без `--download`.

Из корня репозитория, PowerShell:

```powershell
# Для нового окружения: py -3.11 -m venv .local/ocr-service-venv
# & .local/ocr-service-venv/Scripts/python.exe -m pip install -r ocr-service/requirements.txt
$env:OCR_MODEL_ROOT = (Resolve-Path '.local/paddle-eval/models-mobile').Path
$env:OCR_CACHE_ROOT = Join-Path (Resolve-Path '.local/paddle-eval').Path 'service-cache'
# Задайте OCR_SERVICE_KEY через менеджер секретов или окружение процесса.
# Один и тот же случайный ключ (рекомендуется минимум 32 байта) нужен Django и OCR.
& .local/paddle-eval/venv/Scripts/python.exe -m uvicorn app:create_app --factory --app-dir ocr-service --workers 1 --host 127.0.0.1 --port 8090 --no-access-log
```

`GET /health` доступен без ключа, возвращает только `{"ready":true}` (200) или
`{"ready":false}` (503). Отсутствующий `OCR_SERVICE_KEY` запрещает запуск.
Неполные модели оставляют сервис в состоянии not ready без загрузки из интернета.
Проверка готовности подтверждает инициализацию, первый инференс проверяется отдельно.

`POST /recognize`: multipart с единственным полем `file`, обязательный заголовок
`X-OCR-Service-Key`. PNG/JPEG/PDF проверяются по содержимому; пути и URL не принимаются.
Лимиты: файл 20 MiB, тело 20 MiB+64KiB, PDF10 стр., изображение 25 млн пикселей/12000 px,
PDF рендерится около 180dpi с ограничением 14 млн пикселей/8000 px на страницу.
Ответ не превышает 8 MiB. Одновременно обрабатывается один документ; при занятости 503
`ocr_busy`; задача Flowgic переходит в ошибку и доступна для ручного повтора.
Рекомендуемый клиентский timeout600 секунд для многостраничного PDF.

```json
{"engine":"paddleocr-3.7.0/PP-OCRv5_mobile_det/eslav_PP-OCRv5_mobile_rec","pages":[{"number":1,"width":1800,"height":1282,"lines":[{"text":"Масса груза: 15,5 т","confidence":0.97,"bbox":[10.0,20.0,30.0,2.0]}]}]}
```

`bbox` = `[left, top, width, height]` в процентах, нумерация страниц с 1.
OCR confidence не является вероятностью правильного бизнес-поля.
Ошибки имеют короткие машинные коды; тело документа, ключи и детали исключений
не попадают в HTTP ошибки или журналы приложения.

## Контейнер

```powershell
docker build -t flowgic-ocr ./ocr-service
docker run --rm --name flowgic-ocr -p 127.0.0.1:8090:8090 --env OCR_SERVICE_KEY --mount "type=bind,source=$env:OCR_MODEL_ROOT,target=/models,readonly" --memory=3g --cpus=4 flowgic-ocr
```

Для production используйте внутреннюю сеть без публичного порта, закрытый исходящий
доступ и readonly mount моделей. Python сетевые вызовы внутри инициализации и
инференса блокируются дополнительно; сетевую изоляцию ОС это не заменяет.
Один Uvicorn worker обязателен: каждый дополнительный процесс загрузит свою модель
и получит отдельный лимит параллелизма. Не отправляйте реальные документы во внешние API.
Нужны примерно 2–3 GiB RAM на процесс с запасом; измеренный локальный пик mobile
модели около 1.04 GiB, медиана 15.6 сек/стр. Эти результаты зависят от оборудования.

## Тесты без моделей

```powershell
& .local/paddle-eval/venv/Scripts/python.exe -m unittest discover -s ocr-service -p 'test_*.py' -v
```

Тесты сервиса используют httpx (dev dependency), фальшивый OCR только для проверки
HTTP/ограничений и настоящие декодеры PIL/PDFium. Реальное распознавание проверяется
отдельным запросом к запущенному сервису с локальным документом.
