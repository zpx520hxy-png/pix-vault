# -*- coding: utf-8 -*-
"""构建 Jable.tv 作品库 JSON (小规模demo版)"""
import json
from pathlib import Path

ROOT = Path('D:/360MoveData/Users/Pda/Desktop/claude/tools/missav_picker')

# 5 位女优 × 15 部作品 (code, title, url 已知; cover 用 og:image 需要从视频页获取)
# 先用 placeholder,后续从浏览器补充
jable_actresses = [
    {
        'name': '三上悠亜',
        'slug': 'yua-mikami',
        'avatar': 'https://assets-cdn.jable.tv/contents/models/32/s1_mikami_yua.jpg',
        'videos': [
            {'code':'SSIS-834','title':'完全引退 AV女優 最後的1天 三上悠亞最後的SEX','url':'https://jable.tv/videos/ssis-834/'},
            {'code':'SSIS-816','title':'超級明星女優大亂交 激烈稀有共演 S1粉絲感謝祭','url':'https://jable.tv/videos/ssis-816/'},
            {'code':'SSIS-795','title':'三上悠亞用春藥失神 毎天偷偷下春藥7日後的高潮婊子','url':'https://jable.tv/videos/ssis-795/'},
            {'code':'IPZZ-077','title':'IPZZ-077','url':'https://jable.tv/videos/ipzz-077/'},
            {'code':'SSIS-778','title':'SSIS-778','url':'https://jable.tv/videos/ssis-778/'},
            {'code':'SSIS-777','title':'SSIS-777','url':'https://jable.tv/videos/ssis-777/'},
            {'code':'MIDV-400','title':'MIDV-400','url':'https://jable.tv/videos/midv-400/'},
            {'code':'SSIS-737','title':'Yua Mikami 最後硬他媽的！120分鐘120次！','url':'https://jable.tv/videos/ssis-737/'},
            {'code':'SSIS-698','title':'三上悠亞，新有菜及相澤南','url':'https://jable.tv/videos/ssis-698/'},
            {'code':'SSIS-663','title':'SSIS-663','url':'https://jable.tv/videos/ssis-663/'},
            {'code':'SSIS-604','title':'SSIS-604','url':'https://jable.tv/videos/ssis-604/'},
            {'code':'TEK-097','title':'TEK-097','url':'https://jable.tv/videos/tek-097/'},
            {'code':'SSIS-570','title':'SSIS-570','url':'https://jable.tv/videos/ssis-570/'},
            {'code':'SSIS-541','title':'SSIS-541','url':'https://jable.tv/videos/ssis-541/'},
            {'code':'SSIS-509','title':'SSIS-509','url':'https://jable.tv/videos/ssis-509/'},
        ],
    },
    {
        'name': '河北彩花',
        'slug': 'saika-kawakita',
        'avatar': 'https://assets-cdn.jable.tv/contents/models/34/s1_kawakita_saika.jpg',
        'videos': [
            {'code':'SNOS-275','title':'SNOS-275','url':'https://jable.tv/videos/snos-275/'},
            {'code':'SONE-405','title':'SONE-405','url':'https://jable.tv/videos/sone-405/'},
            {'code':'SONE-360','title':'SONE-360','url':'https://jable.tv/videos/sone-360/'},
            {'code':'SONE-311','title':'SONE-311','url':'https://jable.tv/videos/sone-311/'},
            {'code':'SONE-266','title':'SONE-266','url':'https://jable.tv/videos/sone-266/'},
            {'code':'SONE-228','title':'SONE-228','url':'https://jable.tv/videos/sone-228/'},
            {'code':'SONE-200','title':'SONE-200','url':'https://jable.tv/videos/sone-200/'},
            {'code':'SONE-153','title':'與女友最好的朋友、AV女優"川北彩香"操了一輩子的年終奇蹟','url':'https://jable.tv/videos/sone-153/'},
            {'code':'SONE-118','title':'SONE-118','url':'https://jable.tv/videos/sone-118/'},
            {'code':'SONE-071','title':'SONE-071','url':'https://jable.tv/videos/sone-071/'},
            {'code':'SONE-027','title':'SONE-027','url':'https://jable.tv/videos/sone-027/'},
            {'code':'OAE-249','title':'OAE-249','url':'https://jable.tv/videos/oae-249/'},
            {'code':'SSIS-984','title':'SSIS-984','url':'https://jable.tv/videos/ssis-984/'},
            {'code':'SSIS-951','title':'晚上在飯店和我的女老闆單獨在一起 共用房間反向NTR','url':'https://jable.tv/videos/ssis-951/'},
            {'code':'SSIS-913','title':'SSIS-913','url':'https://jable.tv/videos/ssis-913/'},
        ],
    },
    {
        'name': '楓カレン',
        'slug': 'kaede-karen',
        'avatar': 'https://assets-cdn.jable.tv/contents/models/21/s1_kaede_karen.jpg',
        'videos': [
            {'code':'IPZZ-802','title':'IPZZ-802','url':'https://jable.tv/videos/ipzz-802/'},
            {'code':'IPZZ-778','title':'IPZZ-778','url':'https://jable.tv/videos/ipzz-778/'},
            {'code':'IPZZ-703','title':'IPZZ-703','url':'https://jable.tv/videos/ipzz-703/'},
            {'code':'IPZZ-677','title':'IPZZ-677','url':'https://jable.tv/videos/ipzz-677/'},
            {'code':'IPZZ-655','title':'IPZZ-655','url':'https://jable.tv/videos/ipzz-655/'},
            {'code':'IPZZ-508','title':'IPZZ-508','url':'https://jable.tv/videos/ipzz-508/'},
            {'code':'MIDA-039','title':'MIDA-039','url':'https://jable.tv/videos/mida-039/'},
            {'code':'IPX-291','title':'IPX-291','url':'https://jable.tv/videos/ipx-291/'},
            {'code':'IPZZ-484','title':'IPZZ-484','url':'https://jable.tv/videos/ipzz-484/'},
            {'code':'IPZZ-456','title':'IPZZ-456','url':'https://jable.tv/videos/ipzz-456/'},
            {'code':'IPZZ-435','title':'IPZZ-435','url':'https://jable.tv/videos/ipzz-435/'},
            {'code':'IPZZ-415','title':'IPZZ-415','url':'https://jable.tv/videos/ipzz-415/'},
            {'code':'IPZZ-396','title':'IPZZ-396','url':'https://jable.tv/videos/ipzz-396/'},
            {'code':'IPZZ-376','title':'IPZZ-376','url':'https://jable.tv/videos/ipzz-376/'},
            {'code':'IPZZ-353','title':'IPZZ-353','url':'https://jable.tv/videos/ipzz-353/'},
        ],
    },
    {
        'name': '小宵こなん',
        'slug': 'koyoi-konan',
        'avatar': 'https://assets-cdn.jable.tv/contents/models/60/s1_koyoi_konan.jpg',
        'videos': [
            {'code':'SONE-312','title':'SONE-312','url':'https://jable.tv/videos/sone-312/'},
            {'code':'SONE-229','title':'SONE-229','url':'https://jable.tv/videos/sone-229/'},
            {'code':'SONE-267','title':'SONE-267','url':'https://jable.tv/videos/sone-267/'},
            {'code':'SONE-201','title':'SONE-201','url':'https://jable.tv/videos/sone-201/'},
            {'code':'SONE-154','title':'SONE-154','url':'https://jable.tv/videos/sone-154/'},
            {'code':'SONE-119','title':'SONE-119','url':'https://jable.tv/videos/sone-119/'},
            {'code':'SONE-072','title':'SONE-072','url':'https://jable.tv/videos/sone-072/'},
            {'code':'SONE-028','title':'SONE-028','url':'https://jable.tv/videos/sone-028/'},
            {'code':'SSIS-985','title':'SSIS-985','url':'https://jable.tv/videos/ssis-985/'},
            {'code':'SSIS-952','title':'SSIS-952','url':'https://jable.tv/videos/ssis-952/'},
            {'code':'SSIS-926','title':'SSIS-926','url':'https://jable.tv/videos/ssis-926/'},
            {'code':'SSIS-886','title':'SSIS-886','url':'https://jable.tv/videos/ssis-886/'},
            {'code':'SSIS-722','title':'SSIS-722','url':'https://jable.tv/videos/ssis-722/'},
            {'code':'SSIS-686','title':'SSIS-686','url':'https://jable.tv/videos/ssis-686/'},
            {'code':'SSIS-624','title':'SSIS-624','url':'https://jable.tv/videos/ssis-624/'},
        ],
    },
    {
        'name': '橋本ありな',
        'slug': 'arina-hashimoto',
        'avatar': 'https://assets-cdn.jable.tv/contents/models/713/s1_hashimoto_arina.jpg',
        'videos': [
            {'code':'FSDSS-437','title':'FSDSS-437','url':'https://jable.tv/videos/fsdss-437/'},
            {'code':'FSDSS-421','title':'FSDSS-421','url':'https://jable.tv/videos/fsdss-421/'},
            {'code':'FSDSS-408','title':'FSDSS-408','url':'https://jable.tv/videos/fsdss-408/'},
            {'code':'FSDSS-393','title':'FSDSS-393','url':'https://jable.tv/videos/fsdss-393/'},
            {'code':'FSDSS-376','title':'FSDSS-376','url':'https://jable.tv/videos/fsdss-376/'},
            {'code':'FSDSS-365','title':'FSDSS-365','url':'https://jable.tv/videos/fsdss-365/'},
            {'code':'FSDSS-351','title':'FSDSS-351','url':'https://jable.tv/videos/fsdss-351/'},
            {'code':'FSDSS-335','title':'FSDSS-335','url':'https://jable.tv/videos/fsdss-335/'},
            {'code':'FSDSS-320','title':'FSDSS-320','url':'https://jable.tv/videos/fsdss-320/'},
            {'code':'FSDSS-304','title':'FSDSS-304','url':'https://jable.tv/videos/fsdss-304/'},
            {'code':'FSDSS-289','title':'FSDSS-289','url':'https://jable.tv/videos/fsdss-289/'},
            {'code':'FSDSS-274','title':'FSDSS-274','url':'https://jable.tv/videos/fsdss-274/'},
            {'code':'FSDSS-259','title':'FSDSS-259','url':'https://jable.tv/videos/fsdss-259/'},
            {'code':'FSDSS-242','title':'FSDSS-242','url':'https://jable.tv/videos/fsdss-242/'},
            {'code':'FSDSS-226','title':'FSDSS-226','url':'https://jable.tv/videos/fsdss-226/'},
        ],
    },
]

