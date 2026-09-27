/**
 * Same-origin by default (serve /app/ or Vite proxy /api → :8765).
 * Override: VITE_API_BASE=http://127.0.0.1:8765
 */
export const API_BASE = (import.meta.env.VITE_API_BASE || "").replace(/\/$/, "");

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

export async function postJson(path, body) {
  const url = urlFor(path);
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body ?? {}),
  });
  let data = null;
  try {
    data = await res.json();
  } catch {
    data = null;
  }
  if (!res.ok) {
    const detail =
      data && (data.detail || data.error)
        ? typeof data.detail === "string"
          ? data.detail
          : typeof data.error === "string"
            ? data.error
            : JSON.stringify(data.detail || data.error)
        : res.statusText || String(res.status);
    throw new Error(detail);
  }
  return data;
}
