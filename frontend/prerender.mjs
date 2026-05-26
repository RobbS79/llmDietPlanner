import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const DIST = resolve(__dirname, 'dist');
const SITE_URL = process.env.SITE_URL || 'https://squid-app-6avsy.ondigitalocean.app';

// Shim browser globals before importing the SSR bundle
globalThis.localStorage = {
  getItem: () => null,
  setItem: () => {},
  removeItem: () => {},
  clear: () => {},
  length: 0,
  key: () => null,
};

const routes = [
  {
    path: '/',
    outFile: 'index.html',
    title: 'DietPlanner AI — Jidelnicek na miru s cenami z vasich obchodu',
    description: 'Zadejte sve cile, AI vytvori jidelnicek s recepty a nakupnim seznamem s cenami z Rohliku ci Kauflandu. 10 planu zdarma, bez karty. Hotovo za 60s.',
    canonical: '/',
  },
  {
    path: '/login',
    outFile: 'login/index.html',
    title: 'Prihlaseni — DietPlanner AI',
    description: 'Prihlaste se ke svemu uctu DietPlanner AI a zacnete planovat sve jidelni plany s realnimi cenami z obchodu.',
    canonical: '/login',
  },
  {
    path: '/pricing',
    outFile: 'pricing/index.html',
    title: 'Cenik — DietPlanner AI',
    description: 'DietPlanner AI je zdarma pro 10 planu. Pro plan od 99 CZK/mesic s neomezenymi jidelniky, realnimi cenami a exportem.',
    canonical: '/pricing',
  },
  {
    path: '/privacy',
    outFile: 'privacy/index.html',
    title: 'Zasady ochrany soukromi — DietPlanner AI',
    description: 'Informace o zpracovani vasich osobnich udaju sluzbou DietPlanner AI v souladu s GDPR.',
    canonical: '/privacy',
  },
  {
    path: '/terms',
    outFile: 'terms/index.html',
    title: 'Obchodni podminky — DietPlanner AI',
    description: 'Obchodni podminky pouzivani sluzby DietPlanner AI pro generovani personalizovanych jidelniku.',
    canonical: '/terms',
  },
  {
    path: '/forgot-password',
    outFile: 'forgot-password/index.html',
    title: 'Obnova hesla — DietPlanner AI',
    description: 'Obnovte pristup ke svemu uctu DietPlanner AI. Zadejte svuj e-mail a posleme vam odkaz pro obnovu hesla.',
    canonical: '/forgot-password',
  },
];

async function prerender() {
  const template = readFileSync(resolve(DIST, 'index.html'), 'utf-8');
  const { render } = await import(resolve(DIST, 'server', 'entry-server.js'));

  for (const route of routes) {
    console.log(`Prerendering ${route.path} ...`);

    const appHtml = render(route.path);

    let html = template;

    // Inject rendered HTML into the SSR outlet
    html = html.replace('<!--ssr-outlet-->', appHtml);

    // Per-route <title>
    html = html.replace(
      /<title>.*?<\/title>/,
      `<title>${route.title}</title>`
    );

    // Per-route <meta description>
    html = html.replace(
      /<meta name="description" content="[^"]*" \/>/,
      `<meta name="description" content="${route.description}" />`
    );

    // Per-route canonical
    html = html.replace(
      /<link rel="canonical" href="[^"]*" \/>/,
      `<link rel="canonical" href="${SITE_URL}${route.canonical}" />`
    );

    // Per-route OG tags
    html = html.replace(
      /<meta property="og:title" content="[^"]*" \/>/,
      `<meta property="og:title" content="${route.title}" />`
    );
    html = html.replace(
      /<meta property="og:description" content="[^"]*" \/>/,
      `<meta property="og:description" content="${route.description}" />`
    );
    html = html.replace(
      /<meta property="og:url" content="[^"]*" \/>/,
      `<meta property="og:url" content="${SITE_URL}${route.canonical}" />`
    );

    // Per-route Twitter tags
    html = html.replace(
      /<meta name="twitter:title" content="[^"]*" \/>/,
      `<meta name="twitter:title" content="${route.title}" />`
    );
    html = html.replace(
      /<meta name="twitter:description" content="[^"]*" \/>/,
      `<meta name="twitter:description" content="${route.description}" />`
    );

    const outPath = resolve(DIST, 'prerendered', route.outFile);
    mkdirSync(dirname(outPath), { recursive: true });
    writeFileSync(outPath, html);
    console.log(`  -> dist/prerendered/${route.outFile}`);
  }

  console.log(`\nPrerendered ${routes.length} routes successfully.`);
}

prerender().catch((err) => {
  console.error('Prerendering failed:', err);
  process.exit(1);
});
