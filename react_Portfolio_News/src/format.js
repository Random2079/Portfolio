/** Shared display helpers (mirror vanilla dashboard). */

export function fmtRub(n, { signed = false, digits = 0 } = {}) {
  if (n == null || Number.isNaN(Number(n))) return "—";
  const v = Number(n);
  const sign = signed && v > 0 ? "+" : "";
  return (
    sign +
    v.toLocaleString("ru-RU", {
      maximumFractionDigits: digits,
      minimumFractionDigits: digits,
    }) +
    " ₽"
  );
}

export function fmtPct(n) {
  if (n == null || Number.isNaN(Number(n))) return "—";
  const v = Number(n);
  const sign = v > 0 ? "+" : "";
  return sign + v.toFixed(2) + "%";
}

export function pnlClass(n) {
  if (n == null || Number.isNaN(Number(n))) return "";
  if (Number(n) > 0) return "up";
  if (Number(n) < 0) return "down";
  return "";
}

export function qtyFmt(n) {
  if (n == null || Number.isNaN(Number(n))) return "—";
  return Number(n).toLocaleString("ru-RU");
}

export function fmtDateShort(iso) {
  if (!iso) return "—";
  const s = String(iso);
  const m = s.match(/^(\d{4}-\d{2}-\d{2})/);
  if (m) {
    const [y, mo, d] = m[1].split("-");
    return `${d}.${mo}.${y}`;
  }
  return s.slice(0, 16);
}

export function moneyShow(n) {
  if (n == null || Number.isNaN(Number(n))) return "—";
  return Number(n).toLocaleString("ru-RU", {
    maximumFractionDigits: 2,
    minimumFractionDigits: 0,
  });
}

export function shortErr(msg) {
  const s = String(msg || "").trim();
  if (!s) return "Ошибка";
  if (/ConnectTimeout|timed out|iss\.moex/i.test(s)) {
    return "MOEX не ответил — цифры из БКС/кэша";
  }
  if (s.length > 160) return s.slice(0, 157) + "…";
  return s;
}
