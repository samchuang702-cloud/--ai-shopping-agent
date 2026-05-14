import base64
import hashlib
import hmac
import json
import os
from typing import Any, Literal

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from openai import OpenAI, OpenAIError
from pydantic import BaseModel, Field, ValidationError


load_dotenv()

app = FastAPI(
    title="AI 智慧購物代理",
    description="串接 LINE、AI 決策、商品搜尋、比價與推薦輸出的智慧購物代理系統。",
    version="0.2.0",
)
templates = Jinja2Templates(directory="templates")
Platform = Literal["momo", "shopee", "pchome", "yahoo", "sample"]
PCHOME_SEARCH_URL = "https://ecshweb.pchome.com.tw/search/v3.3/all/results"
PCHOME_PRODUCT_URL = "https://24h.pchome.com.tw/prod/{product_id}"
PCHOME_IMAGE_HOST = "https://cs-a.ecimg.tw"
LINE_REPLY_URL = "https://api.line.me/v2/bot/message/reply"


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


class LineWebhookEvent(BaseModel):
    type: str
    replyToken: str | None = None
    message: dict[str, Any] | None = None


class LineWebhookPayload(BaseModel):
    events: list[LineWebhookEvent] = Field(default_factory=list)


SAMPLE_PRODUCTS: list[Product] = [
    Product(
        platform="momo",
        title="Panasonic 12L 小型除濕機",
        price=3990,
        rating=4.8,
        sales=1260,
        shipping_fee=0,
        image="https://example.com/panasonic-dehumidifier.jpg",
        url="https://example.com/momo/panasonic-dehumidifier",
    ),
    Product(
        platform="shopee",
        title="Toshiba 10L 小坪數除濕機",
        price=3590,
        rating=4.7,
        sales=980,
        shipping_fee=60,
        image="https://example.com/toshiba-dehumidifier.jpg",
        url="https://example.com/shopee/toshiba-dehumidifier",
    ),
    Product(
        platform="pchome",
        title="Whirlpool 12L 靜音除濕機",
        price=4180,
        rating=4.6,
        sales=620,
        shipping_fee=0,
        image="https://example.com/whirlpool-dehumidifier.jpg",
        url="https://example.com/pchome/whirlpool-dehumidifier",
    ),
    Product(
        platform="momo",
        title="浴室金屬除鏽凝膠",
        price=299,
        rating=4.5,
        sales=2100,
        shipping_fee=0,
        image="https://example.com/rust-remover.jpg",
        url="https://example.com/momo/rust-remover",
    ),
    Product(
        platform="shopee",
        title="強效鐵鏽清潔噴劑",
        price=199,
        rating=4.4,
        sales=3500,
        shipping_fee=45,
        image="https://example.com/rust-spray.jpg",
        url="https://example.com/shopee/rust-spray",
    ),
    Product(
        platform="pchome",
        title="14 吋學生程式設計輕薄筆電",
        price=29900,
        rating=4.6,
        sales=180,
        shipping_fee=0,
        image="https://example.com/student-laptop.jpg",
        url="https://example.com/pchome/student-laptop",
    ),
]



def get_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="OPENAI_API_KEY is not set. Create a .env file and add your API key.",
        )
    return OpenAI(api_key=api_key)


def verify_line_signature(body: bytes, signature: str | None) -> None:
    if os.getenv("LINE_VERIFY_SIGNATURE", "false").lower() != "true":
        return

    channel_secret = os.getenv("LINE_CHANNEL_SECRET")
    if not channel_secret or not signature:
        return

    digest = hmac.new(channel_secret.encode("utf-8"), body, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode("utf-8")
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=401, detail="LINE 簽章驗證失敗。")


def reply_to_line(reply_token: str | None, messages: list[dict[str, Any]]) -> dict[str, Any]:
    access_token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
    if not access_token:
        return {"sent": False, "reason": "LINE_CHANNEL_ACCESS_TOKEN 未設定。"}
    if not reply_token:
        return {"sent": False, "reason": "沒有 replyToken。"}
    if reply_token.startswith("dummy"):
        return {"sent": False, "reason": "本機 dummy replyToken，略過 LINE Reply API。"}

    response = httpx.post(
        LINE_REPLY_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        json={"replyToken": reply_token, "messages": messages},
        timeout=10,
    )
    if response.status_code >= 400:
        return {
            "sent": False,
            "status_code": response.status_code,
            "reason": response.text[:500],
        }
    return {"sent": True, "status_code": response.status_code}


