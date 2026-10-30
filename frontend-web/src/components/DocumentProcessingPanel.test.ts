import { describe, expect, it } from "vitest";
import {
  DOCUMENT_FIELD_GROUPS,
  documentFieldValues,
  validateProcessingUpload,
} from "./DocumentProcessingPanel";

describe("document upload validation", () => {
  it.each([
    ["накладная.PDF", "application/pdf"],
    ["весовой-талон.jpeg", "image/jpeg"],
    ["упд.png", "image/png"],
    ["скан.jpg", ""],
  ])("accepts supported document %s", (name, type) => {
    expect(validateProcessingUpload({ name, type, size: 20 * 1024 * 1024 })).toBeNull();
  });
  it("rejects empty files, oversized files and misleading extensions", () => {
    expect(validateProcessingUpload({ name: "scan.pdf", type: "application/pdf", size: 0 })).toContain("пустой");
    expect(validateProcessingUpload({ name: "scan.pdf", type: "application/pdf", size: 20 * 1024 * 1024 + 1 })).toContain("20 МБ");
    expect(validateProcessingUpload({ name: "scan.pdf", type: "text/html", size: 100 })).toContain("PDF, JPEG или PNG");
    expect(validateProcessingUpload({ name: "scan.svg", type: "image/png", size: 100 })).toContain("PDF, JPEG или PNG");
  });
});

describe("review fields", () => {
  it("keeps all 37 approved fields unique and editable when OCR misses them", () => {
    const fields = DOCUMENT_FIELD_GROUPS.flatMap((group) => group.fields.map(([id]) => id));
    expect(fields).toHaveLength(37);
    expect(new Set(fields).size).toBe(37);
    const values = documentFieldValues({ cargo_description: { value: "Щебень 5–20" }, cargo_mass: { value: null } });
    expect(Object.keys(values)).toHaveLength(37);
    expect(values.cargo_description).toBe("Щебень 5–20");
    expect(values.cargo_mass).toBe("");
    expect(values.loading_address).toBe("");
  });
  it("does not expose unexpected server fields as editable order data", () => {
    expect(documentFieldValues({ company_id: { value: "other-company" } })).not.toHaveProperty("company_id");
  });
});
