# Frontend Flowgic

React + Vite + TypeScript, Ant Design, TanStack Query и React Router.
Требуется Node.js 22.18 или новее. Docker frontend доступен на http://localhost:5173.

```powershell
cd frontend-web
npm ci --ignore-scripts
npm run dev
# Проверки и production-бандл:
npm test
npm run build
```

Backend должен работать на localhost:8000. Vite проксирует `/api`; адрес можно
изменить через `API_PROXY_TARGET`. Docker использует Nginx с таким же proxy.
Если порт 5173 занят контейнером, остановите frontend или используйте `--port 5174`.

`src/pages` — экраны; `src/components` — формы и блоки; `src/lib` — JWT-сессия,
ошибки и форматирование; `src/client` — сгенерированный SDK. Подробная архитектура,
правила кеша/refresh и инструкция пользователя: [TRANSFORMATION.md](../TRANSFORMATION.md).

## Генерация типизированного клиента

Из корня репозитория:

```powershell
docker compose run --rm --volume "${PWD}/backend:/app" backend python manage.py export_openapi --output /app/openapi.json
npm ci --prefix frontend-web --ignore-scripts
npm run generate-api --prefix frontend-web
npm run typecheck --prefix frontend-web
```

`backend/openapi.json` — детерминированный снимок схемы, а `src/client/` — полностью
сгенерированный код. Не редактируйте его вручную. Для генерации непосредственно
из работающего API задайте `OPENAPI_INPUT=http://localhost:8000/api/openapi.json`.
CI повторяет генерацию и отклоняет расхождение с закоммиченными файлами.

Пример использования:

```typescript
import { client } from './src/client/client.gen';
import { loginAccount, getProfile } from './src/client/sdk.gen';

client.setConfig({ baseUrl: 'http://localhost:8000' });
const result = await loginAccount({
  body: { email: 'user@example.com', password: 'your-password' },
});
if (result.data) {
  client.setConfig({ auth: () => result.data!.access });
  const profile = await getProfile();
}
```

Выбирайте хранение токенов в приложении с учётом его модели безопасности.
Обновление токена явно вызывается через `refreshTokens`; старый refresh после
успешной ротации повторно не используется. После смены/сброса пароля требуется
новый вход. Автоматический повтор запросов после 401 здесь не выполняется.
