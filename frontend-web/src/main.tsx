/** Единые провайдеры локали, темы, серверного кеша и авторизации для всей SPA. */
import React from "react";
import ReactDOM from "react-dom/client";
import { App as AntApp, ConfigProvider } from "antd";
import ruRU from "antd/locale/ru_RU";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";
import dayjs from "dayjs";
import "dayjs/locale/ru";
import "antd/dist/reset.css";
import "./styles.css";
import "./lib/api";
import App from "./App";
import { AuthProvider } from "./auth";
import { ApiError } from "./lib/api";

dayjs.locale("ru");
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 20_000,
      refetchOnWindowFocus: true,
      retry: (count, error) =>
        !(
          error instanceof ApiError &&
          error.status > 0 &&
          error.status < 500
        ) && count < 1,
    },
    mutations: { retry: false }, // Запись не повторяется автоматически после сетевой ошибки.
  },
});
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ConfigProvider
      locale={ruRU}
      theme={{
        token: {
          colorPrimary: "#16796b",
          colorLink: "#16796b",
          colorLinkHover: "#10584d",
          borderRadius: 8,
          fontFamily: "Inter, Segoe UI, system-ui, sans-serif",
          colorText: "#20383f",
          controlHeight: 38,
        },
        components: {
          Table: { headerBg: "#f7faf9", cellPaddingBlock: 18 },
          Button: { primaryShadow: "none" },
        },
      }}
    >
      <AntApp>
        <QueryClientProvider client={queryClient}>
          <BrowserRouter>
            <AuthProvider>
              <App />
            </AuthProvider>
          </BrowserRouter>
        </QueryClientProvider>
      </AntApp>
    </ConfigProvider>
  </React.StrictMode>,
);
