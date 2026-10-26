import { describe, expect, it } from "vitest";
import { ApiError, read } from "./api";
describe("SDK error boundary", () => {
  it("keeps the HTTP status for quota handling", async () => {
    await expect(
      read(
        Promise.resolve({
          response: new Response("", { status: 402 }),
          error: { detail: "Лимит ТС", code: "quota_exceeded" },
        }),
      ),
    ).rejects.toMatchObject({ status: 402, message: "Лимит ТС" });
  });
  it("describes validation errors without exposing request values", () => {
    expect(
      new ApiError(422, {
        detail: [{ msg: "Введите email", input: "private" }],
      }).message,
    ).toBe("Введите email");
  });
  it("shows an actionable message when fetch has no response", async () => {
    await expect(
      read(Promise.resolve({ error: new TypeError("fetch failed") })),
    ).rejects.toMatchObject({
      status: 0,
      message: expect.stringContaining("Сервер недоступен"),
    });
  });
});
