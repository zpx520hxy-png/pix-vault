#!/usr/bin/env python3
"""Normalize local video tags and rebuild the MissAV filter index."""

import argparse
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PICKER_PATH = ROOT / "picker_data.json"
JABLE_PATH = ROOT / "jable_data.json"
INDEX_PATH = ROOT / "picker_index.json"

CATEGORY_ORDER = (
    "画质与版本",
    "人物与身份",
    "身材与外观",
    "行为与玩法",
    "关系与人数",
    "题材与情境",
    "特殊题材",
    "其他",
)

ALIASES = {
    "角色劇情": "剧情",
    "角色剧情": "剧情",
    "顏射": "颜射",
    "調教": "调教",
    "主奴調教": "主奴调教",
    "媚藥": "春药",
    "出軌": "不伦",
    "出轨": "不伦",
    "直接開啪": "直接开啪",
    "絲襪": "丝袜",
    "校服": "制服",
    "制服誘惑": "制服",
    "制服诱惑": "制服",
    "老師": "老师",
    "處女": "处女",
    "錄像": "录像",
    "運動裝": "运动装",
    "漁網": "渔网",
    "吊帶襪": "吊带袜",
    "短髮": "短发",
    "黑絲": "黑丝",
    "進犯": "强奸",
    "男友視角": "主观视角",
    "學校": "学校",
    "誘惑": "诱惑",
    "少女": "美少女",
    "多P": "多人运动",
    "3P": "多人运动",
    "多P群交": "多人运动",
}

EXPANSIONS = {
    "絲襪美腿": ("丝袜", "美腿"),
    "处女作/引退作": ("处女", "引退"),
    "處女作/引退作": ("处女", "引退"),
    "集團進犯": ("强奸", "多人运动"),
}

TITLE_TAGS = (
    ("VR", ("VR",)),
    ("4K", ("4K",)),
    ("中文字幕", ("中文字幕",)),
    ("中文幕", ("中文字幕",)),
    ("巨乳", ("巨乳",)),
    ("超乳", ("超乳",)),
    ("美乳", ("美乳",)),
    ("美腿", ("美腿",)),
    ("美尻", ("美尻",)),
    ("黑絲", ("黑丝",)),
    ("黑丝", ("黑丝",)),
    ("絲襪", ("丝袜",)),
    ("丝袜", ("丝袜",)),
    ("眼鏡", ("眼镜娘",)),
    ("眼镜", ("眼镜娘",)),
    ("短髮", ("短发",)),
    ("短发", ("短发",)),
    ("制服", ("制服",)),
    ("校服", ("制服",)),
    ("女僕", ("女仆",)),
    ("女仆", ("女仆",)),
    ("護士", ("护士",)),
    ("护士", ("护士",)),
    ("女教師", ("女教师",)),
    ("女教师", ("女教师",)),
    ("老師", ("老师",)),
    ("老师", ("老师",)),
    ("女高中", ("女高中生",)),
    ("女大生", ("女大学生",)),
    ("女大学", ("女大学生",)),
    ("人妻", ("人妻",)),
    ("熟女", ("熟女",)),
    ("OL", ("OL",)),
    ("姐姐", ("姐姐",)),
    ("姊姊", ("姐姐",)),
    ("NTR", ("NTR",)),
    ("不倫", ("不伦",)),
    ("不伦", ("不伦",)),
    ("出軌", ("不伦",)),
    ("出轨", ("不伦",)),
    ("中出", ("中出",)),
    ("顏射", ("颜射",)),
    ("颜射", ("颜射",)),
    ("口交", ("口交",)),
    ("乳交", ("乳交",)),
    ("接吻", ("接吻",)),
    ("潮吹", ("潮吹",)),
    ("高潮", ("高潮",)),
    ("騎乘", ("骑乘",)),
    ("骑乘", ("骑乘",)),
    ("手淫", ("手淫",)),
    ("深喉", ("深喉",)),
    ("腳交", ("脚交",)),
    ("脚交", ("脚交",)),
    ("亂交", ("乱交",)),
    ("乱交", ("乱交",)),
    ("調教", ("调教",)),
    ("调教", ("调教",)),
    ("集團進犯", ("强奸", "多人运动")),
    ("集团进犯", ("强奸", "多人运动")),
    ("春藥", ("春药",)),
    ("春药", ("春药",)),
    ("痴女", ("痴女",)),
    ("凌辱", ("凌辱",)),
    ("強姦", ("强奸",)),
    ("强奸", ("强奸",)),
    ("羞辱", ("羞辱",)),
    ("按摩", ("按摩",)),
    ("出差", ("出差",)),
    ("自拍", ("自拍",)),
    ("露出", ("露出",)),
)

MULTI_TITLE_MARKERS = ("3P", "多P", "多人", "群交", "亂交", "乱交", "大亂交", "大乱交")
MULTI_TAGS = {"多人运动", "乱交"}