def parse_json_object(content: str) -> dict[str, Any]:
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=502,
            detail={"message": "The AI response was not valid JSON.", "raw_response": content},
        ) from exc

    if not isinstance(parsed, dict):
        raise HTTPException(status_code=502, detail="The AI response JSON must be an object.")
    return parsed


def llm_json(system_prompt: str, user_prompt: str) -> dict[str, Any]:
    client = get_client()
    try:
        response = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
            temperature=0.2,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
    except OpenAIError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"OpenAI request failed: {exc.__class__.__name__}",
        ) from exc

    return parse_json_object(response.choices[0].message.content or "{}")


def fallback_analysis(payload: ShoppingRequest) -> ProblemAnalysis:
    q = payload.query.lower()
    if "發霉" in payload.query or "黴" in payload.query or "mold" in q or "mould" in q:
        solutions = [
            SolutionOption(
                method="白醋＋小蘇打清潔",
                reason="適合磁磚、浴室或可碰水地板的輕中度霉斑，味道較低且材料容易取得。",
                search_keyword="白醋 小蘇打 清潔刷",
                steps=[
                    "先把地板表面灰塵與毛髮清掉。",
                    "將白醋噴在發霉處，靜置約 10 分鐘。",
                    "撒上小蘇打後用刷子刷洗，再用清水擦乾。",
                ],
                required_items=["白醋", "小蘇打", "清潔刷", "手套", "抹布"],
                cautions=["不建議用在怕酸或未密封的天然石材。"],
            ),
            SolutionOption(
                method="稀釋漂白水消毒",
                reason="殺菌力較強，適合霉斑較明顯、需要消毒的地板區域。",
                search_keyword="漂白水 手套 清潔刷",
                steps=[
                    "將漂白水與水約 1:99 稀釋。",
                    "噴灑或拖在發霉區域，靜置 5 到 10 分鐘。",
                    "刷洗後用清水擦過並保持通風乾燥。",
                ],
                required_items=["漂白水", "水", "手套", "口罩", "清潔刷", "抹布"],
                cautions=["不可與白醋、酸性清潔劑或其他清潔劑混用；使用時保持通風。"],
            ),
            SolutionOption(
                method="除霉清潔劑處理",
                reason="操作最簡單，適合想快速處理霉斑並購買現成清潔用品的人。",
                search_keyword="除霉清潔劑 手套",
                steps=[
                    "依產品說明噴在發霉處。",
                    "等待指定時間後刷洗或擦拭。",
                    "最後擦乾並讓地板保持通風。",
                ],
                required_items=["除霉清潔劑", "手套", "口罩", "清潔刷", "抹布"],
                cautions=["使用前先在不明顯角落測試，避免地板材質變色。"],
            ),
        ]
        problem = "地板發霉"
    elif "rust" in q or "鐵鏽" in payload.query:
        solutions = [
            SolutionOption(
                method="除鏽清潔劑",
                reason="可直接處理表面鐵鏽與鏽斑。",
                search_keyword="除鏽 清潔劑",
                required_items=["除鏽清潔劑", "手套", "清潔刷", "抹布"],
            ),
            SolutionOption(
                method="砂紙與防鏽漆",
                reason="適合金屬表面修復與後續防鏽。",
                search_keyword="防鏽漆",
                required_items=["砂紙", "防鏽漆", "手套", "刷子"],
            ),
        ]
        problem = "鐵鏽清潔"
    elif "除濕" in payload.query or "潮濕" in payload.query or "dehumid" in q:
        solutions = [
            SolutionOption(
                method="小型除濕機",
                reason="適合租屋處穩定降低室內濕度。",
                search_keyword="小型除濕機",
                required_items=["小型除濕機"],
            ),
            SolutionOption(
                method="防潮盒",
                reason="成本低，適合衣櫃或小角落。",
                search_keyword="防潮盒",
                required_items=["防潮盒", "除濕包"],
            ),
        ]
        problem = "室內潮濕"
    elif "香" in payload.query or "臭" in payload.query or "味道" in payload.query or "odor" in q:
        solutions = [
            SolutionOption(
                method="低刺激自然擴香",
                reason="味道較柔和，適合想讓房間有淡香但不刺鼻的人。",
                search_keyword="擴香瓶 精油",
                steps=["先保持房間通風。", "使用低濃度擴香或竹枝擴香。", "從少量開始，依接受度增加。"],
                required_items=["擴香瓶", "精油", "擴香竹"],
                cautions=["家中有寵物、嬰幼兒或過敏體質時，精油種類要特別確認。"],
            ),
            SolutionOption(
                method="先除臭再淡香",
                reason="如果房間本身有悶味，先除臭會比直接用香味蓋過更有效。",
                search_keyword="除臭劑 活性碳",
                steps=["找出異味來源。", "放置活性碳或除臭用品。", "異味降低後再使用淡香產品。"],
                required_items=["活性碳", "除臭劑", "擴香瓶"],
                cautions=["不要用過重香味掩蓋霉味或潮濕味，應先處理源頭。"],
            ),
            SolutionOption(
                method="織品與床鋪香氛",
                reason="適合主要想改善床單、窗簾、衣櫃附近味道的情境。",
                search_keyword="衣物芳香噴霧 香氛袋",
                steps=["清洗或曝曬織品。", "使用衣物芳香噴霧或香氛袋。", "定期更換香氛袋。"],
                required_items=["衣物芳香噴霧", "香氛袋", "除濕包"],
                cautions=["先小範圍測試，避免織品染色或味道過重。"],
            ),
        ]
        problem = "房間氣味改善"
    elif "收納" in payload.query or "整理" in payload.query or "雜亂" in payload.query:
        solutions = [
            SolutionOption(
                method="分類收納盒整理",
                reason="適合物品種類多、桌面或櫃子容易亂的情況。",
                search_keyword="收納盒 分隔盒",
                steps=["先把物品依用途分類。", "淘汰不需要的東西。", "用收納盒或分隔盒固定位置。"],
                required_items=["收納盒", "分隔盒", "標籤貼"],
                cautions=["先量尺寸再買，避免收納盒放不進櫃子或桌面。"],
            ),
            SolutionOption(
                method="垂直空間收納",
                reason="適合租屋處或小房間，能增加牆面與桌上的可用空間。",
                search_keyword="層架 掛勾 收納架",
                steps=["找出可用牆面或桌面角落。", "選擇層架、掛勾或桌上架。", "把常用物品放在容易拿的位置。"],
                required_items=["層架", "掛勾", "桌上收納架"],
                cautions=["租屋處使用黏貼式配件時，要注意牆面材質與拆除痕跡。"],
            ),
            SolutionOption(
                method="文件與線材整理",
                reason="適合書桌、工作區或電腦周邊雜亂的情況。",
                search_keyword="文件架 集線器 束線帶",
                steps=["把紙本文件集中分類。", "用文件架管理資料。", "用束線帶或集線盒整理線材。"],
                required_items=["文件架", "束線帶", "集線盒"],
                cautions=["電源線不要過度彎折或塞太滿，避免散熱與安全問題。"],
            ),
        ]
        problem = "空間整理收納"
    else:
        solutions = [
            SolutionOption(
                method="低成本 DIY 方案",
                reason="先用容易取得、成本較低的方式處理問題，適合想先嘗試基本解法的情境。",
                search_keyword=payload.query,
                steps=["確認問題範圍。", "準備基本工具與材料。", "先在小範圍測試，再擴大處理。"],
                required_items=["基本工具", "清潔用品", "手套"],
                cautions=["若問題涉及安全、電器、化學品或結構損壞，請先確認風險。"],
            ),
            SolutionOption(
                method="購買專用產品方案",
                reason="使用市售專用產品通常更省時間，適合希望快速處理的人。",
                search_keyword=payload.query,
                steps=["選擇符合問題的專用商品。", "依照產品說明使用。", "觀察效果並視情況補強。"],
                required_items=["專用產品", "手套", "輔助工具"],
                cautions=["購買前請確認產品適用材質、尺寸、場景與安全限制。"],
            ),
            SolutionOption(
                method="進階或專業處理方案",
                reason="如果問題較嚴重或 DIY 效果有限，使用更完整的設備或找專業人員會更穩定。",
                search_keyword=payload.query,
                steps=["評估問題嚴重程度。", "準備進階工具或尋找專業服務。", "處理後檢查是否復發。"],
                required_items=["進階工具", "防護用品"],
                cautions=["若涉及施工、用電、漏水或健康風險，建議找專業協助。"],
            ),
        ]
        problem = payload.query

    return ProblemAnalysis(
        original_query=payload.query,
        problem=problem,
        intent="尋找合適商品解決方案",
        user_context=[value for value in [payload.budget, payload.preference] if value],
        solutions=solutions,
    )


