/** Общая граница с генерируемым SDK: типизированные данные и единые ошибки UI. */
import { client } from "../client/client.gen";
import { authorizedFetch, getSession } from "./session";

client.setConfig({
  baseUrl:
    typeof window === "undefined" ? "http://localhost" : window.location.origin,
  auth: () => getSession()?.access,
  fetch: authorizedFetch,
});

export class ApiError extends Error {
  constructor(
    public status: number,
    public payload: unknown,
  ) {
    const detail =
      payload && typeof payload === "object" && "detail" in payload
        ? payload.detail
        : undefined;
    const message =
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? detail.map((item) => item.msg).join(" · ")
          : "Не удалось выполнить запрос. Повторите попытку.";
    super(message);
  }
}
export async function read<T>(
  operation: Promise<{ data?: T; error?: unknown; response?: Response }>,
): Promise<T> {
  const result = await operation;
  if (!result.response)
    throw new ApiError(0, {
      detail: "Сервер недоступен. Проверьте соединение и повторите запрос.",
    });
  if (!result.response.ok || result.data === undefined)
    throw new ApiError(result.response.status, result.error);
  return result.data;
}
export const errorMessage = (error: unknown) =>
  error instanceof TypeError
    ? "Нет соединения с сервером. Повторите попытку."
    : error instanceof Error
      ? error.message
      : "Не удалось сохранить изменения.";

export function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  // Браузеру нужно время начать скачивание до освобождения временного URL.
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
