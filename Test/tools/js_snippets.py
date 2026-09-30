# -*- coding: utf-8 -*-
"""
浏览器端 JS 脚本片段

【来源】从原 17_测试/web/js.py 迁移。

这些脚本在页面上下文执行，用于批量采集元素信息。
比用 Playwright 的 locator 逐个查快得多 —— 一次 evaluate 拿回全部数据。
"""

COLLECT_LINKS = """
() => {
  const out = [];
  document.querySelectorAll('a[href]').forEach(a => {
    const href = a.getAttribute('href') || '';
    if (!href || href.startsWith('javascript:') || href.startsWith('#')
        || href.startsWith('mailto:') || href.startsWith('tel:')) return;
    out.push({href: a.href, text: (a.innerText || '').trim().slice(0, 60),
              visible: !!(a.offsetWidth || a.offsetHeight)});
  });
  return out;
}
"""

COLLECT_FORMS = """
() => {
  const forms = [];
  const seen = new Set();
  const pick = (el, idx) => {
    const fields = [];
    el.querySelectorAll('input, select, textarea').forEach(f => {
      const type = (f.getAttribute('type') || f.tagName).toLowerCase();
      if (['hidden','submit','button','image','reset'].includes(type)) return;
      fields.push({
        name: f.name || f.id || '', type: type,
        selector: f.id ? ('#' + CSS.escape(f.id))
                       : (f.name ? ('[name="' + f.name + '"]') : ''),
        required: f.required || f.getAttribute('aria-required') === 'true',
        maxlength: f.maxLength > 0 ? f.maxLength : null,
        placeholder: f.placeholder || '',
        label: (f.labels && f.labels[0]
                ? f.labels[0].innerText.trim().slice(0,30) : '')
      });
    });
    if (!fields.length) return null;
    const submit = el.querySelector('[type=submit], button:not([type=button])');
    return {
      name: el.getAttribute('name') || el.getAttribute('id') || ('form' + idx),
      selector: el.id ? ('#' + CSS.escape(el.id))
                      : ('form:nth-of-type(' + (idx+1) + ')'),
      action: el.getAttribute('action') || '',
      method: (el.getAttribute('method') || 'GET').toUpperCase(),
      fields: fields,
      submit_selector: submit
        ? (submit.id ? '#' + CSS.escape(submit.id)
                     : (submit.tagName.toLowerCase()
                        + (submit.type ? '[type=' + submit.type + ']' : '')))
        : ''
    };
  };
  document.querySelectorAll('form').forEach((el, i) => {
    const f = pick(el, i);
    if (f && !seen.has(f.selector)) { seen.add(f.selector); forms.push(f); }
  });
  return forms;
}
"""

PERF_TIMING = """
() => {
  const nav = performance.getEntriesByType('navigation')[0];
  if (nav) {
    return {
      load_ms: Math.round(nav.loadEventEnd - nav.startTime),
      dom_ms: Math.round(nav.domContentLoadedEventEnd - nav.startTime),
      ttfb_ms: Math.round(nav.responseStart - nav.startTime),
      transfer_kb: Math.round((nav.transferSize || 0) / 1024)
    };
  }
  return {load_ms: 0, dom_ms: 0, ttfb_ms: 0, transfer_kb: 0};
}
"""

PAGE_TEXT = "() => document.body ? document.body.innerText : ''"
