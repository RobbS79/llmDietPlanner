import { useSyncExternalStore } from 'react';
import { readBasket, subscribeBasket, type Basket } from './basket';

let cache = readBasket();
const subscribe = (fn: () => void) => subscribeBasket(() => { cache = readBasket(); fn(); });
export const useBasket = (): Basket => useSyncExternalStore(subscribe, () => cache, () => cache);
