function formatMinutes(totalMinutes: number): string {
  if (totalMinutes < 1) return "< 1m";
  const days = Math.floor(totalMinutes / 1440);
  const hours = Math.floor((totalMinutes % 1440) / 60);
  const minutes = totalMinutes % 60;
  if (days > 0) return hours > 0 ? `${days}d ${hours}h` : `${days}d`;
  if (hours > 0) return minutes > 0 ? `${hours}h ${minutes}m` : `${hours}h`;
  return `${minutes}m`;
}

export function formatDuration(startIso: string, endIso: string | null): string {
  const end = endIso ? new Date(endIso).getTime() : Date.now();
  return formatMinutes(Math.floor((end - new Date(startIso).getTime()) / 60_000));
}

export function formatSeconds(totalSeconds: number): string {
  if (totalSeconds === 0) return "0m";
  return formatMinutes(Math.floor(totalSeconds / 60));
}
