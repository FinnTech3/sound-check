// render.mjs: screenshot the #frame element of a page written by make_charts.py.
//
//   node render.mjs page.html out.png [scale]
//
// Playwright must be installed (set PW_ROOT to a folder that has it in node_modules if it is not next to this file).
import { createRequire } from 'node:module';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const { chromium } = createRequire(process.env.PW_ROOT ? `${process.env.PW_ROOT}/` : import.meta.url)('playwright');
const [, , input, out, scale] = process.argv;
if (!input || !out) {
  console.error('usage: node render.mjs page.html out.png [scale]');
  process.exit(2);
}
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1400, height: 1000 }, deviceScaleFactor: Number(scale || 2) });
await page.goto(pathToFileURL(path.resolve(input)).href);
await page.locator('#frame').screenshot({ path: out });
await browser.close();
console.log('wrote', out);
