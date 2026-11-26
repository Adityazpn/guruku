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
