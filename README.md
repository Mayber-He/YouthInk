# YouthInk · 青春小说工作台

面向百万字级青春小说创作的 Web 工作台。采用 **React + TypeScript + Python FastAPI** 单体同源部署架构，内置双库隔离（`global.db` + 每部作品独立 `novel.db`）、六层前缀缓存友好 Prompt 体系与三层防幻觉记忆系统。

## 快速启动

### 方式一：一键启动脚本（推荐）

- **Windows**:
  ```bat
  .\start.bat
  ```
- **Linux / macOS**:
  ```bash
  chmod +x start.sh && ./start.sh
  ```

启动后浏览器访问：`http://localhost:8000`

### 方式二：本地前后端热重载开发

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
