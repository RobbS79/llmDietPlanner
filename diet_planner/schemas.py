"""
Pydantic schemas for request/response validation.
Used between LLM and Django for data validation.
"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class CountryEnum(str, Enum):
    """
    Supported countries.
    
    Note: For MVP, only CZ (Czech Republic) and SK (Slovakia) are available
    in the frontend. The backend enum remains flexible for future expansion.
    """
    DE = "DE"  # Germany
    PL = "PL"  # Poland
    CZ = "CZ"  # Czech Republic (MVP)
    SK = "SK"  # Slovakia (MVP)
    HU = "HU"  # Hungary
    RO = "RO"  # Romania
    BG = "BG"  # Bulgaria
    AT = "AT"  # Austria


class DietaryGoalCreateRequest(BaseModel):
    """Request schema for creating a dietary goal."""
    prompt: str = Field(
        ...,
        min_length=10,
        max_length=5000,
        description="User's dietary prompt with goals and requirements"
    )
    dietary_restrictions: Optional[str] = Field(
        None,
        max_length=2000,
        description="Optional dietary restrictions or allergies"
    )
    country: CountryEnum = Field(
        ...,
        description="Country code where user wants to buy ingredients"
    )
    city: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="City where user wants to buy ingredients"
    )
    language_code: str = Field(
        default="pl",
        min_length=2,
        max_length=5,
        description="Language code (ISO 639-1) for i18n support"
    )
    num_recipes: int = Field(
        default=7,
        ge=1,
        le=30,
        description="Number of recipes to generate for the 7-day meal plan"
    )
    num_meals: int = Field(
        default=14,
        ge=1,
        le=50,
        description="Number of small meals to generate for the 7-day meal plan"
    )
    num_snacks: int = Field(
        default=7,
        ge=0,
        le=30,
        description="Number of snacks to generate for the 7-day meal plan"
    )

    @field_validator('prompt')
    @classmethod
    def validate_prompt(cls, v: str) -> str:
        """Ensure prompt is not empty or just whitespace."""
        if not v.strip():
            raise ValueError("Prompt cannot be empty or whitespace only")
        return v.strip()


class MealIdea(BaseModel):
    """Schema for a single meal idea."""
    name: str = Field(..., description="Meal name")
    description: Optional[str] = Field(None, description="Meal description")
    ingredients: List[str] = Field(..., description="List of ingredients")
    preparation_time: Optional[int] = Field(None, description="Preparation time in minutes")
    nutritional_info: Optional[Dict[str, Any]] = Field(None, description="Nutritional information")


class ShoppingListItem(BaseModel):
    """Schema for a shopping list item."""
    ingredient: str = Field(..., description="Ingredient name")
    quantity: Optional[str] = Field(None, description="Required quantity")
    unit: Optional[str] = Field(None, description="Unit of measurement")
    notes: Optional[str] = Field(None, description="Additional notes")


class DietaryPlanResponse(BaseModel):
    """Response schema for a dietary plan."""
    meal_ideas: List[MealIdea] = Field(..., description="Generated meal ideas")
    shopping_list: List[ShoppingListItem] = Field(..., description="Shopping list")


class DietaryGoalResponse(BaseModel):
    """Response schema for a dietary goal."""
    id: int
    status: str
    country: str
    city: str
    currency: str
    language_code: str
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None
    dietary_plan: Optional[DietaryPlanResponse] = None

    class Config:
        from_attributes = True


class DietaryGoalCreateResponse(BaseModel):
    """Response schema when creating a dietary goal."""
    status: str = "success"
    data: Dict[str, Any] = Field(
        ...,
        description="Response data containing goal ID and status"
    )
    error: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "status": "success",
                "data": {
                    "goal_id": 1,
                    "status": "pending",
                    "message": "Dietary goal created. Processing will begin shortly."
                },
                "error": None
            }
        }
