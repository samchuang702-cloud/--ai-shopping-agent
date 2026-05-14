# AI Shopping Agent 開發指南

這個專案是 FastAPI 版的 AI 購物代理服務，提供網頁介面、OpenAI 分析、PChome 商品搜尋、推薦排序，以及 LINE webhook 回覆能力。使用者是 SAM，回覆與介面內容優先使用繁體中文。

## 專案架構

```text
ai-shopping-agent/
├── app.py
├── requirements.txt
├── .env
├── templates/
│   └── index.html
├── static/
├── routers/
│   ├── agent.py
│   ├── line.py
│   └── health.py
├── services/
│   ├── openai_service.py
│   ├── pchome_service.py
│   ├── recommendation_service.py
│   └── line_service.py
└── models/
    ├── shopping.py
    ├── recommendation.py
    └── line.py
```

## 各檔案責任

- `app.py`：只負責建立 FastAPI app、載入 `.env`、設定 `templates/static`、註冊 routers。不要把業務邏輯再塞回這裡。
- `templates/index.html`：首頁 UI。FastAPI 使用 `BASE_DIR / "templates"` 載入模板，避免因啟動目錄不同而找不到 HTML。
- `routers/agent.py`：購物代理 API endpoint，例如 `/agent/analyze`、`/agent/run`、`/agent/plan-products`。
- `routers/line.py`：LINE webhook endpoint，負責接收 LINE event 並呼叫 agent 流程。
- `routers/health.py`：健康檢查 endpoint。
- `services/openai_service.py`：OpenAI client、JSON 解析與 LLM 呼叫。
- `services/pchome_service.py`：PChome 搜尋、商品資料整理、測試商品 fallback。
- `services/recommendation_service.py`：問題分析、方案決策、推薦排序、LINE Flex Message 組裝。
- `services/line_service.py`：LINE signature 驗證與 Reply API。
- `models/`：Pydantic schema，只放資料模型與型別定義。

## 本機啟動

```powershell
.\.venv\Scripts\python.exe -m uvicorn app:app --reload --host 127.0.0.1 --port 8000
```

常用網址：

- 首頁：http://127.0.0.1:8000/
- API 文件：http://127.0.0.1:8000/docs
- 健康檢查：http://127.0.0.1:8000/health

## 環境變數

`.env` 需要包含：

```env
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-4.1-mini
LINE_CHANNEL_ACCESS_TOKEN=your_line_channel_access_token_here
LINE_CHANNEL_SECRET=your_line_channel_secret_here
LINE_VERIFY_SIGNATURE=false
```

本機測試 LINE webhook 時，`LINE_VERIFY_SIGNATURE=false` 比較方便；正式串接時再改成 `true`，並確認 `LINE_CHANNEL_SECRET` 正確。

## 驗證指令

修改 Python 後先跑語法檢查：

```powershell
.\.venv\Scripts\python.exe -m py_compile app.py routers\agent.py routers\line.py routers\health.py services\openai_service.py services\pchome_service.py services\recommendation_service.py services\line_service.py models\shopping.py models\recommendation.py models\line.py
```

確認首頁與健康檢查：

```powershell
.\.venv\Scripts\python.exe -c "from fastapi.testclient import TestClient; from app import app; c=TestClient(app); print(c.get('/').status_code); print(c.get('/health').json())"
```

## 開發規範

- 新增 API endpoint 時，優先放在 `routers/`，不要直接寫在 `app.py`。
- 新增外部服務串接時，放在 `services/`，並讓 router 只做 request/response 協調。
- 新增或調整資料格式時，先更新 `models/`，再調整 service 和 router。
- OpenAI 回傳內容必須維持可被 Pydantic model 驗證；若 LLM 失敗，保留 fallback 流程。
- PChome 搜尋可能會失敗或沒有資料，API 應回傳清楚錯誤或 fallback，不要讓頁面直接崩潰。
- 不要提交 `.env` 的真實金鑰。
- `__pycache__`、log 檔、暫存檔不應納入版本控制。

## 模板注意事項

目前首頁使用：

```python
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
return templates.TemplateResponse(request, "index.html")
```

不要改回 `Jinja2Templates(directory="templates")` 或舊版 `TemplateResponse("index.html", {"request": request})` 寫法，否則可能因工作目錄或 Starlette 版本不同而讀不到模板。
