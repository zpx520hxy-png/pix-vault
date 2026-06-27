import re
html = open('index_template.html', encoding='utf-8').read()

# Fix: <img p(xxx}" → <img src="${xxx}"
html = re.sub(r'<img p\(([^}]+)}"', r'<img src="$\1}"', html)
html = re.sub(r'<video p\(([^}]+)}"', r'<video src="$\1}"', html)

# Fix: poster="${p(v.cover)}" → poster="${v.cover}"
html = html.replace('poster="${p(v.cover)}"', 'poster="${v.cover}"')

# Fix: p(p( → p( (double wrap)
html = re.sub(r'p\(p\(', 'p(', html)

# Remove mutation observer (already done)
# Remove IMG_PROXY (set to '' to disable proxy)
html = html.replace("const IMG_PROXY = location.protocol==='file:'?'':'/img/';", "const IMG_PROXY = '';")

# Verify
lines_with_img = [l.strip() for l in html.split('\n') if ('<img' in l or '<video' in l) and 'p(' in l]
if lines_with_img:
    print(f'WARNING: {len(lines_with_img)} lines still have p():')
    for l in lines_with_img[:5]:
        print(f'  {l[:80]}')
else:
    print('All img/video p() calls cleaned up')

open('index_template.html', 'w', encoding='utf-8').write(html)
print('Saved index_template.html')
