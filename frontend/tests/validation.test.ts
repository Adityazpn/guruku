import { describe, expect, it } from "vitest";
import { validateEmail, validatePassword } from "../lib/validation";

describe("validation", () => {
  it("accepts and rejects emails", () => {
    expect(validateEmail("guru@sekolah.id")).toBeNull();
    expect(validateEmail("guru@")).not.toBeNull();
    expect(validateEmail("")).not.toBeNull();
  });
  it("enforces password length", () => {
    expect(validatePassword("short")).not.toBeNull();
    expect(validatePassword("long-enough-pw")).toBeNull();
    expect(validatePassword("x".repeat(129))).not.toBeNull();
  });
});

import { toPayload, validateForm } from "../lib/form";

const schema = {
  required: ["education_level", "topic"],
  properties: {
    education_level: { enum: ["SD/MI", "SMP/MTs"] },
    topic: { type: "string", minLength: 2, maxLength: 10 },
    count: { type: "integer", minimum: 1, maximum: 10 },
  },
};

describe("tool form", () => {
  it("requires required fields and checks enums/bounds", () => {
    expect(validateForm(schema, {})).toEqual({ education_level: "Wajib diisi", topic: "Wajib diisi" });
    expect(validateForm(schema, { education_level: "SMA", topic: "x" }).education_level).toBe("Pilihan tidak valid");
    expect(validateForm(schema, { education_level: "SD/MI", topic: "Pecahan", count: "11" }).count).toBe("Maksimal 10");
    expect(validateForm(schema, { education_level: "SD/MI", topic: "Pecahan", count: "2.5" }).count).toBe("Harus bilangan bulat");
    expect(validateForm(schema, { education_level: "SD/MI", topic: "Pecahan", count: "3" })).toEqual({});
  });
  it("builds a typed payload and drops empty optionals", () => {
    expect(toPayload(schema, { education_level: "SD/MI", topic: " Pecahan ", count: "3" }))
      .toEqual({ education_level: "SD/MI", topic: "Pecahan", count: 3 });
    expect(toPayload(schema, { education_level: "SD/MI", topic: "Pecahan", count: "" })).not.toHaveProperty("count");
  });
});

import { emptyOf, findProblems } from "../lib/schema";

describe("document editor helpers", () => {
  const schema = { type: "object", properties: { judul: { type: "string", minLength: 1 }, butir: { type: "array", minItems: 1, items: { type: "string", minLength: 1 } },
    kegiatan: { type: "array", minItems: 1, items: { type: "object", properties: { nama: { type: "string", minLength: 1 }, n: { type: "integer", minimum: 1 } } } } } } as const;
  it("builds blank items from the schema", () => {
    expect(emptyOf(schema.properties.kegiatan.items as never)).toEqual({ nama: "", n: 1 });
    expect(emptyOf(schema as never)).toEqual({ judul: "", butir: [], kegiatan: [] });
  });
  it("reports empty required text and too-short lists, and accepts a complete document", () => {
    const bad = findProblems({ judul: " ", butir: [], kegiatan: [{ nama: "", n: 1 }] }, schema as never);
    expect(bad).toEqual(["Judul: tidak boleh kosong", "Butir: minimal 1 butir", "Kegiatan #1 › Nama: tidak boleh kosong"]);
    expect(findProblems({ judul: "A", butir: ["x"], kegiatan: [{ nama: "k", n: 1 }] }, schema as never)).toEqual([]);
  });
});
