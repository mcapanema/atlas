export async function apiFetch<T>(path: string): Promise<T> {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
  });
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return (await response.json()) as T;
}
