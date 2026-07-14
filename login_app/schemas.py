"""
Pydantic schemas for request/response validation.
"""
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator
from typing import Optional


class AttributionPayload(BaseModel):
    """Optional client-captured marketing attribution + consent, sent at signup.

    All fields are optional/defaulted so a partial or malformed payload from the
    client never blocks registration.
    """

    utm_source: str = Field(default="", description="UTM source parameter")
    utm_medium: str = Field(default="", description="UTM medium parameter")
    utm_campaign: str = Field(default="", description="UTM campaign parameter")
    utm_content: str = Field(default="", description="UTM content parameter")
    utm_term: str = Field(default="", description="UTM term parameter")
    fbclid: str = Field(default="", description="Facebook click id")
    fbp: str = Field(default="", description="Facebook browser id (_fbp cookie)")
    fbc: str = Field(default="", description="Facebook click id cookie (_fbc)")
    consent: bool = Field(default=False, description="Whether marketing consent was granted")
    consent_version: str = Field(default="", description="Version of the consent copy shown")


class RegistrationRequest(BaseModel):
    """Schema for user registration request."""

    username: str = Field(..., min_length=3, max_length=150, description="Username (3-150 characters)")
    email: EmailStr = Field(..., description="Valid email address")
    password: str = Field(..., min_length=8, description="Password (minimum 8 characters)")
    password_confirm: str = Field(..., alias="passwordConfirm", description="Password confirmation")
    attribution: Optional[AttributionPayload] = Field(default=None, description="Optional marketing attribution + consent captured client-side")

    @field_validator('password')
    @classmethod
    def validate_password(cls, v: str) -> str:
        """Validate password meets requirements."""
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        if not any(c.isalpha() for c in v):
            raise ValueError("Password must contain at least one letter")
        return v
    
    @model_validator(mode='after')
    def validate_password_match(self):
        """Validate password confirmation matches password."""
        if self.password != self.password_confirm:
            raise ValueError("Passwords do not match")
        return self
    
    class Config:
        """Pydantic configuration."""
        populate_by_name = True  # Allow both password_confirm and passwordConfirm


class LoginRequest(BaseModel):
    """Schema for user login request."""
    
    username: str = Field(..., description="Username or email")
    password: str = Field(..., description="User password")


class EmailVerificationRequest(BaseModel):
    """Schema for email verification request."""

    uid: str = Field(..., description="Base64 encoded user ID")
    token: str = Field(..., description="Verification token")


class PasswordResetRequestSchema(BaseModel):
    """Schema for requesting a password reset email."""

    email: EmailStr = Field(..., description="Email address associated with the account")


class PasswordResetConfirmSchema(BaseModel):
    """Schema for confirming a password reset with new password."""

    uid: str = Field(..., description="Base64 encoded user ID")
    token: str = Field(..., description="Password reset token")
    password: str = Field(..., min_length=8, description="New password (minimum 8 characters)")
    password_confirm: str = Field(..., alias="passwordConfirm", description="New password confirmation")

    @field_validator('password')
    @classmethod
    def validate_password(cls, v: str) -> str:
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        if not any(c.isalpha() for c in v):
            raise ValueError("Password must contain at least one letter")
        return v

    @model_validator(mode='after')
    def validate_password_match(self):
        if self.password != self.password_confirm:
            raise ValueError("Passwords do not match")
        return self

    class Config:
        populate_by_name = True

