/**
 * TypeScript-style type definitions for dietary goals
 * (Using JSDoc for type hints since this is a .js project)
 */

/**
 * @typedef {Object} DietaryGoalCreateRequest
 * @property {string} prompt - User's dietary prompt (min 10 chars)
 * @property {string} [dietary_restrictions] - Optional dietary restrictions
 * @property {string} country - Country code (DE, PL, CZ, SK, HU, RO, BG, AT)
 * @property {string} city - City name (min 1 char, max 100)
 * @property {string} [language_code] - Language code (default: "pl")
 */

/**
 * @typedef {Object} DietaryGoalResponse
 * @property {number} id
 * @property {string} status
 * @property {string} country
 * @property {string} city
 * @property {string} currency
 * @property {string} language_code
 * @property {string} created_at
 * @property {string} updated_at
 * @property {string} [completed_at]
 */

/**
 * @typedef {Object} ApiResponse
 * @property {string} status - "success" | "error"
 * @property {*} data
 * @property {string} [error]
 */

// MVP: Only Slovakia and Czechia supported
export const COUNTRIES = [
  { code: 'CZ', name: 'Czech Republic' },
  { code: 'SK', name: 'Slovakia' },
];

export const LANGUAGES = [
  { code: 'pl', name: 'Polish' },
  { code: 'en', name: 'English' },
  { code: 'de', name: 'German' },
  { code: 'cs', name: 'Czech' },
  { code: 'sk', name: 'Slovak' },
  { code: 'hu', name: 'Hungarian' },
  { code: 'ro', name: 'Romanian' },
  { code: 'bg', name: 'Bulgarian' },
];

// Default language mapping by country (MVP: only CZ and SK)
export const COUNTRY_DEFAULT_LANGUAGE = {
  CZ: 'cs',
  SK: 'sk',
};

