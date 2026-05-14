from typing import Any

from pydantic import BaseModel, Field

from .shopping import Platform, Product, ProductSearchResult


class SolutionOption(BaseModel):
    method: str
    reason: str
    search_keyword: str
    steps: list[str] = Field(default_factory=list)
    required_items: list[str] = Field(default_factory=list)
    cautions: list[str] = Field(default_factory=list)



class ProblemAnalysis(BaseModel):
    original_query: str
    problem: str
    intent: str
    user_context: list[str] = Field(default_factory=list)
    solutions: list[SolutionOption] = Field(default_factory=list)



class DecisionResult(BaseModel):
    selected_solution: SolutionOption
    decision_reason: str
    search_plan: list[str]
    platforms: list[Platform] = Field(default_factory=lambda: ["pchome"])



class PlanProductsRequest(BaseModel):
    query: str = Field(..., min_length=2)
    plan_index: int = Field(..., ge=1)
    missing_items: list[str] = Field(default_factory=list)
    budget: str | None = None
    preference: str | None = None



class ItemProductGroup(BaseModel):
    item_name: str
    keyword: str
    products: list[Product]



class PlanProductsResult(BaseModel):
    analysis: ProblemAnalysis
    selected_plan: SolutionOption
    missing_items: list[str]
    product_groups: list[ItemProductGroup]



class RecommendationItem(BaseModel):
    product: Product
    score: float
    reason: str



class RecommendationResult(BaseModel):
    best_product: RecommendationItem
    ranked_products: list[RecommendationItem]
    comparison_summary: list[str]
    caveats: list[str] = Field(default_factory=list)



class AgentRunResult(BaseModel):
    analysis: ProblemAnalysis
    decision: DecisionResult
    product_search: ProductSearchResult
    recommendation: RecommendationResult
    line_flex_message: dict[str, Any]
