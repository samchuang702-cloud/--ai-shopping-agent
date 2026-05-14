# AI 智慧購物代理

這是一個以 FastAPI 建立的 AI 購物代理系統，可以透過網頁或 LINE 使用。使用者輸入購物需求後，系統會分析問題、決定搜尋方向、搜尋 PChome 真實商品，最後輸出推薦商品與商品連結。

## 目前完成狀態

- 中文網頁前端：`http://127.0.0.1:8001/`
- OpenAI 需求分析與決策流程
- PChome 24h 真實商品搜尋
- 商品價格、圖片、商品頁連結顯示
- LINE webhook 串接
- LINE Flex Message 商品卡片
- ngrok 本機 webhook 測試流程

## 系統流程

```text
使用者輸入需求
-> FastAPI
-> AI 問題分析
-> Decision Agent 決定搜尋方向
-> PChome 商品搜尋
-> 商品整理與推薦排序
-> 網頁顯示或 LINE Flex Message 回覆
```

LINE 流程：

```text
LINE 使用者訊息
-> ngrok 公開網址
-> /line/webhook
-> AI 分析
-> PChome 搜尋
-> LINE 回覆文字與商品卡片
```

## 安裝

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

編輯 `.env`，填入必要設定：

```env
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_MODEL=gpt-4.1-mini
LINE_CHANNEL_ACCESS_TOKEN=your_line_channel_access_token_here
LINE_CHANNEL_SECRET=your_line_channel_secret_here
LINE_VERIFY_SIGNATURE=false
```

本機測試 LINE 時，`LINE_VERIFY_SIGNATURE=false` 可以先保留。正式上線時再改成 `true`，並確認 Channel secret 正確。

## 啟動服務

```powershell
.\.venv\Scripts\python.exe -m uvicorn app:app --reload --host 127.0.0.1 --port 8001
```

如果瀏覽器出現 `ERR_CONNECTION_REFUSED`，通常代表 FastAPI 已經停止，請重新執行上面的啟動指令。

常用網址：

- 中文網頁：`http://127.0.0.1:8001/`
- API 文件：`http://127.0.0.1:8001/docs`
- 健康檢查：`http://127.0.0.1:8001/health`

## 常見問題

### 連不上 `127.0.0.1:8001`

請先確認 FastAPI 是否仍在執行。若服務已停止，重新啟動：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app:app --reload --host 127.0.0.1 --port 8001
```

如果有使用 LINE 測試，FastAPI 和 ngrok 都要同時保持開啟。

## 網頁使用方式

打開：

```text
http://127.0.0.1:8001/
```

輸入需求，例如：

```text
推薦適合租屋處的小型除濕機
```

按下「開始分析並推薦」，系統會顯示：

- 多個解決計畫
- 每個計畫的做法
- 每個計畫需要的物品
- 勾選你缺少的物品
- 根據缺少物品搜尋 PChome 真實商品
- 商品圖片、價格與商品連結

範例流程：

```text
輸入：找除地板發霉的方法
-> 系統提供多個方案，例如白醋＋小蘇打、稀釋漂白水、除霉清潔劑
-> 選擇「稀釋漂白水消毒」
-> 勾選缺少「漂白水」和「手套」
-> 系統推薦 PChome 上的漂白水與清潔手套商品
```

## LINE 使用方式

先啟動 FastAPI，再用 ngrok 開公開網址：

第一個終端機啟動 FastAPI：

```powershell
cd C:\Users\samch\Desktop\ai-shopping-agent
.\.venv\Scripts\python.exe -m uvicorn app:app --reload --host 127.0.0.1 --port 8001
```

第二個終端機啟動 ngrok：

```powershell
ngrok http 8001
```

ngrok 會顯示類似：

```text
Forwarding  https://xxxx.ngrok-free.dev -> http://localhost:8001
```

你要連的公開網頁網址是：

```text
https://xxxx.ngrok-free.dev/
```

到 LINE Developers 後台，把 Webhook URL 設成：

```text
https://xxxx.ngrok-free.dev/line/webhook
```

然後：

1. 開啟 `Use webhook`
2. 關閉自動回覆，避免與 AI bot 回覆衝突
3. 按 `Verify`
4. 用 LINE 傳訊息測試

測試訊息：

```text
推薦適合租屋處的小型除濕機
```

預期 LINE 會回覆：

- AI 判斷文字
- PChome 商品卡片
- `查看商品` 按鈕

注意：FastAPI 和 ngrok 都要同時保持開啟。只要關掉其中一個，網頁或 LINE webhook 就會連不上。

## 主要 API

### 完整代理流程

```powershell
Invoke-WebRequest -UseBasicParsing `
  -Method POST `
  -ContentType "application/json" `
  -Body '{"query":"推薦適合租屋處的小型除濕機","budget":"NTD5000"}' `
  "http://127.0.0.1:8001/agent/run"
```

### PChome 商品搜尋

```powershell
Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:8001/agent/search-products?keyword=小型除濕機"
```

### LINE webhook 本機測試

```powershell
Invoke-WebRequest -UseBasicParsing `
  -Method POST `
  -ContentType "application/json" `
  -Body '{"events":[{"type":"message","replyToken":"dummy-token","message":{"type":"text","text":"推薦適合租屋處的小型除濕機"}}]}' `
  "http://127.0.0.1:8001/line/webhook"
```

## 商品資料格式

目前商品搜尋會回傳統一格式：

```json
{
  "platform": "pchome",
  "title": "商品名稱",
  "price": 3990,
  "rating": null,
  "sales": null,
  "shipping_fee": 0,
  "image": "商品圖片網址",
  "url": "商品頁網址"
}
```

PChome 搜尋 API 沒有穩定提供評分與銷量，所以目前 `rating` 與 `sales` 可能是 `null`。

## 下一步

建議優先做：

1. 改善推薦排序，避免只用價格判斷。
2. 讓 AI 根據商品名稱、用途、坪數與預算判斷最適合商品。
3. 串接 momo 商品搜尋。
4. 串接 Shopee 商品搜尋。
5. 正式上線前打開 LINE 簽章驗證。

待新增的商品 collector：

```text
collect_momo_products(keyword)
collect_shopee_products(keyword)
```
