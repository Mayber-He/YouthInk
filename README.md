# YouthInk · 青春小说工作台

面向百万字级青春小说创作的 Web 工作台。采用 **React + TypeScript + Python FastAPI** 单体同源部署架构，内置双库隔离（`global.db` + 每部作品独立 `novel.db`）、六层前缀缓存友好 Prompt 体系与三层防幻觉记忆系统。

## 快速启动

### 方式一：一键启动脚本（推荐 · 支持前后端热更新）

- **Windows**:
  ```bat
  .\start.bat
  ```
- **Linux / macOS**:
  ```bash
  chmod +x start.sh && ./start.sh
  ```

脚本默认启动**前后端热更新开发模式**：
- 前端页面 (Vite HMR): `http://localhost:5173`（自动代理 `/api` 至后端）
- 后端接口 (FastAPI 自动重载): `http://localhost:8000`
- 接口文档 (Swagger UI): `http://localhost:8000/docs`

> 如需以**生产模式**运行静态资源托管，可执行 `.\start.bat --prod` 或 `./start.sh --prod`。

### 方式二：手动分步启动（本地热重载开发）

1. **启动后端**（默认监听 `8000` 端口）：
   ```bash
   cd backend
   pip install -r requirements.txt
   python -m uvicorn app.main:app --reload --port 8000
   ```
2. **启动前端**（默认监听 `5173` 端口，自动代理 `/api` 至后端）：
   ```bash
   cd frontend
   npm install
   npm run dev
   ```

### 方式三：Docker Compose 部署

```bash
docker compose up --build -d
```

## 文档索引

- [设计文档 (docs/design.md)](./docs/design.md)
- [开发规范文档 (docs/development.md)](./docs/development.md)
