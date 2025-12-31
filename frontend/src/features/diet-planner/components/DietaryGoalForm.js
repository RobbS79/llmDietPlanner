import React, { useState } from 'react';
import { useCreateDietaryGoal } from '../hooks/useDietaryGoals';
import { CountryCitySelector } from './CountryCitySelector';
import { LanguageSelector } from './LanguageSelector';
import { COUNTRY_DEFAULT_LANGUAGE } from '../types';
import './form.css';

/**
 * Main form component for creating dietary goals
 */
export function DietaryGoalForm({ onSuccess }) {
  const [prompt, setPrompt] = useState('');
  const [dietaryRestrictions, setDietaryRestrictions] = useState('');
  const [country, setCountry] = useState('');
  const [city, setCity] = useState('');
  const [languageCode, setLanguageCode] = useState('pl');
  const [errors, setErrors] = useState({});

  const createGoalMutation = useCreateDietaryGoal();

  const handleCountryChange = (newCountry) => {
    setCountry(newCountry);
    // Auto-set language based on country
    if (newCountry && COUNTRY_DEFAULT_LANGUAGE[newCountry]) {
      setLanguageCode(COUNTRY_DEFAULT_LANGUAGE[newCountry]);
    }
    // Clear country error
    if (errors.country) {
      setErrors({ ...errors, country: null });
    }
  };

  const handleCityChange = (newCity) => {
    setCity(newCity);
    // Clear city error
    if (errors.city) {
      setErrors({ ...errors, city: null });
    }
  };

  const validateForm = () => {
    const newErrors = {};

    if (!prompt.trim() || prompt.trim().length < 10) {
      newErrors.prompt = 'Please provide a dietary prompt (minimum 10 characters)';
    }

    if (!country) {
      newErrors.country = 'Please select a country';
    }

    if (!city.trim() || city.trim().length === 0) {
      newErrors.city = 'Please enter a city name';
    } else if (city.trim().length > 100) {
      newErrors.city = 'City name must be 100 characters or less';
    }

    if (dietaryRestrictions && dietaryRestrictions.length > 2000) {
      newErrors.dietaryRestrictions = 'Dietary restrictions must be 2000 characters or less';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!validateForm()) {
      return;
    }

    try {
      const result = await createGoalMutation.mutateAsync({
        prompt: prompt.trim(),
        dietary_restrictions: dietaryRestrictions.trim() || null,
        country,
        city: city.trim(),
        language_code: languageCode,
      });

      if (result.status === 'success') {
        // Reset form
        setPrompt('');
        setDietaryRestrictions('');
        setCountry('');
        setCity('');
        setLanguageCode('pl');
        setErrors({});

        // Call success callback if provided
        if (onSuccess) {
          onSuccess(result.data);
        }
      }
    } catch (error) {
      // Error is handled by React Query, but we can show a message
      setErrors({ submit: error.message || 'Failed to create dietary goal. Please try again.' });
    }
  };

  return (
    <div className="max-w-2xl mx-auto p-6 bg-white rounded-lg shadow-lg">
      <h2 className="text-2xl font-bold text-gray-800 mb-6">Create Your Dietary Goal</h2>

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Dietary Prompt */}
        <div>
          <label htmlFor="prompt" className="block text-sm font-medium text-gray-700 mb-1">
            Dietary Prompt <span className="text-red-500">*</span>
          </label>
          <textarea
            id="prompt"
            value={prompt}
            onChange={(e) => {
              setPrompt(e.target.value);
              if (errors.prompt) {
                setErrors({ ...errors, prompt: null });
              }
            }}
            placeholder="Describe your dietary goals, preferences, and what you'd like to achieve (e.g., 'I want to lose 5kg in 2 months while maintaining muscle mass')"
            rows={6}
            className={`w-full px-3 py-2 border rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 ${
              errors.prompt ? 'border-red-500' : 'border-gray-300'
            }`}
            required
            minLength={10}
            maxLength={5000}
          />
          <p className="mt-1 text-sm text-gray-500">
            {prompt.length}/5000 characters (minimum 10 required)
          </p>
          {errors.prompt && <p className="mt-1 text-sm text-red-600">{errors.prompt}</p>}
        </div>

        {/* Dietary Restrictions */}
        <div>
          <label htmlFor="restrictions" className="block text-sm font-medium text-gray-700 mb-1">
            Dietary Restrictions (Optional)
          </label>
          <textarea
            id="restrictions"
            value={dietaryRestrictions}
            onChange={(e) => {
              setDietaryRestrictions(e.target.value);
              if (errors.dietaryRestrictions) {
                setErrors({ ...errors, dietaryRestrictions: null });
              }
            }}
            placeholder="List any allergies, dietary restrictions, or preferences (e.g., 'No gluten, lactose intolerant, vegetarian')"
            rows={4}
            className={`w-full px-3 py-2 border rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 ${
              errors.dietaryRestrictions ? 'border-red-500' : 'border-gray-300'
            }`}
            maxLength={2000}
          />
          <p className="mt-1 text-sm text-gray-500">
            {dietaryRestrictions.length}/2000 characters
          </p>
          {errors.dietaryRestrictions && (
            <p className="mt-1 text-sm text-red-600">{errors.dietaryRestrictions}</p>
          )}
        </div>

        {/* Country and City */}
        <CountryCitySelector
          country={country}
          city={city}
          onCountryChange={handleCountryChange}
          onCityChange={handleCityChange}
          error={errors.country || errors.city}
        />

        {/* Language */}
        <LanguageSelector
          languageCode={languageCode}
          onLanguageChange={setLanguageCode}
        />

        {/* Submit Error */}
        {errors.submit && (
          <div className="p-3 bg-red-50 border border-red-200 rounded-md">
            <p className="text-sm text-red-600">{errors.submit}</p>
          </div>
        )}

        {/* Success Message */}
        {createGoalMutation.isSuccess && !errors.submit && (
          <div className="p-3 bg-green-50 border border-green-200 rounded-md">
            <p className="text-sm text-green-600">
              Dietary goal created successfully! Processing will begin shortly.
            </p>
          </div>
        )}

        {/* Submit Button */}
        <div className="flex justify-end">
          <button
            type="submit"
            disabled={createGoalMutation.isPending}
            className={`px-6 py-2 rounded-md font-medium text-white ${
              createGoalMutation.isPending
                ? 'bg-gray-400 cursor-not-allowed'
                : 'bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500'
            } transition-colors`}
          >
            {createGoalMutation.isPending ? 'Creating...' : 'Create Dietary Goal'}
          </button>
        </div>
      </form>
    </div>
  );
}

