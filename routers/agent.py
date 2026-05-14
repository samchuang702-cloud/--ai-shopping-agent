from fastapi import APIRouter

from models.recommendation import (
    AgentRunResult,
    DecisionResult,
    PlanProductsRequest,
    PlanProductsResult,
    ProblemAnalysis,
    RecommendationResult,
)
from models.shopping import Platform, ProductSearchResult, ProductSuggestion, ShoppingAdvice, ShoppingRequest
from services.pchome_service import search_products
from services.recommendation_service import (
    analyze_problem,
    decide_search,
    recommend_missing_plan_items,
    recommend_products,
    run_agent,
)


router = APIRouter()


@router.post("/shopping-advice", response_model=ShoppingAdvice)
def shopping_advice(payload: ShoppingRequest) -> ShoppingAdvice:
    analysis = analyze_problem(payload)
    return ShoppingAdvice(
        problem=analysis.problem,
        buying_criteria=[
            "Match the real user problem.",
            "Fit the stated budget and preferences.",
            "Compare price, rating, sales, shipping fee, and platform reliability.",
        ],
        solutions=[
            ProductSuggestion(name=item.method, reason=item.reason, key_features=[item.search_keyword])
            for item in analysis.solutions
        ],
        next_questions=["Do you want me to search products and compare prices now?"],
    )



@router.get("/ask", response_model=ShoppingAdvice)
def ask_gpt(q: str, budget: str | None = None, preference: str | None = None) -> ShoppingAdvice:
    return shopping_advice(ShoppingRequest(query=q, budget=budget, preference=preference))



@router.post("/agent/analyze", response_model=ProblemAnalysis)
def agent_analyze(payload: ShoppingRequest) -> ProblemAnalysis:
    return analyze_problem(payload)



@router.post("/agent/decide", response_model=DecisionResult)
def agent_decide(payload: ShoppingRequest) -> DecisionResult:
    return decide_search(analyze_problem(payload))



@router.get("/agent/search-products", response_model=ProductSearchResult)
def agent_search_products(keyword: str, platform: list[Platform] | None = None) -> ProductSearchResult:
    return search_products(keyword, platform)



@router.post("/agent/recommend", response_model=RecommendationResult)
def agent_recommend(payload: ProductSearchResult) -> RecommendationResult:
    return recommend_products(payload.products, payload.keyword)



@router.post("/agent/run", response_model=AgentRunResult)
def agent_run(payload: ShoppingRequest) -> AgentRunResult:
    return run_agent(payload)



@router.post("/agent/plan-products", response_model=PlanProductsResult)
def agent_plan_products(payload: PlanProductsRequest) -> PlanProductsResult:
    return recommend_missing_plan_items(payload)
