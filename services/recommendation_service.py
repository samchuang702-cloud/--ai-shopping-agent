from typing import Any

from fastapi import HTTPException
from pydantic import ValidationError

from models.recommendation import (
    AgentRunResult,
    DecisionResult,
    ItemProductGroup,
    PlanProductsRequest,
    PlanProductsResult,
    ProblemAnalysis,
    RecommendationItem,
    RecommendationResult,
    SolutionOption,
)
from models.shopping import Product, ShoppingRequest
from services.openai_service import llm_json
from services.pchome_service import search_products


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
