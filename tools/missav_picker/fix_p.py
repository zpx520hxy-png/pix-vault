html = open('index_template.html', encoding='utf-8').read()

# Add p() calls for all cover/preview URLs
html = html.replace('src="${v.cover}"', 'src="${p(v.cover)}"')
html = html.replace('poster="${v.cover}"', 'poster="${p(v.cover)}"')

# Fix the double p() from earlier broken edit
html = html.replace('src="${p(p(v.cover))}"', 'src="${p(v.cover)}"')

# Already has p() for avatars in sel-bar
# Don't fix the actress avatar (already uses +p(av)+)

open('index_template.html', 'w', encoding='utf-8').write(html)
print('Fixed p() calls in template')

# Verify
for line in open('index_template.html', encoding='utf-8'):
    if 'cover' in line and '${v.' in line and 'p(v.' not in line:
        print(f'  MISSING p(): {line.strip()[:80]}')
