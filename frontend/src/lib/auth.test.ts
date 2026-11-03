import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import axios from 'axios';
import { clearAuthTokens, confirmSession, tryRefreshToken } from './auth';
import { readBasket, toggleRecipe } from './basket';
import { RETURN_KEY } from './storageKeys';
import { setReturnIntent } from './returnIntent';

const jwt = (expSec: number) => `h.${btoa(JSON.stringify({ exp: expSec }))}.s`;

describe('auth', () => {
  beforeEach(() => { localStorage.clear(); });
  afterEach(() => { vi.restoreAllMocks(); });

  it('logout clears the basket and the return intent with the tokens', () => {
    localStorage.setItem('access_token', 'a');
    localStorage.setItem('refresh_token', 'r');
    toggleRecipe(7);
    setReturnIntent('/nakup');
    clearAuthTokens();
    expect(localStorage.getItem('refresh_token')).toBeNull();
    expect(readBasket().recipeIds).toEqual([]);
    expect(localStorage.getItem(RETURN_KEY)).toBeNull();
  });

  it('a dead refresh token drops the session but keeps the basket to save after signing in', async () => {
    localStorage.setItem('refresh_token', 'dead');
    toggleRecipe(7);
    vi.spyOn(axios, 'post').mockRejectedValue({ response: { status: 401 } });
    expect(await tryRefreshToken()).toBe(false);
    expect(localStorage.getItem('refresh_token')).toBeNull();
    expect(readBasket().recipeIds).toEqual([7]);
  });

  it('confirmSession trusts a valid access token without a network call', async () => {
    localStorage.setItem('access_token', jwt(Date.now() / 1000 + 600));
    const post = vi.spyOn(axios, 'post');
    expect(await confirmSession()).toBe(true);
    expect(post).not.toHaveBeenCalled();
  });

  it('confirmSession is false when the token is expired and refresh fails', async () => {
    localStorage.setItem('access_token', jwt(Date.now() / 1000 - 600));
    localStorage.setItem('refresh_token', 'dead');
    vi.spyOn(axios, 'post').mockRejectedValue(new Error('401'));
    expect(await confirmSession()).toBe(false);
  });
});
