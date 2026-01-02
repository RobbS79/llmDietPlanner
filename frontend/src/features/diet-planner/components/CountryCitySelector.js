import React from 'react';
import { COUNTRIES } from '../types';

/**
 * Country and City selector component
 * @param {Object} props
 * @param {string} props.country
 * @param {string} props.city
 * @param {Function} props.onCountryChange
 * @param {Function} props.onCityChange
 * @param {boolean} [props.showLabel]
 * @param {string} [props.error]
 */
export function CountryCitySelector({
  country,
  city,
  onCountryChange,
  onCityChange,
  showLabel = true,
  error,
}) {
  return (
    <div className="space-y-4">
      {/* Country Selector */}
      <div>
        {showLabel && (
          <label htmlFor="country" className="block text-sm font-medium text-gray-700 mb-1">
            Country <span className="text-red-500">*</span>
          </label>
        )}
        <select
          id="country"
          value={country}
          onChange={(e) => onCountryChange(e.target.value)}
          className={`w-full px-3 py-2 border rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 ${
            error ? 'border-red-500' : 'border-gray-300'
          }`}
          required
        >
          <option value="">Select a country</option>
          {COUNTRIES.map(({ code, name }) => (
            <option key={code} value={code}>
              {name}
            </option>
          ))}
        </select>
        {error && <p className="mt-1 text-sm text-red-600">{error}</p>}
      </div>

      {/* City Input */}
      <div>
        {showLabel && (
          <label htmlFor="city" className="block text-sm font-medium text-gray-700 mb-1">
            City <span className="text-red-500">*</span>
          </label>
        )}
        <input
          type="text"
          id="city"
          value={city}
          onChange={(e) => onCityChange(e.target.value)}
          placeholder="Enter city name"
          className={`w-full px-3 py-2 border rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 ${
            error ? 'border-red-500' : 'border-gray-300'
          }`}
          required
          minLength={1}
          maxLength={100}
        />
        {error && <p className="mt-1 text-sm text-red-600">{error}</p>}
      </div>
    </div>
  );
}

