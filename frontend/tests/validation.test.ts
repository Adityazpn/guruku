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
