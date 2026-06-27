"""
从 result.json 生成简体中文 Markdown 文档，每部作品带封面缩略图
"""
import json, datetime, re
from pathlib import Path

ROOT = Path(__file__).parent
result = json.loads((ROOT / "result.json").read_text(encoding="utf-8"))

# 按收藏频次排序
items = sorted(result.values(), key=lambda x: -len(x.get("from_videos", [])))

def cover_url(video_url: str) -> str:
    # 从视频 URL 提取 slug（小写），如 sone-308-uncensored-leak
    # URL 格式: https://missav.ai/dm60/sone-308-uncensored-leak
    #       或 https://missav.ai/cn/ofje-505
    parts = video_url.rstrip("/").split("/")
    slug = parts[-1]
    # 如果最后是 cn，取倒数第二段
    if slug == "cn" and len(parts) >= 2:
        slug = parts[-2]
    return f"https://fourhoi.com/{slug}/cover-t.jpg"

lines = []
lines.append("# MissAV 喜欢女优 + 代表作 Top 10\n")
lines.append("> 数据来源：missav.ai/saved（个人收藏页）\n")
lines.append(f"> 生成时间：{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
lines.append(f"> 总计：**{len(items)} 位女优** | 收藏视频 **{sum(len(a.get('from_videos',[])) for a in items)} 部**（含重复）\n")
lines.append("---\n")

# 目录
lines.append("## 目录\n")
for i, a in enumerate(items, 1):
    fv = len(a.get("from_videos", []))
    anchor = re.sub(r"[^\w一-鿿-]", "", a["name"].replace(" ", "-"))
    lines.append(f"{i}. [{a['name']}](#{i}-{anchor}) — 收藏 {fv} 部")
lines.append("\n---\n")

# 每位女优
for i, a in enumerate(items, 1):
    name = a["name"]
    fv = a.get("from_videos", [])
    top10 = a.get("top10", [])
    url = a.get("url", "")

    lines.append(f"## {i}. {name}\n")
    lines.append(f"- **MissAV 主页**：[链接]({url})")
    lines.append(f"- **收藏的番号**：{', '.join(fv)}")
    lines.append(f"- **收藏次数**：{len(fv)} 部\n")

    if top10:
        lines.append("| # | 封面 | 番号 | 标题 |")
        lines.append("|---|------|------|------|")
        for j, v in enumerate(top10, 1):
            code = v.get("code", "")
            title = v.get("title", "")
            vurl = v.get("url", "")
            img = cover_url(vurl)
            # 标题去掉开头重复的番号
            if title.upper().startswith(code.upper()):
                title = title[len(code):].strip()
            lines.append(f"| {j} | ![]({img}) | [{code}]({vurl}) | {title} |")
    else:
        lines.append("（未抓到代表作）")
    lines.append("\n---\n")

md = "\n".join(lines)
out = ROOT.parent.parent / "docs" / "missav_女优代表作.md"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(md, encoding="utf-8")
print(f"写入 {out}，共 {len(lines)} 行")
