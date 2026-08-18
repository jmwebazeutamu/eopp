/**
 * Screenshot and measure the running web app.
 *
 * jsdom applies no stylesheet, so the vitest suite cannot see a layout fault —
 * `/dashboard/programme` rendered blank in a browser while every test passed.
 * This drives a real engine so geometry claims can be measured rather than
 * asserted from the source.
 *
 * Signs in by minting a JWT through `manage.py` and writing it into
 * localStorage, so it needs no password and mutates no account.
 *
 * Chromium comes from the playwright download cache, deliberately *not* from
 * package.json: it is a local verification tool, not a dependency of the app.
 *
 *   npx playwright install chromium          # once
 *   node scripts/shoot.mjs --user cm1 --out .shots/before
 *   node scripts/shoot.mjs --user cm1 --out .shots/after --routes /cases,/alerts
 *
 * Writes <out>/<route>.<width>.png and prints a measurement table.
 */
import { execFileSync } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const npxRoot = execFileSync("bash", [
  "-c",
  "ls -d /home/ubuntu/.npm/_npx/*/node_modules/playwright 2>/dev/null | head -1",
]).toString().trim();
if (!npxRoot) {
  console.error("playwright not found — run: npx playwright install --with-deps chromium");
  process.exit(1);
}
const { chromium } = require(npxRoot);

const arg = (name, fallback) => {
  const i = process.argv.indexOf(`--${name}`);
  return i === -1 ? fallback : process.argv[i + 1];
};

const USER = arg("user", "cm1");
const OUT = arg("out", ".shots/current");
const BASE = arg("base", "http://localhost:8100");
const ROUTES = arg("routes", "/cases,/referrals,/alerts,/dashboard/my-work").split(",");
// --pref rail.collapsed=true — seed a per-user preference before the app boots,
// so a stored state can be photographed without scripting a click.
const PREFS = (arg("pref", "") || "").split(",").filter(Boolean).map((pair) => pair.split("="));
// The brief's two reference sizes: laptop, and a 390px phone.
const SIZES = (arg("sizes", "1440x900,390x844")).split(",").map((pair) => {
  const [w, h] = pair.split("x").map(Number);
  return { w, h, label: `${w}` };
});

/** Mint an access token in the container. No password, no account change. */
function mintToken(username) {
  const py = `
from rest_framework_simplejwt.tokens import RefreshToken
from apps.users.models import User
u = User.objects.get(username="${username}")
r = RefreshToken.for_user(u)
print("TOKEN:%s:%s:%s" % (r.access_token, r, u.id))
`;
  const out = execFileSync(
    "docker",
    ["compose", "-f", "docker-compose.yml", "-f", "docker-compose.dev.yml",
     "exec", "-T", "web", "python", "manage.py", "shell", "-v", "0"],
    { cwd: new URL("../infra", import.meta.url).pathname, input: py },
  ).toString();
  const line = out.split("\n").find((l) => l.startsWith("TOKEN:"));
  if (!line) throw new Error(`could not mint a token for ${username}:\n${out}`);
  const [, access, refresh, userId] = line.trim().split(":");
  return { access, refresh, userId };
}

const { access, refresh, userId: USER_ID } = mintToken(USER);
mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch();
const rows = [];
const consoleErrors = [];

