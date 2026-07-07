# 🎲 MissAV 随机选片器

一个**局域网 AV 随机选片工具**——根据女优、标签筛选，随机抽取 MissAV 作品，封面 + 预览 + 直达播放页。

## 架构原理

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│  missav.ws   │────▶│  result.json  │────▶│ picker_data.json │
│  (数据源头)   │ 爬取  │  (女优+作品)   │ 构建  │  (前端数据)       │
└─────────────┘     └──────────────┘     └─────────────────┘
                                                │
                                          ┌─────▼─────┐
                                          │ server.py  │  HTTP :8699
                                          │ index.html │  gzip + 图片代理
                                          └─────┬─────┘
                                        ┌───────┴───────┐
                                        ▼               ▼
                                    PC 浏览器        手机浏览器
                                  localhost:8699   192.168.x.x:8699
```

### 数据流

1. **爬取** (`scripts/missav_scrape/`) — 从 missav.ws 爬取女优主页的作品列表
2. **构建** (`scripts/build_picker_data.py`) — 汇合作品库 JSON（~560KB），含封面URL/预览MP4/标签/女优分组
3. **组装** (`scripts/assemble_picker.py`) — 将 JSON 内嵌到 HTML 模板生成 `index.html`
4. **服务** (`server.py`) — Python HTTP 服务器，gzip 压缩 + 图片反向代理

### 图片代理

浏览器直接加载 `fourhoi.com` 图片会被浏览器 ORB/CORS 策略拦截。server.py 提供 `/img/` 路由：

```
浏览器请求 /img/fourhoi.com/xxx/cover-t.jpg
       │
       ▼
server.py 用 urllib.request 服务端转发 (纯 Python，无子进程)
       │
       ▼
返回图片给浏览器 (同源，无跨域问题)
```

**不会产生磁盘缓存**——全部在内存中透传，不落盘。

### 首屏加载优化

```
第1步 (20KB gzip)          第2步 (120KB gzip)
picker_index.json    →    picker_data.json
(女优列表/头像/标签)       (全部作品详情)
     │                        │
     ▼                        ▼
  立刻渲染 UI              异步后台加载
  女优/标签立即可见          随机/浏览功能可用
```

### 数据语义：`saved` 有两个独立含义

前端"已收藏"标签背后其实是**两个不同维度**的数据源，名称都叫 `saved` 但不要混用：

| 字段 | 含义 | 数据来源 | 范围 |
|---|---|---|---|
| `videos[*].is_saved` (bool) | 你**收藏了这部作品** | `scripts/missav_scrape/saved.json` | 作品级 |
| `actress_groups[code] == 'saved'` | 这位女优在**关注名单**里 | `scripts/picker_lib/saved_actresses.AUTH_SAVED_NAMES` (子串匹配 39 位) | 女优级 |

UI 上的对应关系：

- 卡片角标 "⭐ 已收藏" / chip 过滤 "⭐ 仅收藏" → `videos[*].is_saved`
- 左侧女优网格 "⭐ 已收藏" 分桶 → `actress_groups[*] == 'saved'`

**注意**：
- `AUTH_SAVED_NAMES` 用的是**子串匹配** (`a in n or n in a`)，名字里含相同字符的不同女优可能被误判成"关注"
- 两套维度**没有强制一致性**：一位"已收藏女优"的作品不一定是 `is_saved=true`（可能这部没收藏但女优关注了）；一部 `is_saved=true` 的作品的女优不一定是"已收藏女优"（可能这部被收藏但女优不在关注名单里）
- 改 `AUTH_SAVED_NAMES` → 重跑 `python scripts/build_picker_data.py` 即可

### 女优分组逻辑

| 组 | 判定 |
|---|---|
| ⭐ 已收藏 (= 关注名单) | 名字在 `AUTH_SAVED_NAMES` 里命中（子串匹配） |
| 🌟 新人 | Top 15 作品中有「出道/首秀/NO.1 STYLE」关键词 |
| 👤 其他 | 其余 |

### 合集过滤

剔除以下系列（即使标题/番号含它们也不算"单人作品"）：
- `OFJE` S1 GIRLS COLLECTION
- `IDBD` IDEA POCKET BEST
- `MIRD` MOODYZ 粉丝感谢/巴士之旅
- `MIZD/MKCK/PPBD/BMW/PBD` 各类 BEST 合集
- 标题含「全明星/感谢会/12小时/48小时/20周年/双打」等关键词

## 缓存说明

| 缓存位置 | 类型 | 大小 |
|---|---|---|
| 浏览器内存 | `picker_index.json` 数据 | ~100KB |
| 浏览器内存 | `picker_data.json` 数据 | ~550KB |
| 浏览器 HTTP 缓存 | JSON 文件 (no-cache, 每次校验) | 0 |
| 浏览器 HTTP 缓存 | 图片 (`max-age=86400`, 24小时) | 取决于浏览量 |
| localStorage | 抽片历史 (最近 12 条番号) | <1KB |
| **磁盘** | **无** (图片代理纯内存透传，不写文件) | **0** |

**不会堆积大量缓存**。唯一持久化的是 localStorage 里的 12 条番号历史。

## 目录结构

```
tools/missav_picker/
├── index.html          # 单文件 (file:// 也可以用)
├── index_template.html # HTML 模板 (有 __DATA_JSON_PLACEHOLDER__)
├── picker_data.json    # 完整作品库 JSON
├── picker_index.json   # 轻量索引 (首屏用)
├── server.py           # 局域网 HTTP 服务器 (gzip + 图片代理)
├── start.bat           # 双击启动 (pythonw.exe 无窗口)
├── start.vbs           # 开机自启脚本
└── fix_template.py     # 模板修复工具

scripts/
├── build_picker_data.py    # 构建 picker 数据
├── assemble_picker.py      # 组装 index.html
├── missav_scrape/
│   ├── scrape.py            # curl 爬取
│   ├── result.json          # 旧爬取结果 (102女优)
│   ├── result_solo15.json   # 新爬取结果 (118女优, 每人15部)
│   ├── scrape_avatars.py    # 爬取女优头像ID
│   ├── recrawl_solo15.py    # 补爬单人作品
│   └── cookies.txt          # MissAV cookie
└── generate_final.py        # 生成 missav_女优代表作.md
```

## 启动方式

| 方式 | 命令 |
|---|---|
| 双击启动 | `start.bat` |
| 命令行 | `python server.py` |
| 开机自启 | 已复制到 `启动` 文件夹 (missav_picker.vbs) |

## 访问地址

- 本机: `http://localhost:8699`
- 手机: `http://<本机IP>:8699`
