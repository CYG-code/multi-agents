# multi-agents

## Python 虚拟环境规范（前后端分离）

- 仅使用一个 Python 虚拟环境：`backend/.venv`
- `frontend/` 不使用 Python venv，依赖由 `npm` 管理

目录示例：

```text
d:\Projects\multi-agents\
├── backend\
│   ├── .venv\
│   ├── requirements.txt
│   └── app\
├── frontend\
│   ├── node_modules\
│   ├── package.json
│   └── src\
```

## 后端启动（Windows PowerShell）

```powershell
cd d:\Projects\multi-agents\backend
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
alembic upgrade head
python -m uvicorn app.main:app --reload --port 8000
```

## 环境变量说明（backend）

- `backend/.env.example`：模板文件，提交到仓库
- `backend/.env`：本地实际配置，不提交到仓库

这两个文件同时存在是标准做法，不冲突。推荐流程：

```powershell
cd d:\Projects\multi-agents\backend
Copy-Item .env.example .env
```

然后编辑 `backend/.env`。

## AI 中转站（yunwu.ai）配置

1. 获取令牌  
登录后台 -> 进入“令牌”页面 -> 点击“添加令牌”获取 API Key。

2. 配置环境变量（`backend/.env`）

```env
AI_API_KEY=your_token_here
AI_BASE_URL=https://yunwu.ai
AGENT_MODEL=selected_model_name
```

`AI_BASE_URL` 如遇客户端兼容问题，可依次尝试：
- `https://yunwu.ai`
- `https://yunwu.ai/v1`
- `https://yunwu.ai/v1/chat/completions`

3. 测试验证
- 直接启动后端并在前端聊天页测试
- 或用 Postman 调用接口测试

## 前端启动

```powershell
cd d:\Projects\multi-agents\frontend
npm install
npm run dev
```
