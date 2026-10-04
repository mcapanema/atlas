/**
 * External link to a work item in its origin system. The URL is third-party
 * data, so only http(s) is ever rendered as an href; anything else is a dash.
 */
function originHost(url: string | null): string | null {
  if (!url) return null;
  try {
    const { protocol, hostname } = new URL(url);
    return protocol === "https:" || protocol === "http:" ? hostname : null;
  } catch {
    return null;
  }
}

export function SourceLink({ url }: { url: string | null }) {
  const host = originHost(url);
  if (host === null) return <>—</>;
  return (
    <a href={url ?? undefined} target="_blank" rel="noopener noreferrer">
      {host} ↗
    </a>
  );
}
