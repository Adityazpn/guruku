export function validateEmail(v: string): string | null {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v.trim()) ? null : "Email tidak valid";
}

export function validatePassword(v: string): string | null {
  if (v.length < 10) return "Kata sandi minimal 10 karakter";
  if (v.length > 128) return "Kata sandi maksimal 128 karakter";
  return null;
}
