import httpx
from fastapi import HTTPException

from models.shopping import Platform, Product, ProductSearchResult


PCHOME_SEARCH_URL = "https://ecshweb.pchome.com.tw/search/v3.3/all/results"
PCHOME_PRODUCT_URL = "https://24h.pchome.com.tw/prod/{product_id}"
PCHOME_IMAGE_HOST = "https://cs-a.ecimg.tw"


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

