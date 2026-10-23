// Rasterize the unmodified Apache SVG locally; no external URLs are loaded.
import { chromium } from '../frontend/node_modules/playwright/index.mjs';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const output = path.resolve(root, process.env.CSI_FLINK_BENCHMARK_OUTPUT || 'docs/benchmarks/flink');
const browser = await chromium.launch({ headless: true, channel: 'chrome' });
try {
  const page = await browser.newPage({ viewport: { width: 1000, height: 760 }, deviceScaleFactor: 1 });
  await page.route('**/*', route => route.abort());
  await page.setContent('<html><body style="margin:24px;background:white">' +
    readFileSync(path.join(output, 'architecture.svg'), 'utf8') + '</body></html>');
  await page.locator('svg').screenshot({ path: path.join(output, 'architecture.png') });
} finally {
  await browser.close();
}