def normalize_analysis_payload(data: dict[str, Any], payload: ShoppingRequest) -> dict[str, Any]:
    data.setdefault("original_query", payload.query)
    data.setdefault("problem", payload.query)
    data.setdefault("intent", "尋找可執行的解決方案")
    data.setdefault("user_context", [value for value in [payload.budget, payload.preference] if value])

    raw_solutions = (
        data.get("solutions")
        or data.get("solution_plans")
        or data.get("plans")
        or data.get("options")
        or []
    )
    normalized_solutions = []
    for index, item in enumerate(raw_solutions, start=1):
        if not isinstance(item, dict):
            continue
        method = str(item.get("method") or item.get("name") or f"方案 {index}").strip()
        reason = str(item.get("reason") or item.get("description") or "此方案可作為其中一種可行做法。").strip()
        required_items = item.get("required_items") or item.get("items") or []
        if isinstance(required_items, list):
            required_items = [
                str(part.get("name") if isinstance(part, dict) else part).strip()
                for part in required_items
                if str(part.get("name") if isinstance(part, dict) else part).strip()
            ]
        elif isinstance(required_items, str):
            required_items = [part.strip() for part in required_items.replace("、", ",").split(",") if part.strip()]
        steps = item.get("steps") or []
        if isinstance(steps, str):
            steps = [part.strip() for part in steps.split("\n") if part.strip()]
        cautions = item.get("cautions") or []
        if isinstance(cautions, str):
            cautions = [part.strip() for part in cautions.split("\n") if part.strip()]
        search_keyword = str(
            item.get("search_keyword")
            or " ".join(required_items[:2])
            or method
            or payload.query
        ).strip()
        normalized_solutions.append(
            {
                "method": method,
                "reason": reason,
                "search_keyword": search_keyword,
                "steps": steps,
                "required_items": required_items,
                "cautions": cautions,
            }
        )

    if len(normalized_solutions) < 2:
        return fallback_analysis(payload).model_dump()

    data["solutions"] = normalized_solutions[:4]
    return data


