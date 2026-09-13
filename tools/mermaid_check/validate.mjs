// Real mermaid.js parse check -- not an approximation of the grammar.
// Usage: node validate.mjs <file containing raw mermaid text>
// Exit 0 + "PARSE OK" on success; exit 1 + "PARSE FAILED: <reason>" otherwise.
//
// mermaid.parse() needs a browser-like DOM even though we never render an
// SVG -- jsdom provides the minimum (document/navigator/SVGElement) it
// checks for during parsing.
import { JSDOM } from "jsdom";
import fs from "fs";

const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>");
global.window = dom.window;
global.document = dom.window.document;
global.SVGElement = dom.window.SVGElement || class {};
Object.defineProperty(global, "navigator", { value: dom.window.navigator, configurable: true });

const mermaid = (await import("mermaid")).default;
mermaid.initialize({ startOnLoad: false });

const file = process.argv[2];
if (!file) {
  console.error("usage: node validate.mjs <file>");
  process.exit(2);
}

const text = fs.readFileSync(file, "utf-8");
try {
  await mermaid.parse(text);
  console.log("PARSE OK");
  process.exit(0);
} catch (err) {
  console.error(`PARSE FAILED: ${err.message || err}`);
  process.exit(1);
}
