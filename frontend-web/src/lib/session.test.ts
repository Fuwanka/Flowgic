import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  authorizedFetch,
  getSession,
  refreshSession,
  setSession,
} from "./session";

const old = { access: "old-access", refresh: "old-refresh" };
const next = { access: "new-access", refresh: "new-refresh" };
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
beforeEach(() => setSession(null));
afterEach(() => {
  vi.unstubAllGlobals();
  setSession(null);
});

describe("JWT rotation", () => {
  it("shares a single refresh across concurrent requests", async () => {
    setSession(old);
    const fetch = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const request = new Request(input, init);
        if (request.url.endsWith("/token/refresh")) {
          expect(await request.json()).toEqual({ refresh: old.refresh });
          return json(next);
        }
        return request.headers.get("Authorization") === `Bearer ${next.access}`
          ? json({ ok: true })
          : json({}, 401);
      },
    );
    vi.stubGlobal("fetch", fetch);
    const request = () =>
      new Request("http://localhost/api/logistics/orders", {
        headers: { Authorization: `Bearer ${old.access}` },
      });
    const results = await Promise.all([
      authorizedFetch(request()),
      authorizedFetch(request()),
      authorizedFetch(request()),
    ]);
    expect(results.every((r) => r.status === 200)).toBe(true);
    expect(
      fetch.mock.calls.filter(([input]) =>
        String(input).endsWith("/token/refresh"),
      ),
    ).toHaveLength(1);
    expect(getSession()).toEqual(next);
  });

  it("does not resurrect a session cleared during refresh", async () => {
    setSession(old);
    let finish!: (value: Response) => void;
    vi.stubGlobal(
      "fetch",
      vi.fn(
        () =>
          new Promise<Response>((resolve) => {
            finish = resolve;
          }),
      ),
    );
    const pending = refreshSession();
    setSession(null);
    finish(json(next));
    await expect(pending).rejects.toThrow("Сессия уже изменена");
    expect(getSession()).toBeNull();
  });

  it("does not discard a new login when an old refresh fails", async () => {
    setSession(old);
    let finish!: (value: Response) => void;
    vi.stubGlobal(
      "fetch",
      vi.fn(
        () =>
          new Promise<Response>((resolve) => {
            finish = resolve;
          }),
      ),
    );
    const pending = refreshSession();
    setSession(next);
    finish(json({}, 401));
    await expect(pending).rejects.toThrow();
    expect(getSession()).toEqual(next);
  });

  it("clears expired refresh tokens without an endless retry", async () => {
    setSession(old);
    const fetch = vi.fn(async () => json({}, 401));
    vi.stubGlobal("fetch", fetch);
    const response = await authorizedFetch(
      new Request("http://localhost/api/logistics/orders", {
        headers: { Authorization: "Bearer old-access" },
      }),
    );
    expect(response.status).toBe(401);
    expect(getSession()).toBeNull();
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  it("never refreshes a failed public login or retries a server error", async () => {
    setSession(old);
    const fetch = vi.fn(async () => json({}, 401));
    vi.stubGlobal("fetch", fetch);
    expect(
      (await authorizedFetch("http://localhost/api/accounts/token")).status,
    ).toBe(401);
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(getSession()).toEqual(old);
    fetch.mockResolvedValueOnce(json({}, 500));
    expect(
      (
        await authorizedFetch(
          new Request("http://localhost/api/logistics/orders", {
            headers: { Authorization: "Bearer old-access" },
          }),
        )
      ).status,
    ).toBe(500);
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  it("replays the unchanged JSON body only after an authentication rejection", async () => {
    setSession(old);
    const bodies: unknown[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const request = new Request(input, init);
        if (request.url.endsWith("/token/refresh")) return json(next);
        bodies.push(await request.json());
        return request.headers.get("Authorization") === `Bearer ${next.access}`
          ? json({ ok: true })
          : json({}, 401);
      }),
    );
    const response = await authorizedFetch(
      new Request("http://localhost/api/logistics/orders", {
        method: "POST",
        headers: {
          Authorization: `Bearer ${old.access}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ cargo_type: "Equipment" }),
      }),
    );
    expect(response.status).toBe(200);
    expect(bodies).toEqual([
      { cargo_type: "Equipment" },
      { cargo_type: "Equipment" },
    ]);
  });
});
