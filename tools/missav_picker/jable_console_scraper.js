// Jable 分页 + 详情抓取脚本
// 打开 https://jable.tv/latest-updates/ 后按 F12, 粘贴此脚本到 Console, 回车执行。
// 它会在当前已通过 Cloudflare 的浏览器会话里：
// 1) 分页抓列表页
// 2) 再进入每个详情页提取女优 / 标签 / 日期
// 3) 导出完整 JSON

(async function scrapeJablePages() {
  const TARGET = 1500;
  const MAX_PAGES = 90;
  const WAIT_MS = 450;
  const DETAIL_WAIT_MS = 300;

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
        is_multi: false,
        actresses: [],
        tags: [],
        date: '',
        preview: ''
      });
    });
    return found;
  }

  async function enrichItem(item) {
    try {
      const res = await fetch(item.url, { credentials: 'include', cache: 'no-store' });
      if (!res.ok) return item;
      const html = await res.text();
      const doc = parser.parseFromString(html, 'text/html');

      const actors = new Set();
      const tags = new Set();
      let date = '';
      let preview = item.preview || '';

      // 常见 Jable 详情结构
      doc.querySelectorAll('a[href*="/models/"], a[href*="/star/"]').forEach(a => {
        const t = (a.textContent || '').trim();
        if (t) actors.add(t);
      });
      doc.querySelectorAll('a[href*="/categories/"], a[href*="/tags/"]').forEach(a => {
        const t = (a.textContent || '').trim();
        if (t) tags.add(t);
      });

      const text = doc.body ? doc.body.innerText : '';
      const dateMatch = text.match(/(\d{4}-\d{2}-\d{2})/);
      if (dateMatch) date = dateMatch[1];

      const video = doc.querySelector('video source, video');
      const videoSrc = video ? (video.getAttribute('src') || video.getAttribute('data-src') || '') : '';
      if (videoSrc && /play\//i.test(videoSrc)) preview = videoSrc;

      item.actresses = [...actors];
      item.tags = [...tags];
      item.date = date;
      item.preview = preview;
      item.is_multi = item.actresses.length > 1;

      const titleMeta = doc.querySelector('meta[property="og:title"]')?.content || '';
      if (titleMeta && titleMeta.trim()) item.title = titleMeta.trim();

      const coverMeta = doc.querySelector('meta[property="og:image"]')?.content || '';
      if (coverMeta) item.cover = coverMeta;
    } catch (err) {
      console.log('detail error', item.code, err);
    }
    return item;
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

  console.log(`开始抓详情页元数据，共 ${items.length} 部...`);
  for (let i = 0; i < items.length; i++) {
    await enrichItem(items[i]);
    if ((i + 1) % 20 === 0) {
      console.log(`detail ${i + 1}/${items.length}`);
      downloadJson(`detail_${i + 1}`);
    }
    await sleep(DETAIL_WAIT_MS);
  }

  downloadJson('final');
  console.log(`Jable 抓取完成：${items.length} 部（含女优/标签/日期）。文件已下载。`);
})();
