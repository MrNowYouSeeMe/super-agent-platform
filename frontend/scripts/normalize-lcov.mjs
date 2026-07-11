import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

const lcovPath = resolve("coverage", "lcov.info");
let content = readFileSync(lcovPath, "utf8");

content = content.replace(/^SF:(?![A-Za-z]:[\\/]|\/)(.+)$/gm, (_match, filePath) => {
  const normalized = String(filePath).replaceAll("\\", "/");
  return normalized.startsWith("frontend/")
    ? `SF:${normalized}`
    : `SF:frontend/${normalized}`;
});

const hasAppCoverage =
  content.includes("SF:frontend/src/App.tsx") ||
  /SF:.*\/frontend\/src\/App\.tsx/m.test(content);

if (!hasAppCoverage) {
  throw new Error("LCOV did not contain frontend/src/App.tsx");
}

writeFileSync(lcovPath, content, "utf8");
