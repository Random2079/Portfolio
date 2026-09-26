/** Asset-class helpers — mirror vanilla dashboard-demo.html */

const KNOWN_FUNDS = {
  BCSR: 1,
  GOLD: 1,
  TMOS: 1,
  SBMX: 1,
  SBSP: 1,
  FXGD: 1,
  FXUS: 1,
  FXRU: 1,
  FXDE: 1,
  FXCN: 1,
};

export const ASSET_GROUPS = [
  { key: "stock", title: "Акции" },
  { key: "fund", title: "Фонды" },
  { key: "bond", title: "Облигации" },
  { key: "other", title: "Прочее" },
];

export const LIST_PREVIEW = 5;

export function paperId(h) {
  return String(h?.ticker || h?.sec_code || "")
    .trim()
    .toUpperCase();
}

/** stock | fund | bond | cash | other — prefers API asset_class */
export function assetClassOf(h) {
  const raw = String(h?.asset_class || "").toLowerCase();
  if (raw === "equity" || raw === "share" || raw === "shares") return "stock";
  if (
    raw === "stock" ||
    raw === "fund" ||
    raw === "bond" ||
    raw === "cash" ||
    raw === "other"
  ) {
    return raw;
  }
  const id = paperId(h);
  const isin = String(h?.isin || "").toUpperCase();
  if (/^(RUB|USD|EUR|CNY|HKD|GBP|CHF|CASH)$/.test(id)) return "cash";
  const cc = String(h?.class_code || "").toUpperCase();
  const name = String(h?.name || "");
  const nameL = name.toLowerCase();
  const hay = cc + " " + name;
  if (
    /TQTF|TQIF|TQTD|TQTE|ETF|BPIF|БПИФ|ПИФ/i.test(hay) ||
    /бпиф|etf|пиф/.test(nameL)
  ) {
    return "fund";
  }
  if (KNOWN_FUNDS[id]) return "fund";
  if (
    /фонд/.test(nameL) ||
    (/индекс/.test(nameL) && /мосбирж|мос биржа/.test(nameL))
  ) {
    return "fund";
  }
  if (/TQCB|TQOB|TQIR|EQOB|BOND|ОФЗ|обл|сери/i.test(hay)) return "bond";
  if (/^RU000A/i.test(id) || /^RU000A/i.test(isin) || /^SU/i.test(id)) {
    return "bond";
  }
  if (/TQBR|SMAL|EQBR/i.test(cc)) return "stock";
  if (id && !/^RU000/i.test(id)) return "stock";
  return "other";
}

export function isCashHolding(h) {
  return assetClassOf(h) === "cash";
}

export function groupHoldingsByAssetClass(rows) {
  const buckets = { stock: [], fund: [], bond: [], other: [], cash: [] };
  for (const h of rows || []) {
    const ac = assetClassOf(h);
    (buckets[ac] || buckets.other).push(h);
  }
  for (const key of Object.keys(buckets)) {
    buckets[key].sort((a, b) => {
      const va = Number(a.market_value);
      const vb = Number(b.market_value);
      const na = Number.isFinite(va) ? va : -Infinity;
      const nb = Number.isFinite(vb) ? vb : -Infinity;
      return nb - na;
    });
  }
  return ASSET_GROUPS.filter((g) => buckets[g.key]?.length).map((g) => ({
    key: g.key,
    title: g.title,
    rows: buckets[g.key],
  }));
}

export function sumField(rows, key) {
  let s = 0;
  let ok = false;
  for (const r of rows || []) {
    if (r[key] != null && !Number.isNaN(Number(r[key]))) {
      s += Number(r[key]);
      ok = true;
    }
  }
  return ok ? s : null;
}

export function countPapersByKind(papers) {
  const c = { equity: 0, bond: 0, fund: 0 };
  for (const h of papers || []) {
    const ac = assetClassOf(h);
    if (ac === "bond") c.bond += 1;
    else if (ac === "fund") c.fund += 1;
    else if (ac !== "cash") c.equity += 1;
  }
  return c;
}

export function fmtPosBreakdown(c) {
  const parts = [];
  if (c.equity) parts.push("акц " + c.equity);
  if (c.bond) parts.push("облиг " + c.bond);
  if (c.fund) parts.push("фонд " + c.fund);
  return parts.length ? parts.join(" · ") : "без бумаг";
}
