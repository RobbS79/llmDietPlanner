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
    title: 'Vařto — Jídelníček s poctivým odhadem ceny',
    description: 'Zadejte sve cile a Vařto sestavi jidelnicek s recepty a nakupnim seznamem ke kazdemu receptu — s poctivym odhadem ceny a prehledem surovin ve sleve. 2 jidelnicky zdarma, bez karty. Hotovo za 60s.',
    canonical: '/',
  },
  {
    path: '/login',
    outFile: 'login/index.html',
    title: 'Přihlášení — Vařto',
    description: 'Prihlaste se ke svemu uctu Vařto a zacnete planovat sve jidelnicky s poctivym odhadem ceny.',
    canonical: '/login',
  },
  {
    path: '/pricing',
    outFile: 'pricing/index.html',
    title: 'Ceník — Vařto',
    description: 'Vařto je zdarma pro 2 jidelnicky. Placene tarify Standard (99 CZK) a Premium (199 CZK) s vice jidelnicky a prehledem akci.',
    canonical: '/pricing',
  },
  {
    path: '/o-nas',
    outFile: 'o-nas/index.html',
    title: 'O nás — Vařto',
    description: 'Vařto postavil Robert Soroka — planuje zdrava jidla a ukaze poctivy odhad, na kolik vas vyjdou. Pribeh zakladatele.',
    canonical: '/o-nas',
  },
  {
    path: '/privacy',
    outFile: 'privacy/index.html',
    title: 'Zásady ochrany soukromí — Vařto',
    description: 'Informace o zpracovani vasich osobnich udaju sluzbou Vařto v souladu s GDPR.',
    canonical: '/privacy',
  },
  {
    path: '/terms',
    outFile: 'terms/index.html',
    title: 'Obchodní podmínky — Vařto',
    description: 'Obchodni podminky pouzivani sluzby Vařto pro generovani personalizovanych jidelniku.',
    canonical: '/terms',
  },
  {
    path: '/forgot-password',
    outFile: 'forgot-password/index.html',
    title: 'Obnova hesla — Vařto',
    description: 'Obnovte pristup ke svemu uctu Vařto. Zadejte svuj e-mail a posleme vam odkaz pro obnovu hesla.',
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
