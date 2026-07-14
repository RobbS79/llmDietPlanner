// Meta Pixel loader + funnel event helpers. Everything is a no-op unless the
// user has granted consent AND VITE_FB_PIXEL_ID is set.

export const CONSENT_KEY = 'mkt_consent_v1';
export const CONSENT_VERSION = '1';
const UTM_KEY = 'mkt_attribution_v1';

export type UtmParams = {
  utm_source: string; utm_medium: string; utm_campaign: string;
  utm_content: string; utm_term: string; fbclid: string;
};

const EMPTY_UTM: UtmParams = {
  utm_source: '', utm_medium: '', utm_campaign: '',
  utm_content: '', utm_term: '', fbclid: '',
};

const PIXEL_ID = import.meta.env.VITE_FB_PIXEL_ID as string | undefined;

declare global { interface Window { fbq?: (...args: unknown[]) => void; } }

export function readUtmParams(search: string): UtmParams {
  const p = new URLSearchParams(search);
  return {
    utm_source: p.get('utm_source') ?? '',
    utm_medium: p.get('utm_medium') ?? '',
    utm_campaign: p.get('utm_campaign') ?? '',
    utm_content: p.get('utm_content') ?? '',
    utm_term: p.get('utm_term') ?? '',
    fbclid: p.get('fbclid') ?? '',
  };
}

// Capture UTM/fbclid once at landing; keep the first-touch values.
export function captureAttribution(search: string): void {
  if (localStorage.getItem(UTM_KEY)) return;
  const utm = readUtmParams(search);
  const anySet = Object.values(utm).some((v) => v !== '');
  if (anySet) localStorage.setItem(UTM_KEY, JSON.stringify(utm));
}

export function getStoredAttribution(): UtmParams {
  try { return { ...EMPTY_UTM, ...JSON.parse(localStorage.getItem(UTM_KEY) || '{}') }; }
  catch { return EMPTY_UTM; }
}

export function getConsent(): boolean | null {
  const raw = localStorage.getItem(CONSENT_KEY);
  if (raw === null) return null;
  try { return JSON.parse(raw).consent === true; } catch { return null; }
}

export function setConsent(consent: boolean): void {
  localStorage.setItem(CONSENT_KEY,
    JSON.stringify({ consent, version: CONSENT_VERSION, ts: Date.now() }));
}

// Read the pixel's first-party cookies (available only after the pixel loads).
export function readCookie(name: string): string {
  const m = document.cookie.match(new RegExp('(^|; )' + name + '=([^;]*)'));
  return m ? decodeURIComponent(m[2]) : '';
}

let loaded = false;
export function loadPixel(): void {
  if (loaded || !PIXEL_ID || getConsent() !== true) return;
  loaded = true;
  /* eslint-disable */
  (function (f: any, b: any, e: string, v: string, n?: any, t?: any, s?: any) {
    if (f.fbq) return; n = f.fbq = function () {
      n.callMethod ? n.callMethod.apply(n, arguments) : n.queue.push(arguments);
    };
    if (!f._fbq) f._fbq = n; n.push = n; n.loaded = true; n.version = '2.0';
    n.queue = []; t = b.createElement(e); t.async = true;
    t.src = v; s = b.getElementsByTagName(e)[0]; s.parentNode.insertBefore(t, s);
  })(window, document, 'script', 'https://connect.facebook.net/en_US/fbevents.js');
  /* eslint-enable */
  window.fbq!('init', PIXEL_ID);
  window.fbq!('track', 'PageView');
}

function track(event: string, params?: Record<string, unknown>): void {
  if (getConsent() !== true || !window.fbq) return;
  window.fbq('track', event, params);
}
function trackCustom(event: string, params?: Record<string, unknown>): void {
  if (getConsent() !== true || !window.fbq) return;
  window.fbq('trackCustom', event, params);
}

export const trackLandingView = () => track('PageView');
export const trackQuizStarted = () => trackCustom('QuizStarted');
export const trackCheckoutStarted = () => track('InitiateCheckout');