for (const size of SIZES) {
  const context = await browser.newContext({
    viewport: { width: size.w, height: size.h },
    deviceScaleFactor: 1,
  });
  // Seed the session before any app code runs.
  await context.addInitScript(
    ([a, r, userId, prefs]) => {
      localStorage.setItem("yep.access", a);
      localStorage.setItem("yep.refresh", r);
      for (const [name, value] of prefs) {
        localStorage.setItem(`yep.pref.${userId}.${name}`, value);
      }
    },
    [access, refresh, USER_ID, PREFS],
  );
  const page = await context.newPage();
  page.on("console", (m) => {
    if (m.type() === "error") consoleErrors.push(`[${size.label}] ${m.text()}`);
  });
  page.on("pageerror", (e) => consoleErrors.push(`[${size.label}] ${e.message}`));

  for (const route of ROUTES) {
    await page.goto(`${BASE}${route}`, { waitUntil: "networkidle" });
    // Let the counter/summary fetches settle; they arrive after first paint.
    await page.waitForTimeout(1200);

    const slug = route.replace(/^\//, "").replace(/\//g, "-") || "root";
    const file = `${OUT}/${slug}.${size.w}x${size.h}.png`;
    await page.screenshot({ path: file, fullPage: process.argv.includes("--full") });

    /**
     * Content-top to first data row. "Content top" is the top of the main
     * column's first child, not the viewport — the header is chrome, and the
     * brief measures how much chrome sits between arriving and reading data.
     */
    const measured = await page.evaluate(() => {
      const px = (el) => (el ? Math.round(el.getBoundingClientRect().top) : null);
      // Only elements the breakpoint actually shows. `.only-laptop` is
      // `display:none` on a phone, and a hidden node reports a rect of 0 —
      // which read as "no chrome at all" instead of "wrong element".
      const shown = (sel) =>
        [...document.querySelectorAll(sel)].find((el) => el.getClientRects().length > 0) ?? null;
      const main = shown("main") ?? shown(".page");
      const page = shown(".page");
      const firstRow = shown("tbody tr") ?? shown(".card");
      // The brief's target is content top to the *table header*, which is what
      // a reader has to scroll past before the data starts.
      const tableHead = shown("thead th") ?? shown("thead");
      const heading = shown("h1");
      return {
        viewportTop: px(main),
        contentTop: px(page),
        headingTop: px(heading),
        tableHeadTop: px(tableHead),
        firstRowTop: px(firstRow),
        bodyText: (document.body.innerText || "").slice(0, 160).replace(/\s+/g, " "),
        // A blank page renders almost nothing; this is the guard the
        // programme-dashboard bug slipped past.
        renderedChars: (document.body.innerText || "").trim().length,
      };
    });

    rows.push({
      route,
      size: `${size.w}x${size.h}`,
      ...measured,
      toFirstRow:
        measured.firstRowTop != null && measured.headingTop != null
          ? measured.firstRowTop - measured.headingTop
          : null,
      toTableHead:
        measured.tableHeadTop != null && measured.contentTop != null
          ? measured.tableHeadTop - measured.contentTop
          : null,
      // "The first table row must be visible without scrolling at 1440x900."
      firstRowVisible: measured.firstRowTop != null && measured.firstRowTop < size.h,
      file,
    });
  }
  await context.close();
}
await browser.close();

writeFileSync(`${OUT}/measurements.json`, JSON.stringify({ user: USER, rows, consoleErrors }, null, 2));

const pad = (s, n) => String(s ?? "—").padEnd(n);
console.log(`\nsigned in as ${USER}\n`);
console.log(
  pad("route", 22) + pad("size", 10) + pad("top→thead", 11) + pad("row top", 9) +
  pad("row seen", 10) + "chars",
);
for (const r of rows) {
  console.log(
    pad(r.route, 22) + pad(r.size, 10) + pad(r.toTableHead, 11) + pad(r.firstRowTop, 9) +
    pad(r.firstRowVisible ? "yes" : "NO", 10) + r.renderedChars,
  );
}
if (consoleErrors.length) {
  console.log(`\n${consoleErrors.length} console error(s):`);
  for (const e of [...new Set(consoleErrors)].slice(0, 12)) console.log("  " + e);
}

/*
 * Accessibility auditing
 * ----------------------
 * axe-core drives the same chromium this script uses. It is deliberately not a
 * package.json dependency — the field brief treats bundle weight as a real cost
 * — so install it outside the project and point a script at it:
 *
 *   mkdir -p /tmp/axe && cd /tmp/axe && npm init -y && npm install axe-core
 *   node audit.mjs        # injects axe.min.js, runs window.axe.run per route
 *
 * The 2026-08-18 pass took the app from 120 violation nodes to 18 across 11
 * routes at two breakpoints. What it caught that hand review had not: the rail
 * section labels at 3.42:1, --ink-400 failing on three of the four surfaces it
 * lands on, and the filter pill's 65%-opacity count at 2.95:1.
 */