CATEGORY_TAGS = {
    "画质与版本": {
        "4K",
        "VR",
        "高清",
        "独家",
        "中文字幕",
        "超薄格",
        "薄格",
        "合集",
        "4小时以上",
        "纪录片",
        "自拍",
        "无码流出",
        "BEST",
    },
    "人物与身份": {
        "美少女",
        "熟女",
        "人妻",
        "OL",
        "女高中生",
        "女大学生",
        "老师",
        "女教师",
        "偶像艺人",
        "姐姐",
        "妹妹",
        "女仆",
        "护士",
        "女神",
        "处女",
        "制服",
        "引退",
    },
    "身材与外观": {
        "巨乳",
        "超乳",
        "美乳",
        "苗条",
        "美腿",
        "美尻",
        "丝袜",
        "黑丝",
        "眼镜娘",
        "短发",
        "水着",
        "运动装",
        "吊带袜",
        "渔网",
        "巨乳偏好",
    },
    "行为与玩法": {
        "中出",
        "颜射",
        "口交",
        "口爆",
        "乳交",
        "接吻",
        "高潮",
        "极限高潮",
        "潮吹",
        "骑乘",
        "手淫",
        "深喉",
        "脚交",
        "爆汗",
        "强制口交",
    },
    "关系与人数": {"单体作品", "多人运动", "乱交", "姐妹", "亲属"},
    "题材与情境": {
        "NTR",
        "不伦",
        "剧情",
        "出道",
        "出差",
        "主观视角",
        "按摩",
        "按摩油",
        "回春按摩",
        "诱惑",
        "直接开啪",
        "录像",
        "学校",
        "汽车",
        "厕所",
        "露出",
    },
    "特殊题材": {
        "强奸",
        "凌辱",
        "调教",
        "主奴调教",
        "春药",
        "痴女",
        "羞辱",
        "淫乱",
        "淫语",
        "凌辱快感",
        "监狱",
        "痉挛",
        "时间停止",
    },
}


def sort_tags(counts):
    return sorted(counts, key=lambda tag: (-counts[tag], tag.casefold()))


def normalized_tags(video):
    tags = []
    seen = set()
    original = video.get("tags")
    for value in original if isinstance(original, list) else []:
        if not isinstance(value, str):
            continue
        tag = value.strip()
        if not tag:
            continue
        replacements = EXPANSIONS.get(tag, (ALIASES.get(tag, tag),))
        for replacement in replacements:
            if replacement not in seen:
                tags.append(replacement)
                seen.add(replacement)

    title = str(video.get("title") or "")
    for marker, additions in TITLE_TAGS:
        if marker in title:
            for addition in additions:
                if addition not in seen:
                    tags.append(addition)
                    seen.add(addition)
    return tags


def category_for(tag):
    for category in CATEGORY_ORDER:
        if tag in CATEGORY_TAGS.get(category, set()):
            return category
    return "其他"


def build_tag_metadata(videos):
    counts = Counter()
    for video in videos:
        counts.update(video.get("tags", []))
    sorted_tags = sort_tags(counts)
    groups = {category: [] for category in CATEGORY_ORDER}
    for tag in sorted_tags:
        groups[category_for(tag)].append(tag)
    return (
        sorted_tags,
        dict(counts),
        {key: value for key, value in groups.items() if value},
    )


def normalize_data(data):
    changes = {"tags": 0, "multi": 0}
    videos = data.get("videos", [])
    for video in videos:
        tags = normalized_tags(video)
        if "tags" not in video or tags != video.get("tags", []):
            video["tags"] = tags
            changes["tags"] += 1
        title = str(video.get("title") or "")
        if not video.get("is_multi") and (
            any(tag in MULTI_TAGS for tag in tags)
            or any(marker in title for marker in MULTI_TITLE_MARKERS)
        ):
            video["is_multi"] = True
            changes["multi"] += 1
    tags, counts, groups = build_tag_metadata(videos)
    data["tags"] = tags
    data["tag_counts"] = counts
    data["tag_groups"] = groups
    return changes


def build_index(data):
    videos = data.get("videos", [])
    counts = Counter()
    actresses = set()
    for video in videos:
        counts.update(set(video.get("tags", [])))
        for actress in video.get("actresses") or []:
            if isinstance(actress, str) and actress.strip():
                actresses.add(actress.strip())
    return {
        "actresses": sorted(actresses),
        "actress_groups": data.get("actress_groups", {}),
        "actress_avatars": data.get("actress_avatars", {}),
        "actress_display": data.get("actress_display", {}),
        "actress_aid": data.get("actress_aid", {}),
        "tags": sort_tags(counts),
        "tag_counts": dict(counts),
        "tag_groups": data.get("tag_groups", {}),
        "total_videos": len(videos),
    }


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, value):
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="Report changes without writing files."
    )
    args = parser.parse_args()

    picker = load_json(PICKER_PATH)
    jable = load_json(JABLE_PATH)
    picker_changes = normalize_data(picker)
    jable_changes = normalize_data(jable)
    index = build_index(picker)

    print(
        "MissAV: {tags} tag updates, {multi} multi-video corrections, {count} tags".format(
            **picker_changes, count=len(picker["tag_counts"])
        )
    )
    print(
        "Jable: {tags} tag updates, {multi} multi-video corrections, {count} tags".format(
            **jable_changes, count=len(jable["tag_counts"])
        )
    )
    print(
        "MissAV index: {videos} videos, {tags} tags".format(
            videos=index["total_videos"], tags=len(index["tags"])
        )
    )
    if args.check:
        return

    write_json(PICKER_PATH, picker)
    write_json(JABLE_PATH, jable)
    write_json(INDEX_PATH, index)


if __name__ == "__main__":
    main()
