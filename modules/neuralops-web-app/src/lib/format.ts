// Compact numbers for usage lines: exact under a thousand, one decimal
// past it, and no trailing ".0".
export function formatTokens(n: number): string {
  const fmt = (v: number, unit: string) => `${(Math.round(v * 10) / 10).toString().replace(/\.0$/, "")}${unit}`;
  if (n >= 1e9) return fmt(n / 1e9, "B");
  if (n >= 1e6) return fmt(n / 1e6, "M");
  if (n >= 1e3) return fmt(n / 1e3, "k");
  return String(n);
}

// Dollars with cents; below a cent, enough digits to be seen at all.
export function formatUsd(n: number): string {
  const digits = n > 0 && n < 0.01 ? 4 : 2;
  return `$${n.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits })}`;
}
