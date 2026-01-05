import React from 'react';
import { LANGUAGES } from '../types';

/**
 * Language selector component
 * @param {Object} props
 * @param {string} props.languageCode
 * @param {Function} props.onLanguageChange
 * @param {boolean} [props.showLabel]
 */
export function LanguageSelector({
  languageCode,
  onLanguageChange,
  showLabel = true,
}) {
  return (
    <div>
      {showLabel && (
        <label htmlFor="language" className="block text-sm font-medium text-gray-700 mb-1">
          Language
        </label>
      )}
      <select
        id="language"
        value={languageCode}
        onChange={(e) => onLanguageChange(e.target.value)}
        className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
      >
        {LANGUAGES.map(({ code, name }) => (
          <option key={code} value={code}>
            {name}
          </option>
        ))}
      </select>
    </div>
  );
}