# 构建统一格式
videos = []
for actress in jable_actresses:
    for v in actress['videos']:
        videos.append({
            'code': v['code'],
            'title': v['title'] if not v['title'].startswith(v['code']) else v['code'],
            'url': v['url'],
            # Jable cover: use og:image pattern. Need to scrape per-video.
            # Fallback: use the general screenshot pattern
            'cover': f'https://assets-cdn.jable.tv/contents/videos_screenshots/thumb/{v["code"].lower()}.jpg',
            'preview': '', # Jable uses iframe embed, no direct preview mp4
            'date': '',
            'actresses': [actress['name']],
            'is_multi': False,
            'tags': [],
            'is_saved': False,
            'source': 'jable',
        })

data = {
    'source': 'jable',
    'videos': videos,
    'actresses': [a['name'] for a in jable_actresses],
    'actress_avatars': {a['name']: a['avatar'] for a in jable_actresses},
    'actress_display': {a['name']: a['name'] for a in jable_actresses},
    'actress_groups': {a['name']: 'saved' for a in jable_actresses}, # all in "saved"
    'tags': [],
    'tag_counts': {},
    'video_count': len(videos),
}

out = ROOT / 'jable_data.json'
out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
print(f'Written {len(videos)} Jable videos (5 actresses x 15) to {out}')