def analyze_problem(payload: ShoppingRequest) -> ProblemAnalysis:
    system_prompt = (
        "You are the Problem Analyzer and Solution Generator of a shopping agent. "
        "Answer in Traditional Chinese. Return JSON with original_query, problem, "
        "intent, user_context, and solutions. Provide 2 to 4 different solution plans. "
        "Each solution needs method, reason, search_keyword, steps, required_items, and cautions. "
        "Do not jump directly to one product; first provide practical plans the user can choose from. "
        "Make the plans work for any user problem, not only shopping requests. "
        "For required_items, list concrete purchasable items or tools needed by each plan."
    )
    try:
        data = llm_json(system_prompt, payload.model_dump_json())
        data = normalize_analysis_payload(data, payload)
        return ProblemAnalysis.model_validate(data)
    except (HTTPException, ValidationError):
        return fallback_analysis(payload)


def decide_search(analysis: ProblemAnalysis) -> DecisionResult:
    selected = analysis.solutions[0] if analysis.solutions else SolutionOption(
        method="商品搜尋",
        reason="目前沒有更明確的解決方案。",
        search_keyword=analysis.problem,
    )
    return DecisionResult(
        selected_solution=selected,
        decision_reason=f"選擇「{selected.method}」，因為它最符合使用者目前的問題。",
        search_plan=[
            f"在 PChome 搜尋 {selected.search_keyword}",
            "整理商品名稱、價格、評分、銷量、運費、圖片與網址。",
            "移除無效資料，依價格、評分與銷量排序。",
            "momo 與 Shopee 搜尋器尚未串接，下一階段再加入。",
        ],
    )


def normalized_text(value: str) -> str:
    return value.lower().replace("-", " ")


def pchome_image_url(path: str | None) -> str | None:
    if not path:
        return None
    if path.startswith("http://") or path.startswith("https://"):
        return path
    if path.startswith("/"):
        return f"{PCHOME_IMAGE_HOST}{path}"
    return f"{PCHOME_IMAGE_HOST}/{path}"


def collect_pchome_products(keyword: str, limit: int = 10) -> list[Product]:
    try:
        response = httpx.get(
            PCHOME_SEARCH_URL,
            params={"q": keyword, "page": 1, "sort": "sale/dc"},
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0 AI-Shopping-Agent/0.2"},
        )
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=f"PChome 搜尋失敗：{exc.__class__.__name__}") from exc

    products: list[Product] = []
    for item in data.get("prods", [])[:limit]:
        product_id = str(item.get("Id") or "").strip()
        name = str(item.get("name") or "").strip()
        price = item.get("price")
        if not product_id or not name or price is None:
            continue
        try:
            price_int = int(price)
        except (TypeError, ValueError):
            continue

        products.append(
            Product(
                platform="pchome",
                title=name,
                price=price_int,
                rating=None,
                sales=None,
                shipping_fee=0,
                image=pchome_image_url(item.get("picB") or item.get("picS")),
                url=PCHOME_PRODUCT_URL.format(product_id=product_id),
            )
        )

    return products


