# 任务计划：MissAV Picker V2 架构重构

## 目标
在新目录 tools/missav_picker_v2/ 完成模块化重构，不动现有 tools/missav_picker/，用新端口调试。

## 当前阶段
阶段1

## 阶段

### 阶段1：后端模块化
- [ ] 拆分 server.py → server/ 包
  - server/__init__.py
  - server/app.py (HTTP 路由入口)
  - server/sources.py (数据源：missav/jable)
  - server/play_proxy.py (播放代理 + hlsUrl 提取)
  - server/trending.py (热门抓取 + 缓存)
  - server/cache.py (缓存层：图片/视频/热门分级)
  - server/img_proxy.py (图片代理)
  - server/sync_state.py (局域网同步)
  - server/config.py (配置常量)
- [ ] 修复已知 bug：browser_hls_map 未定义
- [ ] 数据文件软链接到现有 jable_data.json / picker_data.json
- **状态：** in_progress

### 阶段2：前端拆分
- [ ] index.html → 纯结构
- [ ] app.css → 样式（含 Premium skin）
- [ ] app.js → 逻辑（按功能分模块）
  - modules/state.js (全局 state + sync)
  - modules/render.js (renderResult/renderHistory/renderFavorites)
  - modules/player.js (initJplayer/mountHls)
  - modules/trending.js (热门板块)
  - modules/filters.js (筛选/女优/标签)
  - modules/browse.js (浏览/候选抽卡)
  - modules/api.js (fetch 封装)
- **状态：** pending

### 阶段3：播放链路异步化
- [ ] /play/<code> → 立即返回队列状态
- [ ] 后台异步解析 hlsUrl + 预缓存
- [ ] /play/<code>/status 轮询
- [ ] 前端适配：先显示"加载中"，status ready 再播
- **状态：** pending

### 阶段4：数据源插件化 + 缓存策略
- [ ] VideoSource 抽象基类
- [ ] JableSource / MissavSource 实现
- [ ] 缓存分级 L1(内存)/L2(磁盘)
- [ ] LRU 淘汰按 play/img 分开
- **状态：** pending

### 阶段5：新端口启动 + 验证
- [ ] 端口 8700 启动
- [ ] 验证页面加载/筛选/抽片/热门/收藏/播放
- [ ] 提交
- **状态：** pending

## 已做决策
| 决策 | 理由 |
|----------|-----------|
| 新目录 tools/missav_picker_v2/ | 不动现有工具 |
| 端口 8700 | 8699 现有工具，8700 空闲 |
| 数据文件软链接 | 避免复制大 JSON |
| 保持 stdlib http.server | 个人项目不需要 FastAPI |

## 遇到的错误
| 错误 | 尝试次数 | 解决方法 |
|-------|---------|------------|
