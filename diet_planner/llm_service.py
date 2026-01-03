"""
OpenAI LLM Service for generating dietary plans.
Handles API calls, token counting, and cost calculation.
"""
from typing import Dict, Any, Optional
import json
import logging
from decimal import Decimal

from django.conf import settings
from openai import OpenAI
import tiktoken

logger = logging.getLogger(__name__)


# OpenAI pricing per 1M tokens (as of 2024, update as needed)
# Prices in USD
OPENAI_PRICING = {
    'gpt-4o': {
        'input': 2.50,  # $2.50 per 1M input tokens
        'output': 10.00,  # $10.00 per 1M output tokens
    },
    'gpt-4o-mini': {
        'input': 0.15,  # $0.15 per 1M input tokens
        'output': 0.60,  # $0.60 per 1M output tokens
    },
    'gpt-4-turbo': {
        'input': 10.00,  # $10.00 per 1M input tokens
        'output': 30.00,  # $30.00 per 1M output tokens
    },
    'gpt-4': {
        'input': 30.00,  # $30.00 per 1M input tokens
        'output': 60.00,  # $60.00 per 1M output tokens
    },
    'gpt-3.5-turbo': {
        'input': 0.50,  # $0.50 per 1M input tokens
        'output': 1.50,  # $1.50 per 1M output tokens
    },
}


def get_model_pricing(model: str) -> Dict[str, float]:
    """
    Get pricing for a specific model.
    
    Args:
        model: Model name (e.g., 'gpt-4o', 'gpt-4o-mini')
        
    Returns:
        Dict with 'input' and 'output' prices per 1M tokens
    """
    # Handle model variants (e.g., 'gpt-4o-2024-05-13' -> 'gpt-4o')
    base_model = model.split('-')[0:3]  # Get first 3 parts (e.g., ['gpt', '4o', '2024'])
    if len(base_model) >= 2:
        base_model_name = '-'.join(base_model[:2])  # 'gpt-4o'
    else:
        base_model_name = model
    
    return OPENAI_PRICING.get(
        base_model_name,
        OPENAI_PRICING.get('gpt-4o-mini')  # Default to cheapest option
    )


def count_tokens(text: str, model: str = 'gpt-4o') -> int:
    """
    Count tokens in a text string using tiktoken.
    
    Args:
        text: Text to count tokens for
        model: Model name to use for encoding
        
    Returns:
        Number of tokens
    """
    try:
        # Map model names to tiktoken encodings
        encoding_map = {
            'gpt-4o': 'o200k_base',
            'gpt-4o-mini': 'o200k_base',
            'gpt-4-turbo': 'cl100k_base',
            'gpt-4': 'cl100k_base',
            'gpt-3.5-turbo': 'cl100k_base',
        }
        
        # Get base model for encoding
        base_model = model.split('-')[0:3]
        if len(base_model) >= 2:
            base_model_name = '-'.join(base_model[:2])
        else:
            base_model_name = model
        
        encoding_name = encoding_map.get(base_model_name, 'cl100k_base')
        
        # Get encoding
        encoding = tiktoken.get_encoding(encoding_name)
        
        # Count tokens
        return len(encoding.encode(text))
    except Exception as e:
        logger.warning(f"Error counting tokens: {e}. Using approximate count.")
        # Fallback: approximate 1 token = 4 characters
        return len(text) // 4


def calculate_cost(
    input_tokens: int,
    output_tokens: int,
    model: str
) -> Decimal:
    """
    Calculate the cost of an API call in USD.
    
    Args:
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens
        model: Model name used
        
    Returns:
        Cost in USD as Decimal
    """
    pricing = get_model_pricing(model)
    
    input_cost = (input_tokens / 1_000_000) * pricing['input']
    output_cost = (output_tokens / 1_000_000) * pricing['output']
    
    total_cost = Decimal(str(input_cost + output_cost))
    return total_cost.quantize(Decimal('0.000001'))  # Round to 6 decimal places


class OpenAIService:
    """
    Service for interacting with OpenAI API.
    Handles API calls, token counting, and cost tracking.
    """
    
    def __init__(self):
        """Initialise OpenAI client with API key from settings."""
        api_key = getattr(settings, 'OPENAI_API_KEY', None)
        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY not set in settings. "
                "Please set it as an environment variable."
            )
        
        self.client = OpenAI(api_key=api_key)
        self.default_model = getattr(
            settings,
            'OPENAI_MODEL',
            'gpt-4o-mini'  # Default to cost-effective model
        )
    
    def generate_dietary_plan(
        self,
        prompt_text: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        language_code: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generate a dietary plan using OpenAI API.
        
        Args:
            prompt_text: User prompt (JSON formatted)
            system_prompt: System prompt (optional, uses default if not provided)
            model: Model to use (optional, uses default if not provided)
            language_code: Language code for response (e.g., 'cs', 'pl', 'en')
            
        Returns:
            Dict containing:
                - 'response': LLM response content (parsed JSON)
                - 'input_tokens': Number of input tokens
                - 'output_tokens': Number of output tokens
                - 'total_tokens': Total tokens used
                - 'cost_usd': Cost in USD
                - 'model': Model used
        """
        model = model or self.default_model
        
        # Default system prompt (with language support)
        if system_prompt is None:
            # Language mapping for better prompts
            language_names = {
                'cs': 'Czech',
                'sk': 'Slovak',
                'pl': 'Polish',
                'hu': 'Hungarian',
                'ro': 'Romanian',
                'bg': 'Bulgarian',
                'de': 'German',
                'en': 'English',
            }
            target_language = language_names.get(language_code or 'en', 'English')
            
            system_prompt = (
                f"You are a nutrition expert creating personalised 7-day meal plans for users in Central and Eastern Europe. "
                f"Your responses must be valid JSON only, with no markdown formatting or code blocks. "
                f"All meal names, descriptions, and content should be in {target_language} language (language code: {language_code or 'en'}). "
                f"Focus on ingredients available in local supermarkets (Lidl, Biedronka, Kaufland, etc.). "
                f"Consider local cuisine preferences and dietary restrictions. "
                f"Generate exactly the number of recipes, small meals, and snacks as specified in the meal plan configuration. "
                f"Each meal idea must include a 'meal_type' field indicating whether it's a 'recipe', 'small_meal', or 'snack'. "
                f"Do not include prices - the system will calculate them separately."
            )
        
        # Count input tokens
        input_tokens = count_tokens(system_prompt + prompt_text, model)
        
        try:
            # Make API call
            response = self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt_text}
                ],
                response_format={"type": "json_object"},
                temperature=0.7,
            )
            
            # Extract response
            content = response.choices[0].message.content
            
            # Get token usage from API response
            usage = response.usage
            input_tokens_api = usage.prompt_tokens
            output_tokens_api = usage.completion_tokens
            total_tokens_api = usage.total_tokens
            
            # Use API token counts (more accurate)
            input_tokens = input_tokens_api
            output_tokens = output_tokens_api
            total_tokens = total_tokens_api
            
            # Calculate cost
            cost_usd = calculate_cost(input_tokens, output_tokens, model)
            
            # Parse JSON response
            try:
                parsed_response = json.loads(content)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse LLM JSON response: {e}")
                logger.error(f"Response content: {content}")
                raise ValueError(f"LLM returned invalid JSON: {e}")
            
            return {
                'response': parsed_response,
                'input_tokens': input_tokens,
                'output_tokens': output_tokens,
                'total_tokens': total_tokens,
                'cost_usd': cost_usd,
                'model': model,
            }
            
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            raise

