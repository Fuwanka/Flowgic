/** Одна JWT-сессия на вкладку. sessionStorage переживает reload, но не хранится бессрочно. */
import type { TokenPairOut } from "../client/types.gen";

const KEY = "flowgic.session.v1";
let tokens: TokenPairOut | null = null;
try {
  const raw =
    typeof sessionStorage === "undefined" ? null : sessionStorage.getItem(KEY);
  const value = raw ? JSON.parse(raw) : null;
  if (
    value &&
    typeof value.access === "string" &&
    typeof value.refresh === "string"
  )
    tokens = value;
} catch {
  /* Закрытое хранилище или повреждённая запись означают новый вход. */
}
let generation = 0;
let refreshPromise: Promise<TokenPairOut> | null = null;
const listeners = new Set<() => void>();
export const getSession = () => tokens;
export const subscribeSession = (listener: () => void) => {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
};
export function setSession(value: TokenPairOut | null) {
  tokens = value;
  generation += 1;
  try {
    if (typeof sessionStorage !== "undefined") {
      if (value) sessionStorage.setItem(KEY, JSON.stringify(value));
      else sessionStorage.removeItem(KEY);
    }
  } catch {
    /* Вход остаётся доступным в памяти даже без browser storage. */
  }
  listeners.forEach((listener) => listener());
}

export async function refreshSession(): Promise<TokenPairOut> {
  if (refreshPromise) return refreshPromise;
  if (!tokens) throw new Error("Сессия завершена");
  const snapshot = tokens;
  const startedAt = generation;
  refreshPromise = (async () => {
    try {
      const origin =
        typeof window === "undefined"
          ? "http://localhost"
          : window.location.origin;
      const response = await fetch(`${origin}/api/accounts/token/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh: snapshot.refresh }),
      });
      if (!response.ok) throw new Error("Сессия истекла");
      const pair = (await response.json()) as TokenPairOut;
      if (startedAt !== generation) throw new Error("Сессия уже изменена");
      setSession(pair);
      return pair;
    } catch (error) {
      // Ответ старого refresh не должен ни восстановить logout, ни удалить новый login.
      if (startedAt === generation) setSession(null);
      throw error;
    } finally {
      refreshPromise = null;
    }
  })();
  return refreshPromise;
}

export const authorizedFetch: typeof fetch = async (input, init) => {
  const request = new Request(input, init);
  const response = await fetch(request.clone());
  if (
    response.status !== 401 ||
    !tokens ||
    !request.headers.has("Authorization")
  )
    return response;
  // Параллельные запросы используют один refresh. Повторяется лишь отклонённый JWT-запрос.
  try {
    const pair =
      request.headers.get("Authorization") !== `Bearer ${tokens.access}`
        ? tokens
        : await refreshSession();
    const headers = new Headers(request.headers);
    headers.set("Authorization", `Bearer ${pair.access}`);
    return fetch(new Request(request, { headers }));
  } catch {
    return response;
  }
};
