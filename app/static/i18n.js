/* Local presentation translation. Source identifiers and user input stay unchanged.
   WeakMaps remember original text; rerenders and language changes share one path. */
(() => {
  let language = localStorage.getItem('alignspaceLanguage') || 'en';
  const originals = new WeakMap(), attributes = new WeakMap();
  const dictionary = window.AlignLocale || {};
  const entries = Object.entries(dictionary).sort((a,b) => b[0].length-a[0].length);
  const matcher = new RegExp('(?<![A-Za-z])(?:' + entries.map(([en]) => en.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|') + ')(?![A-Za-z])', 'g');
  function searchQuery(text) {
    if (!/[\u4e00-\u9fff]/.test(text)) return text.trim();
    for (const [zh,en] of Object.entries(window.AlignSearchAliases).sort((a,b)=>b[0].length-a[0].length)) text = text.replaceAll(zh, ' '+en+' ');
    return text.replace(/我想要|我喜欢|我想找|我想看|帮我找|请搜索|搜索|看看|想要|喜欢|风格|的|和|与/g,' ').trim().replace(/\s+/g,' ');
  }
  function t(text) {
    if (language !== 'zh') return text;
    const trimmed = String(text).trim();
    if (dictionary[trimmed]) return String(text).replace(trimmed, dictionary[trimmed]);
    // Composed system labels may contain counts, dates, roles and other dynamic values.
    let result = String(text);
    result = result.replace(matcher, match => dictionary[match]);
    return result;
  }
  function apply(root = document.body) {
    observer.disconnect();
    root.querySelectorAll?.('option:not([value])').forEach(option => option.value = option.textContent);
    const walk = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    for (let node = walk.nextNode(); node; node = walk.nextNode()) {
      const parent = node.parentElement;
      if (!parent || parent.closest('script,style,textarea,code,[translate="no"]')) continue;
      const explicit = parent.closest('[data-en][data-zh]');
      let record = originals.get(node);
      if (!record || node.nodeValue !== record.shown) record = {en: node.nodeValue};
      record.shown = explicit ? explicit.dataset[language === 'zh' ? 'zh' : 'en'] : t(record.en);
      if (node.nodeValue !== record.shown) node.nodeValue = record.shown;
      originals.set(node, record);
    }
    root.querySelectorAll?.('[placeholder],[aria-label],[title],meta[name="description"]').forEach(el => {
      if (el.closest('[translate="no"]')) return;
      const saved = attributes.get(el) || {};
      for (const key of ['placeholder','aria-label','title','content']) {
        if (!el.hasAttribute(key)) continue;
        if (!saved[key] || el.getAttribute(key) !== saved[key].shown) saved[key] = {en:el.getAttribute(key)};
        saved[key].shown = t(saved[key].en); el.setAttribute(key,saved[key].shown);
      }
      attributes.set(el,saved);
    });
    document.documentElement.lang = language === 'zh' ? 'zh-CN' : 'en';
    document.title = t('AlignSpace · Design alignment workspace');
    const toggle = document.getElementById('language-toggle');
    if (toggle) { toggle.textContent = language === 'zh' ? 'English' : '中文'; toggle.setAttribute('aria-pressed',String(language === 'zh')); }
    observer.observe(document.body, {childList:true,subtree:true,characterData:true,attributes:true,attributeFilter:['placeholder','aria-label','title']});
  }
  const observer = new MutationObserver(() => apply());
  window.I18n = {t, searchQuery, get language() {return language;}, apply};
  document.getElementById('language-toggle').addEventListener('click', () => {
    language = language === 'zh' ? 'en' : 'zh';
    localStorage.setItem('alignspaceLanguage', language);
    const name = document.querySelector('#project-form [name="name"]');
    if (['My living room','我的客厅'].includes(name.value)) name.value = language === 'zh' ? '我的客厅' : 'My living room';
    apply();
  });
  const initialName = document.querySelector('#project-form [name="name"]');
  if (language === 'zh' && initialName.value === 'My living room') initialName.value = '我的客厅';
  apply();
})();
