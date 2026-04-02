# 成电吃什么 Agent MVP

面向电子科技大学学生的校园餐饮推荐 Agent（MVP）。

## 技术栈
- 前端: Next.js (TypeScript)
- 后端: FastAPI
- 数据: CSV + SQLite schema 预留

## 项目结构
- `docs/`: PRD、API 设计、页面草图
- `backend/`: FastAPI 服务、mock 数据、推荐逻辑骨架
- `frontend/`: Next.js 页面与组件骨架
- `miniprogram/`: 微信小程序端（推荐、换一批、反馈弹层、匿名身份）

## 快速开始（后续）
1. 进入 `backend/` 安装依赖并运行 API。
2. 进入 `frontend/` 安装依赖并启动前端。
3. 前端默认请求 `http://localhost:8000/api/v1/recommend`。

## 微信小程序运行
1. 使用微信开发者工具打开仓库根目录 `D:\chedian-eat-agent-mvp`。
2. `project.config.json` 已配置 `miniprogramRoot=miniprogram/`。
3. 先启动后端（默认 `http://127.0.0.1:8000`），再在小程序中调试。
4. 小程序请求配置位于 `miniprogram/utils/config.js`。
