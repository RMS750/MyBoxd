from __future__ import annotations

import re
from pydantic import BaseModel, Field, field_validator

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=5, max_length=320)
    password: str = Field(min_length=10, max_length=128)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("Name is required")
        return value

    @field_validator("email")
    @classmethod
    def clean_email(cls, value: str) -> str:
        value = value.strip().casefold()
        if not EMAIL_RE.match(value):
            raise ValueError("Enter a valid email address")
        return value


class LoginRequest(BaseModel):
    email: str = Field(min_length=5, max_length=320)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def clean_email(cls, value: str) -> str:
        return value.strip().casefold()


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=10, max_length=128)


class ProfileUpdateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        return " ".join(value.split())


class ContextRecommendationRequest(BaseModel):
    prompt: str = Field("", max_length=1000)
    mood: str | None = Field(None, max_length=120)
    max_runtime: int | None = Field(None, ge=30, le=400)
    min_runtime: int | None = Field(None, ge=0, le=400)
    genres: list[str] = Field(default_factory=list, max_length=20)
    avoid: list[str] = Field(default_factory=list, max_length=30)
    darkness: int | None = Field(None, ge=0, le=100)
    pace: int | None = Field(None, ge=0, le=100)
    experimental: int | None = Field(None, ge=0, le=100)
    mainstream: int | None = Field(None, ge=0, le=100)
    company: str | None = Field(None, max_length=40)
    decade: int | None = Field(None, ge=1880, le=2100)
    language: str | None = Field(None, max_length=40)
    country: str | None = Field(None, max_length=80)
    emotional_intensity: int | None = Field(None, ge=0, le=100)
    limit: int = Field(5, ge=1, le=20)


class RouletteRequest(BaseModel):
    max_runtime: int | None = Field(None, ge=30, le=400)
    watchlist_only: bool = False
    category: str | None = Field(None, max_length=30)
    hidden_gem: bool = False


class WeightSettings(BaseModel):
    genre: float = Field(.18, ge=0, le=1)
    semantic: float = Field(.15, ge=0, le=1)
    creator: float = Field(.10, ge=0, le=1)
    decade: float = Field(.04, ge=0, le=1)
    locale: float = Field(.03, ge=0, le=1)
    runtime: float = Field(.03, ge=0, le=1)
    popularity: float = Field(.03, ge=0, le=1)
    community: float = Field(.12, ge=0, le=1)
    predicted_rating: float = Field(.30, ge=0, le=1)
    novelty: float = Field(.02, ge=0, le=1)


class SettingsUpdate(BaseModel):
    weights: WeightSettings
