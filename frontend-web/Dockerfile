# Сборка не требует запущенного API: используется закоммиченный клиент OpenAPI.
FROM node:22.18.0-bookworm-slim AS build
WORKDIR /web
COPY frontend-web/package*.json ./
RUN npm ci --ignore-scripts --no-audit --no-fund
COPY frontend-web/ ./
RUN npm run build

FROM nginx:1.30.6-alpine
COPY frontend-web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /web/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=15s --timeout=3s --start-period=5s CMD wget -q -O /dev/null http://127.0.0.1/health || exit 1
