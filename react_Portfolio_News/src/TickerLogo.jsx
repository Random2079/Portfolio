import { useState } from "react";

/** Offline dumps from Portfolio_News/static/logos (same as vanilla). */
const LOCAL_LOGOS = Object.fromEntries(
  [
    "BELU",
    "BSPB",
    "CHMF",
    "GMKN",
    "GOLD",
    "HEAD",
    "HNFG",
    "IRAO",
    "LEAS",
    "LKOH",
    "LSNGP",
    "MAGN",
    "MDMG",
    "MOEX",
    "MTSS",
    "OZON",
    "PLZL",
    "ROSN",
    "SBER",
    "SIBN",
    "SPBE",
    "SVCB",
    "T",
    "TATN",
    "TATNP",
    "TRNFP",
    "X5",
    "YDEX",
  ]
    .map((t) => [t, `/static/logos/${t}.png`])
    .concat([["BCSR", "/static/logos/BCSR.svg"]])
);

function hueFor(id) {
  let h = 0;
  const s = String(id || "");
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
  return h % 360;
}

function logoUrl(ticker, isin) {
  const id = String(ticker || "")
    .trim()
    .toUpperCase();
  if (id && LOCAL_LOGOS[id]) return LOCAL_LOGOS[id];
  const is = String(isin || "")
    .trim()
    .toUpperCase();
  if (!is) return "";
  return `https://invest-brands.cdn-tinkoff.ru/${encodeURIComponent(is)}x160.png`;
}

/**
 * Avatar like vanilla assetAvatarHtml — local PNG/SVG, else Tinkoff CDN by ISIN, else initials.
 */
export default function TickerLogo({ ticker, isin, title }) {
  const id = String(ticker || "?")
    .trim()
    .toUpperCase();
  const initials = id.replace(/[^A-Z0-9]/g, "").slice(0, 2) || "?";
  const url = logoUrl(id, isin);
  const [hasImg, setHasImg] = useState(false);
  const [failed, setFailed] = useState(false);
  const bg = `hsl(${hueFor(id)} 42% 42%)`;

  return (
    <span
      className={"logo-wrap" + (hasImg && !failed ? " has-img" : "")}
      title={title || isin || id}
    >
      {url && !failed ? (
        <img
          alt=""
          loading="lazy"
          referrerPolicy="no-referrer"
          src={url}
          onLoad={() => setHasImg(true)}
          onError={() => {
            setFailed(true);
            setHasImg(false);
          }}
        />
      ) : null}
      <span className="fb" style={{ background: bg }}>
        {initials}
      </span>
    </span>
  );
}