def search_products(keyword: str, platforms: list[Platform] | None = None) -> ProductSearchResult:
    enabled = set(platforms or ["momo", "shopee", "pchome"])
    if "pchome" in enabled:
        products = collect_pchome_products(keyword)
        if products:
            return ProductSearchResult(keyword=keyword, products=products)

    keyword_text = normalized_text(keyword)
    tokens = [token for token in keyword_text.split() if len(token) > 1]
    matched: list[Product] = []

    for product in SAMPLE_PRODUCTS:
        if product.platform not in enabled:
            continue
        title = normalized_text(product.title)
        if any(token in title for token in tokens) or not tokens:
            matched.append(product)

    if not matched:
        matched = [product for product in SAMPLE_PRODUCTS if product.platform in enabled][:3]

    return ProductSearchResult(keyword=keyword, products=matched)


def product_score(product: Product) -> float:
    rating_score = (product.rating or 0) * 20
    sales_score = min((product.sales or 0) / 50, 30)
    price_score = max(0, 50 - (product.price / 1000))
    shipping_score = 5 if (product.shipping_fee or 0) == 0 else 0
    return round(rating_score + sales_score + price_score + shipping_score, 2)


def recommend_products(products: list[Product], problem: str) -> RecommendationResult:
    if not products:
        raise HTTPException(status_code=404, detail="找不到商品資料。")

    ranked = sorted(
        [
            RecommendationItem(
                product=product,
                score=product_score(product),
                reason=(
                    f"符合「{problem}」需求；價格 NTD{product.price}，"
                    f"評分 {product.rating or '無資料'}，銷量 {product.sales or '無資料'}。"
                ),
            )
            for product in products
        ],
        key=lambda item: item.score,
        reverse=True,
    )
    cheapest = min(products, key=lambda item: item.price + (item.shipping_fee or 0))
    best_rated = max(products, key=lambda item: item.rating or 0)
    rating_summary = (
        f"最高評分：{best_rated.title}，評分 {best_rated.rating}。"
        if best_rated.rating is not None
        else "PChome 搜尋結果未提供商品評分資料。"
    )

    return RecommendationResult(
        best_product=ranked[0],
        ranked_products=ranked,
        comparison_summary=[
            f"最低總價：{cheapest.title}，平台 {cheapest.platform}。",
            rating_summary,
            f"已比較 {len(products)} 個 PChome 商品。",
        ],
        caveats=[
            "目前已串接 PChome 真實搜尋資料。",
            "momo 與 Shopee 尚未串接，下一階段可加入更多平台比價。",
        ],
    )


def build_line_flex_message(result: RecommendationResult) -> dict[str, Any]:
    bubbles = []
    for item in result.ranked_products[:3]:
        product = item.product
        bubbles.append(
            {
                "type": "bubble",
                "hero": {
                    "type": "image",
                    "url": product.image or "https://example.com/product.jpg",
                    "size": "full",
                    "aspectRatio": "20:13",
                    "aspectMode": "cover",
                },
                "body": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {"type": "text", "text": product.title, "weight": "bold", "wrap": True},
                        {"type": "text", "text": f"NTD {product.price}", "size": "lg", "weight": "bold"},
                        {"type": "text", "text": f"{product.platform} | score {item.score}", "size": "sm"},
                        {"type": "text", "text": item.reason, "size": "sm", "wrap": True},
                    ],
                },
                "footer": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {
                            "type": "button",
                            "style": "primary",
                            "action": {"type": "uri", "label": "查看商品", "uri": product.url},
                        }
                    ],
                },
            }
        )

    return {
        "type": "flex",
        "altText": "AI 購物推薦",
        "contents": {"type": "carousel", "contents": bubbles},
    }


def run_agent(payload: ShoppingRequest) -> AgentRunResult:
    analysis = analyze_problem(payload)
    decision = decide_search(analysis)
    product_search = search_products(decision.selected_solution.search_keyword, decision.platforms)
    recommendation = recommend_products(product_search.products, analysis.problem)
    return AgentRunResult(
        analysis=analysis,
        decision=decision,
        product_search=product_search,
        recommendation=recommendation,
        line_flex_message=build_line_flex_message(recommendation),
    )


def item_search_keyword(item_name: str) -> str:
    keyword_map = {
        "手套": "清潔手套 橡膠手套",
        "口罩": "清潔口罩 防護口罩",
        "清潔刷": "清潔刷 地板刷",
        "抹布": "清潔抹布",
        "漂白水": "漂白水",
        "白醋": "白醋",
        "小蘇打": "小蘇打",
    }
    return keyword_map.get(item_name, item_name)


