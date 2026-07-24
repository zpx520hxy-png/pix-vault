# PixVault — 本地图片画廊浏览器

浏览、筛选、收藏、标记不喜欢、幻灯片播放、顺序/随机模式。

## 项目结构

```
.
├── server.py          # 后端
├── run.py             # 生产启动器 -> 8720 端口
├── run_test.py        # 测试启动器 -> 8721 端口
├── static/            # 前端页面、样式与脚本
├── test_images/       # 测试图片目录
├── README.md
├── 启动.bat
└── 启动_测试.bat
```

## 启动

**方式一：双击 bat 文件**
- `启动.bat` — 生产环境（浏览 generated_images）
- `启动_测试.bat` — 测试环境（浏览 test_images）

**方式二：命令行**
```bash
python run.py       # 生产环境
python run_test.py  # 测试环境
```

或直接用环境变量：

```bash
PIXVAULT_PORT=8722 PIXVAULT_IMAGES=/path/to/images python server.py
```

| 启动器 | 端口 | 图片目录 |
|--------|------|----------|
| `run.py` | 8720 | `../generated_images` |
| `run_test.py` | 8721 | `test_images/` |

## 快捷键

| 键 | 功能 |
|----|------|
| `Q` | 随机一张 |
| `空格` | 收藏 / 取消 |
| `D` | 不喜欢 / 取消 |
| `←` `→` | 历史导航 / 顺序翻页 |
| `S` | 幻灯片播放 / 停止 |
| `M` | 随机 ↔ 顺序模式 |
| `G` | 网格视图 |
| `R` | 重新扫描 |
| `Esc` | 关闭弹窗 / 返回网格 |

## 喜好标签

| 标签 | 来源 |
|------|------|
| 写实 / 动漫 | 文件夹名 |
| 大胸 | batch_log + 文件名 |
| 欧美 / 东亚 | 文件名 |
| NSFW | 文件夹名 + batch_log |
| 正常 | 自动（= 无 NSFW） |

## 测试环境

1. 添加图片到 `test_images/`（任意多级子目录）
2. `python run_test.py`
3. 访问 `http://localhost:8721`

测试环境的所有收藏/不喜欢/删除操作都作用于 test_images，不影响主库。
