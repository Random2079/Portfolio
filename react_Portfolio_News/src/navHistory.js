/** Hash routes for tab + optional Day review ticker. Examples: `#/news`, `#/home?t=SBER` */

const TABS = new Set(["home", "news", "ops", "calendar"]);

export function parseNavHash(hash = typeof window !== "undefined" ? window.location.hash : "") {
  const raw = String(hash || "")
    .replace(/^#\/?/, "")
    .trim();
  if (!raw) return { tab: "home", selected: "" };
  const q = raw.indexOf("?");
  const path = (q >= 0 ? raw.slice(0, q) : raw).toLowerCase();
  const query = q >= 0 ? raw.slice(q + 1) : "";
  const tab = TABS.has(path) ? path : "home";
  let selected = "";
  if (tab === "home" && query) {
    const t = new URLSearchParams(query).get("t");
    selected = String(t || "")
      .trim()
      .toUpperCase();
  }
  return { tab, selected };
}

export function navHash({ tab, selected }) {
  const t = TABS.has(tab) ? tab : "home";
  const id =
    t === "home"
      ? String(selected || "")
          .trim()
          .toUpperCase()
      : "";
  return id ? `#/${t}?t=${encodeURIComponent(id)}` : `#/${t}`;
}

export function navKey({ tab, selected }) {
  const t = TABS.has(tab) ? tab : "home";
  const id =
    t === "home"
      ? String(selected || "")
          .trim()
          .toUpperCase()
      : "";
  return `${t}|${id}`;
}

export function viewFromState(state) {
  if (state && TABS.has(state.tab)) {
    const selected =
      state.tab === "home"
        ? String(state.selected || "")
            .trim()
            .toUpperCase()
        : "";
    return { tab: state.tab, selected };
  }
  return parseNavHash();
}
