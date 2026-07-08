// Jable 分页抓取脚本
// 打开 https://jable.tv/latest-updates/ 后按 F12, 粘贴此脚本到 Console, 回车执行。
// 这个版本不靠滚动，而是在当前已通过 Cloudflare 的页面里 fetch 分页 HTML。

(async function scrapeJablePages() {
  const TARGET = 1500;
  const MAX_PAGES = 90;
  const WAIT_MS = 450;

  const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
  const parser = new DOMParser();
  const seen = new Set();
  const items = [];

  function pageUrl(page) {
    if (page <= 1) return 'https://jable.tv/latest-updates/';
    return `https://jable.tv/latest-updates/${page}/`;
  }

  function extractFromDocument(doc) {
    const found = [];
    doc.querySelectorAll('a[href*="/videos/"]').forEach(a => {
      const href = a.href || a.getAttribute('href') || '';
      const m = href.match(/\/videos\/([a-z0-9]+(?:-[a-z0-9]+)*)\/?(?:$|[?#])/i);
      if (!m) return;

      const code = m[1].toUpperCase();
      if (seen.has(code)) return;

      const card = a.closest('.col-6, .col-sm-4, .col-lg-3, .card, .video-img-box, .img-box, .item, div') || a;
      const img = card.querySelector('img') || a.querySelector('img');
      const cover = img ? (img.currentSrc || img.src || img.getAttribute('data-src') || img.getAttribute('data-original') || '') : '';

      let title = '';
      const titleEl = card.querySelector('h4, h3, h2, .title, .video-title, [class*="title"]');
      if (titleEl) title = titleEl.textContent.trim();
      if (!title) title = (a.getAttribute('title') || img?.getAttribute('alt') || a.textContent || '').trim();
      if (title === code) title = '';

      seen.add(code);
      found.push({
        code,
        title,
        cover,
        url: `https://jable.tv/videos/${code.toLowerCase()}/`,
        source: 'jable',
        is_multi: false
      });
    });
    return found;
  }

  function downloadJson(suffix) {
    const json = JSON.stringify({ source: 'jable', videos: items, actresses: [] }, null, 2);
    const blob = new Blob([json], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const dl = document.createElement('a');
    dl.href = url;
    dl.download = `jable_scraped_${suffix}_${items.length}.json`;
    document.body.appendChild(dl);
    dl.click();
    document.body.removeChild(dl);
    URL.revokeObjectURL(url);
  }

  console.log('Jable 分页抓取开始。请保持此标签页打开，不要刷新。');

  for (let page = 1; page <= MAX_PAGES && items.length < TARGET; page++) {
    try {
      const url = pageUrl(page);
      let doc;
      if (page === 1) {
        doc = document;
      } else {
        const res = await fetch(url, {
          credentials: 'include',
          cache: 'no-store',
          headers: { 'X-Requested-With': 'XMLHttpRequest' }
        });
        if (!res.ok) {
          console.log(`page ${page}: HTTP ${res.status}, stop`);
          break;
        }
        const html = await res.text();
        doc = parser.parseFromString(html, 'text/html');
      }

      const found = extractFromDocument(doc);
      items.push(...found);
      console.log(`page ${page}/${MAX_PAGES}: +${found.length}, total=${items.length}`);

      if (page % 10 === 0) downloadJson(`part_page${page}`);
      await sleep(WAIT_MS);
    } catch (err) {
      console.log(`page ${page}: error`, err);
      break;
    }
  }

  downloadJson('final');
  console.log(`Jable 抓取完成：${items.length} 部。文件已下载。`);
})();
