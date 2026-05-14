from typing import Literal

from pydantic import BaseModel, Field


Platform = Literal["momo", "shopee", "pchome", "yahoo", "sample"]


class ShoppingRequest(BaseModel):
    query: str = Field(..., min_length=2, description="The shopping need or question.")
    budget: str | None = Field(None, description="Optional budget, such as NTD30000.")
    preference: str | None = Field(None, description="Optional brand, usage, or feature preference.")



class ProductSuggestion(BaseModel):
    name: str
    reason: str
    key_features: list[str] = Field(default_factory=list)
    cautions: list[str] = Field(default_factory=list)



class ShoppingAdvice(BaseModel):
    problem: str
    buying_criteria: list[str]
    solutions: list[ProductSuggestion]
    next_questions: list[str] = Field(default_factory=list)



class Product(BaseModel):
    platform: Platform
    title: str
    price: int
    rating: float | None = None
    sales: int | None = None
    shipping_fee: int | None = None
    image: str | None = None
    url: str



class ProductSearchResult(BaseModel):
    keyword: str
    products: list[Product]

