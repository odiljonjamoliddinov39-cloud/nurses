// Fails if a string passed to t()/tx() (or listed in a label/help/option table) has no uz+ru translation.
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

const src = join(import.meta.dirname, "..", "src");
const files = ["App.tsx", "ui.tsx", ...readdirSync(join(src, "pages")).map((f) => `pages/${f}`)];
const lit = String.raw`"((?:[^"\\]|\\.)*)"`;
const have = new Set();
for (const m of readFileSync(join(src, "i18n.tsx"), "utf8").matchAll(new RegExp(String.raw`^\s*${lit}:\s*(?:\[|$)`, "gm"))) have.add(JSON.parse(`"${m[1]}"`));

const used = new Map();
const add = (k, f) => { k = JSON.parse(`"${k}"`); if (/[A-Za-z]/.test(k)) used.set(k, f); };
for (const f of files) {
  const text = readFileSync(join(src, f), "utf8");
  for (const m of text.matchAll(new RegExp(String.raw`\bt[x]?\(\s*${lit}`, "g"))) add(m[1], f);
  for (const m of text.matchAll(new RegExp(String.raw`\bt\([^"()]*\?\s*${lit}\s*:\s*${lit}`, "g"))) { add(m[1], f); add(m[2], f); }
  for (const m of text.matchAll(new RegExp(String.raw`\b(?:label|help):\s*${lit}`, "g"))) add(m[1], f);
  for (const m of text.matchAll(new RegExp(String.raw`\["[a-z]+",\s*(?=\"[A-Z])${lit}\]`, "g"))) add(m[1], f);
}
const gaps = [...used].filter(([k]) => !have.has(k));
for (const [k, f] of gaps) console.log(`missing  ${f}: ${k}`);
console.log(`${used.size} strings checked, ${gaps.length} missing`);
process.exit(gaps.length ? 1 : 0);
