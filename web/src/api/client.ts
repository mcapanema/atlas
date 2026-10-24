export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (!headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const response = await fetch(path, { ...init, headers });
  if (!response.ok) {
    throw new Error(await errorDetail(response));
  }
  return (await response.json()) as T;
}

// FastAPI puts human-readable errors in a string `detail` field; 422
// validation errors carry an array of {loc, msg} there, joined as
// "<field>: <msg>" — a nested field by its path, e.g. "teams[1].overrides.x".
async function errorDetail(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown } | null;
    const detail = body?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail) && detail.length > 0) return detail.map(validationMessage).join("; ");
  } catch {
    // non-JSON error body
  }
  return `Request failed: ${response.status}`;
}

const REQUEST_PARTS = new Set(["body", "query", "path"]);

function fieldPath(loc: (string | number)[]): string {
  return loc
    .filter((part, i) => i > 0 || !REQUEST_PARTS.has(String(part)))
    .map((part, i) => (typeof part === "number" ? `[${part}]` : i === 0 ? part : `.${part}`))
    .join("");
}

function validationMessage(item: { loc?: (string | number)[]; msg?: string }): string {
  const field = item.loc ? fieldPath(item.loc) : "";
  return field === "" ? String(item.msg) : `${field}: ${String(item.msg)}`;
}
