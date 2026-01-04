import React, { useState, useEffect } from 'react';
import { getShopsForCountry } from '../utils/api';

/**
 * Shop selector component that fetches available shops based on country
 * Displays available shops for the selected country (CZ: Lidl, Rohlik; SK: Lidl, Lunys)
 */
export function ShopSelector({ country, shop, onShopChange, error, showLabel = true }) {
  const [shops, setShops] = useState([]);
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState(null);

  useEffect(() => {
    const fetchShops = async () => {
      if (!country) {
        setShops([]);
        onShopChange('');
        return;
      }

      setLoading(true);
      setErrorMessage(null);

      try {
        const response = await getShopsForCountry(country);
        if (response.status === 'success' && response.data && response.data.shops) {
          setShops(response.data.shops);
          // Reset shop selection when country changes
          onShopChange('');
        } else {
          setErrorMessage('Failed to load shops');
          setShops([]);
        }
      } catch (err) {
        console.error('Error fetching shops:', err);
        setErrorMessage('Failed to load shops');
        setShops([]);
      } finally {
        setLoading(false);
      }
    };

    fetchShops();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [country]);

  if (!country) {
    return null; // Don't show shop selector if no country is selected
  }

  return (
    <div>
      {showLabel && (
        <label htmlFor="shop" className="block text-sm font-medium text-gray-700 mb-1">
          Shop (Optional)
        </label>
      )}
      <select
        id="shop"
        value={shop || ''}
        onChange={(e) => onShopChange(e.target.value || null)}
        disabled={loading || shops.length === 0}
        className={`w-full px-3 py-2 border rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 ${
          error || errorMessage ? 'border-red-500' : 'border-gray-300'
        } ${loading || shops.length === 0 ? 'bg-gray-100 cursor-not-allowed' : 'bg-white'}`}
      >
        <option value="">Select a shop (optional)</option>
        {shops.map((shopOption) => (
          <option key={shopOption.code} value={shopOption.code}>
            {shopOption.name}
          </option>
        ))}
      </select>
      {loading && (
        <p className="mt-1 text-sm text-gray-500">Loading shops...</p>
      )}
      {errorMessage && (
        <p className="mt-1 text-sm text-red-600">{errorMessage}</p>
      )}
      {error && !errorMessage && (
        <p className="mt-1 text-sm text-red-600">{error}</p>
      )}
      {!loading && !errorMessage && shops.length === 0 && country && (
        <p className="mt-1 text-sm text-gray-500">No shops available for this country</p>
      )}
      {!loading && shops.length > 0 && (
        <p className="mt-1 text-xs text-gray-500">
          Select a shop to source ingredients from (optional)
        </p>
      )}
    </div>
  );
}

