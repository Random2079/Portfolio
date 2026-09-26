/** Vanilla Portfolio_News API (python -m portfolio_news serve). */
export const API_BASE =
  (import.meta.env.VITE_API_BASE || "http://127.0.0.1:8765").replace(/\/$/, "");

function urlFor(path) {
  return path.startsWith("http")
    ? path
    : `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`;
}

export async function getJson(path) {
  const url = urlFor(path);
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${res.status} ${url}`);
  return res.json();
}

export async function putJson(path, body) {
  const url = urlFor(path);
  const res = await fetch(url, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
  });
  if (!res.ok) throw new Error(`${res.status} ${url}`);
  return res.json();
}
