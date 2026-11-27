import { useSyncExternalStore } from 'react';
import { BASKET_KEY, readBasket, subscribeBasket, type Basket } from './basket';

const raw = () => { try { return localStorage.getItem(BASKET_KEY); } catch { return null; } };
let cacheRaw = raw();
let cache = readBasket();
// Writes made while nothing was subscribed (another page, before mount) leave the
// cache stale, so re-read on subscribe when storage has moved on.
const refresh = () => { const r = raw(); if (r !== cacheRaw) { cacheRaw = r; cache = readBasket(); } };
const subscribe = (fn: () => void) => {
  refresh();
  return subscribeBasket(() => { cacheRaw = raw(); cache = readBasket(); fn(); });
};
export const useBasket = (): Basket => useSyncExternalStore(subscribe, () => cache, () => cache);
