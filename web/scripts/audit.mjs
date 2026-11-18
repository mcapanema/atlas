// `npm audit --audit-level=high` with a per-advisory ignore list (npm has none).
// ponytail: hand-kept list; delete an entry the day its package ships a fix,
// and this whole file (back to plain `npm audit --audit-level=high`) when empty.
import { execFileSync } from "node:child_process";

const IGNORED = new Map([
  // picomatch ReDoS: every release (<=4.0.7) is affected, no fix published.
  // Dev tooling only (vite/vitest/eslint/knip); `npm audit --omit=dev` is clean.
  ["GHSA-fc5q-39xc-vjpf", "picomatch, no patched release"],
]);
const FAILING = new Set(["high", "critical"]);

let raw;
try {
  raw = execFileSync("npm", ["audit", "--json"], { encoding: "utf8" });
} catch (error) {
  raw = error.stdout; // npm audit exits non-zero whenever it finds anything
}
const report = JSON.parse(raw);
if (report.error) throw new Error(`npm audit failed: ${JSON.stringify(report.error)}`);

const advisories = new Map();
for (const vuln of Object.values(report.vulnerabilities ?? {})) {
  for (const via of vuln.via) {
    if (typeof via === "object") advisories.set(via.url, via);
  }
}
const blocking = [...advisories.values()].filter(
  (a) => FAILING.has(a.severity) && !IGNORED.has(a.url.split("/").pop()),
);

for (const [id, why] of IGNORED) console.log(`ignored ${id}: ${why}`);
for (const a of blocking)
  console.error(`${a.severity}: ${a.name} ${a.range} — ${a.title} ${a.url}`);
if (blocking.length > 0) process.exit(1);
console.log("npm audit: no unignored high/critical advisories");
