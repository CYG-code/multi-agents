# multi-agents

## 后端启动（Windows PowerShell）
```powershell
cd d:\Projects\multi-agents\backend
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
alembic upgrade head
python -m uvicorn app.main:app --reload --port 8000
```

## 前端启动
```powershell
cd d:\Projects\multi-agents\frontend
npm install
npm run dev
```

## 环境变量文件
- `backend/.env.example`：已提交到仓库的模板文件
- `backend/.env`：本地运行配置（不要提交）

创建本地配置：
```powershell
cd d:\Projects\multi-agents\backend
Copy-Item .env.example .env
```

## Relay API 配置（yunwu.ai）
`backend/.env` 推荐配置：
```env
LLM_PROVIDER=openai_compatible
AI_API_KEY=your_token_here
AI_BASE_URL=https://yunwu.ai/v1
AGENT_MODEL=selected_model_name
DEBUG=true
```

说明：
- `AI_BASE_URL` 需要使用带 `/v1` 的地址，以兼容 OpenAI 风格 SDK 调用。
- 如果你误填为 `https://yunwu.ai` 或 `https://yunwu.ai/v1/chat/completions`，
  代码现在会自动规范化为 `https://yunwu.ai/v1`。

## Relay 连通性快速测试
```powershell
cd d:\Projects\multi-agents\backend
$env:RUN_RELAY_API_TEST='1'
python -m pytest tests/integration/test_relay_api_connection.py -q
```

期望结果：
- 出现 `1 passed` 表示 Relay 连通性和流式生成功能都正常。

## 本机 / 局域网快速切换
1. 本机模式

在项目根目录同时启动后端和前端：

```powershell
cd d:\Projects\multi-agents
.\start-dev.ps1
```

访问：

- `http://localhost:5173/`

2. 局域网模式

在项目根目录同时启动后端和前端：

```powershell
cd d:\Projects\multi-agents
.\start-dev.ps1 -Lan
```

访问：

- `http://192.168.3.119:5173`

你也可以分别启动后端和前端：

```powershell
# backend
cd d:\Projects\multi-agents\backend
.\start.ps1
.\start.ps1 -Lan

# frontend
cd d:\Projects\multi-agents\frontend
npm run dev
npm run dev:lan
```

## Encoding Guard

This repo now includes a UTF-8 guard to reduce encoding corruption:

1. `.editorconfig` enforces `charset = utf-8`.
2. `.gitattributes` normalizes text file handling in Git.
3. `scripts/check-utf8.ps1` validates tracked text files are UTF-8.

Run check:

```powershell
cd d:\Projects\multi-agents
.\scripts\check-utf8.ps1
```

Strict mode (also fail on UTF-8 BOM):

```powershell
cd d:\Projects\multi-agents
.\scripts\check-utf8.ps1 -FailOnBom
```

Auto-fix UTF-8 BOM for tracked text files:

```powershell
cd d:\Projects\multi-agents
.\scripts\check-utf8.ps1 -FixBom
```
