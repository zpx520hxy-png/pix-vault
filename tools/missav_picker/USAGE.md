# MissAV Picker 使用说明

> 局域网 AV 随机选片工具 —— 找女优 / 找标签 / 随机抽片，封面 + 预览 + 直达播放页。

## 🎰 候选抽卡

- 点 `🎰 抽 6 部候选` 会按当前片源、类型、标签、排除标签和女优筛选条件随机生成一组候选。
- 候选会优先避开本轮已抽历史；候选不足 6 部时自动降级为当前筛选池。
- 点候选卡片会把该作品设为当前结果并写入历史；`🔄 重抽` 可刷新本轮候选，`✖ 收起` 会清空候选。
- 局域网同步开启时，手机和电脑会同步候选列表，适合电脑筛选、手机点选。

---

## ⚠️ 必须用 HTTP 打开，不能 file://

这个工具的封面和头像都走**本地图片代理**（`/img/...` 路径），浏览器必须在能访问 server 的协议下才能正常显示。

| 打开方式 | 能不能用 | 原因 |
|---|---|---|
| **http://localhost:8699**（推荐） | ✅ 全部正常 | 有图片代理 + 磁盘缓存 |
| **file:///.../index.html**（opencode 双击 / 资源管理器双击） | ❌ 封面破图 | `fetch('/img/...')` 失败；外链图片被 ORB/CORS 拦 |
| opencode 终端预览（默认用系统浏览器） | ✅ 只要 URL 是 http:// | 看下面"opencode 怎么用" |

> **症状对照**：打开后能看到标题/标签/女优名字，但封面/头像是空白方块 = 你走的是 file://。重启 `server.py` 后用浏览器开 `http://localhost:8699` 即可。

---

## 🚀 启动服务

### 方式 1：双击 `start.bat`（最简单）
```
双击  tools\missav_picker\start.bat
```
启动后无窗口常驻后台，关闭需到任务管理器找 `pythonw.exe`。

### 方式 2：命令行
```bash
cd "D:\360MoveData\Users\Pda\Desktop\claude\tools\missav_picker"
C:\Users\Pda\AppData\Local\Programs\Python\Python311\python.exe server.py
```
按 `Ctrl+C` 停止。

### 方式 3：开机自启
`start.vbs` 已复制到 Windows 启动文件夹，重启电脑自动起。

启动成功会看到：
```
  封面/头像已走本地代理 + 磁盘缓存 (500MB 上限)
  缓存目录: D:\...\tools\missav_picker\.img_cache
  本机:  http://localhost:8699
  手机:  http://192.168.x.x:8699
  状态:  http://localhost:8699/stats
  按 Ctrl+C 停止
```

---

## 🛜 访问地址

| 设备 | URL |
|---|---|
| 本机电脑 | http://localhost:8699 |
| 局域网手机/平板 | http://192.168.x.x:8699（启动时打印） |

---

## 💾 缓存机制（解决"封面/头像不缓冲"问题）

之前的问题：每次刷新页面，server 都要重新从 fourhoi.com 拉图，几十 KB 的图在弱网下慢、还容易被限速。
**已修复**：server.py 加了磁盘缓存。

### 缓存规则
| 情况 | 缓存 TTL | 落盘 |
|---|---|---|
| 图片拉取成功 | 7 天 | ✅ 写到 `.img_cache/<域名>/<路径>` |
| 拉取失败（被墙 / 超时）| 5 分钟 | ✅ 写 `.fail` 空文件，避免反复重试被墙域名 |
| 浏览器侧缓存 | `max-age` 跟随 TTL | 走 HTTP `Cache-Control` 头 |

### 容量控制
- 缓存目录上限 **500MB**（`CACHE_MAX_BYTES`）
- 超过后自动按 mtime 删最旧的 10% 文件
- 想清空：直接删 `tools\missav_picker\.img_cache\` 目录

### 实时状态
打开 `http://localhost:8699/stats` 看：
```
缓存 247 张 / 38.2MB · 命中 1830 / 未命中 247 / 失败 12
```
- 命中 > 未命中 = 缓存生效，秒开
- 失败数 > 0 是正常的（jable CDN 在国内被墙，那部分会显示占位图）

---

## 🌐 opencode 怎么用

Opencode 是终端编辑器，**不能**像 VSCode 那样给 HTML 提供内置 HTTP server。
两种正确打开方式：

### A. 先起服务，opencode 只编辑
```bash
# 1. 终端 1: 启服务
cd "D:\360MoveData\Users\Pda\Desktop\claude\tools\missav_picker"
python server.py

# 2. opencode 编辑代码,浏览器手动开 http://localhost:8699
```

### B. opencode 启动后用 `start` 唤起浏览器
opencode 没有内置 webview，但你可以：
- `Ctrl+Shift+P` → "Open in Default Browser"（opencode 这条命令如果不存在，跳过）
- 直接复制 http://localhost:8699 粘到浏览器

> **不要**直接在 opencode 里点 HTML 文件预览（如果它有这个功能的话），预览走的是 file://，封面会破。

---

## 🔧 故障排查

| 症状 | 原因 | 解决 |
|---|---|---|
| 启动后浏览器连不上 | 端口被占 | 任务管理器杀 `pythonw.exe` 8699 端口的进程 |
| 封面空白 | file:// 打开 | 改用 http://localhost:8699 |
| 封面加载慢（首次）| 第一次拉图需要时间 | 等 3-5 秒,后续命中缓存秒开 |
| 全部 jable 封面破图 | jable.tv 在国内被墙 | 切到 "MissAV" 标签页（看左下角切换）;或挂代理后重启服务 |
| 缓存占盘太多 | 看图多 | 删 `.img_cache/` 目录,或调小 `CACHE_MAX_BYTES` |

### 看运行日志
```bash
# 实时日志
tail -f tools/missav_picker/server.log
```

---

## 📂 文件结构

```
tools/missav_picker/
├── index.html          # 主页面(单文件,~600KB 含内嵌数据)
├── index_template.html # 模板(给 assemble_picker.py 用)
├── jable_data.json     # Jable 数据源(5 女优 / 75 视频)
├── picker_data.json    # MissAV 完整作品库(内嵌到 HTML)
├── picker_index.json   # 轻量索引
├── server.py           # 本地 HTTP 服务 + 图片代理 + 磁盘缓存
├── start.bat           # 双击启动
├── start.vbs           # 开机自启脚本
├── .img_cache/         # 缓存目录(自动生成,500MB 上限)
└── USAGE.md            # 本文件
```

---

## 🧪 验证服务是否正常

```bash
# 主页
curl -I http://localhost:8699/                          # HTTP 200

# 图片代理 + 缓存命中
curl -I http://localhost:8699/img/fourhoi.com/test.jpg   # 第一次 200,第二次同 URL 应该 < 50ms

# 缓存统计
curl http://localhost:8699/stats                        # 看命中/未命中/失败
```

---

## 🔄 改完代码怎么生效

| 改了 | 生效方式 |
|---|---|
| `index.html` / `index_template.html` | 直接刷新浏览器 (`Ctrl+Shift+R` 强制刷新) |
| `server.py` | 重启服务(`taskkill` + `python server.py`) |
| `jable_data.json` / `picker_data.json` | 浏览器按 `Ctrl+Shift+R` 强制刷新 |