def recommend_missing_plan_items(payload: PlanProductsRequest) -> PlanProductsResult:
    analysis = analyze_problem(
        ShoppingRequest(query=payload.query, budget=payload.budget, preference=payload.preference)
    )
    if payload.plan_index > len(analysis.solutions):
        raise HTTPException(status_code=400, detail="選擇的計畫不存在。")

    selected_plan = analysis.solutions[payload.plan_index - 1]
    missing_items = [item.strip() for item in payload.missing_items if item.strip()]
    if not missing_items:
        missing_items = selected_plan.required_items
    if not missing_items:
        missing_items = [selected_plan.search_keyword]

    product_groups = []
    for item in missing_items:
        keyword = item_search_keyword(item)
        result = search_products(keyword, ["pchome"])
        product_groups.append(
            ItemProductGroup(
                item_name=item,
                keyword=keyword,
                products=result.products[:3],
            )
        )

    return PlanProductsResult(
        analysis=analysis,
        selected_plan=selected_plan,
        missing_items=missing_items,
        product_groups=product_groups,
    )


INDEX_HTML = """
<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AI 智慧購物代理</title>
  <style>
    body { margin: 0; font-family: "Microsoft JhengHei", "Noto Sans TC", Arial, sans-serif; background: #f6f7f9; color: #1f2937; }
    header { background: #fff; border-bottom: 1px solid #d8dde6; }
    .wrap { width: min(1120px, calc(100% - 32px)); margin: 0 auto; }
    .topbar { padding: 18px 0; display: flex; justify-content: space-between; gap: 16px; align-items: center; }
    h1 { margin: 0; font-size: 24px; }
    h2 { margin: 0 0 14px; font-size: 18px; }
    h3 { margin: 0 0 8px; font-size: 16px; }
    main { padding: 24px 0 40px; }
    .layout { display: grid; grid-template-columns: 360px 1fr; gap: 20px; align-items: start; }
    section, .card { background: #fff; border: 1px solid #d8dde6; border-radius: 8px; padding: 18px; }
    label { display: block; font-weight: 700; margin: 14px 0 6px; }
    textarea, input { width: 100%; border: 1px solid #d8dde6; border-radius: 6px; padding: 10px; font: inherit; box-sizing: border-box; }
    textarea { min-height: 120px; resize: vertical; }
    button { border: 0; border-radius: 6px; padding: 10px 14px; font: inherit; font-weight: 700; background: #0f766e; color: #fff; cursor: pointer; }
    button.secondary { background: #475569; }
    button.full { width: 100%; margin-top: 16px; }
    button:disabled { opacity: .65; cursor: wait; }
    .muted { color: #64748b; font-size: 14px; }
    .status { min-height: 22px; margin-top: 12px; color: #64748b; }
    .error { color: #b91c1c; }
    .grid { display: grid; gap: 14px; }
    .plans, .products { display: grid; gap: 12px; }
    .plan { border: 1px solid #d8dde6; border-radius: 8px; padding: 14px; background: #fff; }
    .items { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
    .item { border: 1px solid #d8dde6; border-radius: 999px; padding: 6px 10px; background: #f8fafc; }
    .product-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }
    .product { border: 1px solid #d8dde6; border-radius: 8px; padding: 12px; background: #fff; }
    .product img { width: 100%; aspect-ratio: 4 / 3; object-fit: contain; background: #f8fafc; border-radius: 6px; border: 1px solid #d8dde6; }
    .price { font-size: 22px; font-weight: 800; color: #115e59; margin: 6px 0; }
    a { color: #0f766e; }
    @media (max-width: 860px) { .layout { grid-template-columns: 1fr; } .topbar { align-items: flex-start; flex-direction: column; } }
  </style>
</head>
<body>
  <header>
    <div class="wrap topbar">
      <div>
        <h1>AI 智慧購物代理</h1>
        <div class="muted">先提供多個解決計畫，選定方法後只推薦你缺少的物品。</div>
      </div>
      <a href="/docs">API 文件</a>
    </div>
  </header>

  <main class="wrap">
    <div class="layout">
      <section>
        <h2>輸入問題</h2>
        <form id="query-form">
          <label for="query">你想解決什麼問題？</label>
          <textarea id="query" name="query" required>找除地板發霉的方法</textarea>
          <label for="budget">預算</label>
          <input id="budget" name="budget" placeholder="例如 NTD1000">
          <label for="preference">偏好條件</label>
          <input id="preference" name="preference" placeholder="例如 不想用味道太重的清潔劑">
          <button id="analyze-button" class="full" type="submit">產生解決計畫</button>
          <div id="status" class="status">服務已就緒。</div>
        </form>
      </section>

      <div class="grid">
        <section>
          <h2>可選擇的解決計畫</h2>
          <div id="plans" class="plans muted">送出問題後，這裡會顯示多個方法。</div>
        </section>

        <section>
          <h2>我缺少的物品</h2>
          <div id="selected-plan" class="muted">請先選擇一個計畫。</div>
          <div id="missing-items" class="items"></div>
          <label for="custom-missing">其他缺少物品</label>
          <input id="custom-missing" placeholder="例如 漂白水、手套、刷子">
          <button id="recommend-button" class="full secondary" type="button" disabled>推薦缺少物品</button>
        </section>

        <section>
          <h2>商品推薦</h2>
          <div id="products" class="products muted">選擇缺少物品後，這裡會顯示 PChome 商品。</div>
        </section>
      </div>
    </div>
  </main>

  <script>
    const form = document.querySelector("#query-form");
    const statusEl = document.querySelector("#status");
    const plansEl = document.querySelector("#plans");
    const selectedPlanEl = document.querySelector("#selected-plan");
    const missingItemsEl = document.querySelector("#missing-items");
    const customMissingEl = document.querySelector("#custom-missing");
    const productsEl = document.querySelector("#products");
    const analyzeButton = document.querySelector("#analyze-button");
    const recommendButton = document.querySelector("#recommend-button");
    let currentAnalysis = null;
    let selectedPlanIndex = null;

    function escapeHtml(value) {
      return String(value ?? "")
        .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;").replaceAll("'", "&#039;");
    }

    function setStatus(text, isError = false) {
      statusEl.textContent = text;
      statusEl.className = isError ? "status error" : "status";
    }

    function renderPlan(plan, index) {
      const steps = (plan.steps || []).map(step => `<li>${escapeHtml(step)}</li>`).join("");
      const cautions = (plan.cautions || []).map(item => `<li>${escapeHtml(item)}</li>`).join("");
      return `
        <article class="plan">
          <h3>方案 ${index + 1}：${escapeHtml(plan.method)}</h3>
          <p>${escapeHtml(plan.reason)}</p>
          ${steps ? `<strong>做法</strong><ol>${steps}</ol>` : ""}
          ${cautions ? `<strong>注意事項</strong><ul>${cautions}</ul>` : ""}
          <button type="button" data-plan-index="${index + 1}">選擇這個計畫</button>
        </article>
      `;
    }

    function renderMissingItems(plan) {
      selectedPlanEl.innerHTML = `<strong>已選擇：</strong>${escapeHtml(plan.method)}<p>${escapeHtml(plan.reason)}</p>`;
      const items = plan.required_items || [];
      missingItemsEl.innerHTML = items.map(item => `
        <label class="item">
          <input type="checkbox" value="${escapeHtml(item)}">
          我沒有 ${escapeHtml(item)}
        </label>
      `).join("");
      recommendButton.disabled = false;
    }

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      analyzeButton.disabled = true;
      recommendButton.disabled = true;
      productsEl.textContent = "尚未選擇缺少物品。";
      setStatus("正在產生解決計畫...");
      const body = {
        query: form.query.value.trim(),
        budget: form.budget.value.trim() || null,
        preference: form.preference.value.trim() || null
      };
      try {
        const response = await fetch("/agent/analyze", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify(body)
        });
        if (!response.ok) throw new Error(await response.text());
        currentAnalysis = await response.json();
        selectedPlanIndex = null;
        plansEl.className = "plans";
        plansEl.innerHTML = currentAnalysis.solutions.map(renderPlan).join("");
      selectedPlanEl.textContent = "請選擇一個計畫。";
      missingItemsEl.innerHTML = "";
      customMissingEl.value = "";
      setStatus("請選擇你想採用的計畫。");
      } catch (error) {
        setStatus("發生錯誤：" + error.message, true);
      } finally {
        analyzeButton.disabled = false;
      }
    });

    plansEl.addEventListener("click", (event) => {
      const button = event.target.closest("button[data-plan-index]");
      if (!button || !currentAnalysis) return;
      selectedPlanIndex = Number(button.dataset.planIndex);
      renderMissingItems(currentAnalysis.solutions[selectedPlanIndex - 1]);
      setStatus("勾選你缺少的物品後，再按推薦。");
    });

    recommendButton.addEventListener("click", async () => {
      if (!selectedPlanIndex) return;
      const checked = [...missingItemsEl.querySelectorAll("input:checked")].map(input => input.value);
      const customItems = customMissingEl.value
        .split(/[、,，\\n]/)
        .map(item => item.trim())
        .filter(Boolean);
      const missingItems = [...new Set([...checked, ...customItems])];
      recommendButton.disabled = true;
      productsEl.textContent = "正在搜尋你缺少的物品...";
      setStatus("正在搜尋 PChome 商品...");
      try {
        const response = await fetch("/agent/plan-products", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({
            query: form.query.value.trim(),
            budget: form.budget.value.trim() || null,
            preference: form.preference.value.trim() || null,
            plan_index: selectedPlanIndex,
            missing_items: missingItems
          })
        });
        if (!response.ok) throw new Error(await response.text());
        const data = await response.json();
        productsEl.className = "products";
        productsEl.innerHTML = data.product_groups.map(group => `
          <div class="card">
            <h3>缺少物品：${escapeHtml(group.item_name)}</h3>
            <div class="product-grid">
              ${group.products.map(product => `
                <article class="product">
                  ${product.image ? `<img src="${escapeHtml(product.image)}" alt="${escapeHtml(product.title)}">` : ""}
                  <h3>${escapeHtml(product.title)}</h3>
                  <div class="price">NTD ${escapeHtml(product.price)}</div>
                  <div class="muted">${escapeHtml(product.platform)}</div>
                  <a href="${escapeHtml(product.url)}" target="_blank" rel="noreferrer">查看商品</a>
                </article>
              `).join("")}
            </div>
          </div>
        `).join("");
        setStatus("完成。");
      } catch (error) {
        productsEl.textContent = "搜尋失敗。";
        setStatus("發生錯誤：" + error.message, true);
      } finally {
        recommendButton.disabled = false;
      }
    });
  </script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
   return HTMLResponse(open("templates/index.html", encoding="utf-8").read())


@app.get("/health")
def health() -> dict[str, bool | str]:
    return {
        "status": "ok",
        "openai_key_configured": bool(os.getenv("OPENAI_API_KEY")),
    }


@app.post("/shopping-advice", response_model=ShoppingAdvice)
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


@app.get("/ask", response_model=ShoppingAdvice)
def ask_gpt(q: str, budget: str | None = None, preference: str | None = None) -> ShoppingAdvice:
    return shopping_advice(ShoppingRequest(query=q, budget=budget, preference=preference))


@app.post("/agent/analyze", response_model=ProblemAnalysis)
def agent_analyze(payload: ShoppingRequest) -> ProblemAnalysis:
    return analyze_problem(payload)


@app.post("/agent/decide", response_model=DecisionResult)
def agent_decide(payload: ShoppingRequest) -> DecisionResult:
    return decide_search(analyze_problem(payload))


@app.get("/agent/search-products", response_model=ProductSearchResult)
def agent_search_products(keyword: str, platform: list[Platform] | None = None) -> ProductSearchResult:
    return search_products(keyword, platform)


@app.post("/agent/recommend", response_model=RecommendationResult)
def agent_recommend(payload: ProductSearchResult) -> RecommendationResult:
    return recommend_products(payload.products, payload.keyword)


@app.post("/agent/run", response_model=AgentRunResult)
def agent_run(payload: ShoppingRequest) -> AgentRunResult:
    return run_agent(payload)


@app.post("/agent/plan-products", response_model=PlanProductsResult)
def agent_plan_products(payload: PlanProductsRequest) -> PlanProductsResult:
    return recommend_missing_plan_items(payload)


@app.post("/line/webhook")
async def line_webhook(request: Request) -> dict[str, Any]:
    raw_body = await request.body()
    verify_line_signature(raw_body, request.headers.get("x-line-signature"))
    payload = LineWebhookPayload.model_validate(json.loads(raw_body or b"{}"))
    replies = []
    delivery_results = []

    for event in payload.events:
        if event.type != "message":
            continue
        text = ""
        if event.message and event.message.get("type") == "text":
            text = str(event.message.get("text", "")).strip()
        if not text:
            continue

        result = run_agent(ShoppingRequest(query=text))
        messages = [
            {
                "type": "text",
                "text": (
                    f"我判斷你的需求是：{result.analysis.problem}\n"
                    f"推薦方向：{result.decision.selected_solution.method}"
                ),
            },
            result.line_flex_message,
        ]
        replies.append({"replyToken": event.replyToken, "messages": messages})
        delivery_results.append(reply_to_line(event.replyToken, messages))

    return {
        "status": "ok",
        "mode": "reply_api",
        "note": "如果 replyToken 是本機 dummy，系統會略過實際 LINE 回覆。",
        "reply_messages": replies,
        "delivery_results": delivery_results,
    }
