// Reads one filesystem path per line on stdin and exits 0 only if every one of them exists.
//
// Used by scripts/have-playwright-browsers.sh to turn `playwright install --dry-run` output
// into an actual presence check. See that script for why the obvious check does not work.
//
// Empty input is a failure, not a pass: if the parse found no "Install location:" lines at all
// then the guard learned nothing, and a guard that learned nothing must not report "present".

import { existsSync } from "node:fs";

let input = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => {
  input += chunk;
});
process.stdin.on("end", () => {
  const paths = input
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);

  if (paths.length === 0) {
    console.error("no install locations parsed; cannot confirm the browsers are present");
    process.exit(1);
  }

  const missing = paths.filter((p) => !existsSync(p));
  for (const p of missing) {
    console.error(`missing: ${p}`);
  }
  process.exit(missing.length > 0 ? 1 : 0);
});
