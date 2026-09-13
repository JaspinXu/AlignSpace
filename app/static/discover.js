/* Curated Singapore discovery. Source facts stay separate from user preferences. */
(() => {
  const el = id => document.getElementById(id);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const area = h => h.area ? `${h.area} m²` : 'Area not listed';
  let data = null, kind = 'All', savedOnly = false, visibleCount = 12, compared = [], saved = [];
  try { const value = JSON.parse(localStorage.getItem('alignspaceSavedHomes') || '[]'); if (Array.isArray(value)) saved = [...new Set(value.filter(x => typeof x === 'string'))].slice(0,6); } catch { /* Start with an empty collection if browser storage is unavailable. */ }
  let live = null, searchVersion = 0, controller = null;
  const find = id => data?.projects.find(home => home.id === id);
  const merge = homes => { const map = new Map(data.projects.map(h => [h.id, h])); homes.forEach(h => map.set(h.id, h)); data.projects = [...map.values()]; };
  function cancelSearch() { searchVersion++; controller?.abort(); live = null; visibleCount = 12; el('search-source').disabled = false; el('search-source').textContent = 'Search more homes ↗'; el('source-search-status').hidden = true; }
  const toast = text => { el('discovery-toast').textContent = text; el('discovery-toast').hidden = false; clearTimeout(toast.timer); toast.timer = setTimeout(() => el('discovery-toast').hidden = true, 4000); };
  function persist() {
    try { localStorage.setItem('alignspaceSavedHomes', JSON.stringify(saved)); } catch { toast('Saved for this visit. Browser storage is unavailable.'); }
  }
  function updateSaved() {
    el('saved-count').textContent = saved.length;
    el('import-count').textContent = saved.length;
    el('inspiration-import').hidden = !saved.length;
    el('saved-filter').setAttribute('aria-pressed', String(savedOnly));
    document.querySelectorAll('[data-save-home]').forEach(button => {
      const active = saved.includes(button.dataset.saveHome);
      button.setAttribute('aria-pressed', String(active));
      button.textContent = active ? '♥ Saved' : '♡ Save';
      button.setAttribute('aria-label', `${active ? 'Unsave' : 'Save'} ${find(button.dataset.saveHome)?.title || 'home'}`);
    });
  }
  function toggleSave(id) {
    if (!find(id)) return;
    if (saved.includes(id)) saved = saved.filter(item => item !== id);
    else {
      if (saved.length >= 6) { toast('Keep up to 6 homes in your collection. Unsave one to make room.'); return; }
      saved.push(id);
    }
    persist(); updateSaved();
    if (savedOnly) renderHomes();
  }
  function imageMarkup(home, loading = 'lazy') {
    return `<div class="home-photo"><span class="photo-fallback" aria-hidden="true">${esc(home.title)}<small>View photography at the source ↗</small></span><img src="${esc(home.imageUrl)}" alt="${esc(home.title)} by ${esc(home.designer)}, via Qanvast" loading="${loading}" referrerpolicy="no-referrer"></div>`;
  }
  function bindImageFallback(root) {
    root.querySelectorAll('img').forEach(img => img.addEventListener('error', () => { img.hidden = true; }, {once:true}));
  }
  function renderHomes() {
    if (!data) return;
    const query = el('home-search').value.trim().toLowerCase(), style = el('home-style').value;
    let homes = savedOnly ? saved.map(find).filter(Boolean) : live ? live.projects : data.projects;
    if (!live && !savedOnly) homes = homes.filter(h => (kind === 'All' || h.propertyType === kind) && (style === 'All' || h.style.toLowerCase().includes(style.toLowerCase())) && query.split(/\s+/).every(word => [h.title,h.town,h.style,h.flatType,h.designer,h.features.join(' '),h.styleCue].join(' ').toLowerCase().includes(word)));
    const visible = homes.slice(0,visibleCount);
    el('collection-status').textContent = `${homes.length} ${homes.length === 1 ? 'preview' : 'previews'}${savedOnly ? ' in your collection' : live ? ' from your search' : ' to explore'} · ${visible.length} shown`;
    el('home-grid').innerHTML = visible.map(home => `<article class="home-card">
      <div class="home-cover"><button class="home-image-button" data-detail-home="${esc(home.id)}" type="button" aria-label="Explore ${esc(home.title)}">${imageMarkup(home)}</button><span class="property-badge ${esc(home.propertyType.toLowerCase())}">${esc(home.flatType)}</span><button class="save-home" data-save-home="${esc(home.id)}" type="button" aria-pressed="false">♡ Save</button></div>
      <div class="home-card-body"><p class="home-style">${esc(home.style)}</p><h3><button type="button" data-detail-home="${esc(home.id)}">${esc(home.title)} <span>↗</span></button></h3><p class="home-cue">${esc(home.styleCue)}</p><div class="preview-tags" aria-label="Source image tags">${home.features.slice(0,3).map(tag => `<span>${esc(tag)}</span>`).join('')}</div><div class="home-card-bottom"><span>${esc(home.propertyType)} · ${esc(area(home))}</span><label class="compare-choice"><input type="checkbox" data-compare-home="${esc(home.id)}" ${compared.includes(home.id) ? 'checked' : ''}> Compare</label></div><a class="photo-credit" href="${esc(home.sourceUrl)}" target="_blank" rel="noopener noreferrer">${esc(home.designer)} · Qanvast ↗</a></div>
    </article>`).join('') || '<div class="collection-empty"><span>⌕</span><h3>Keep exploring.</h3><p>Try Search more homes to look beyond this collection, or change the style and words.</p><button id="reset-home-filters" class="button ghost" type="button">Reset filters</button></div>';
    el('more-homes').hidden = homes.length <= visibleCount;
    el('more-homes').textContent = `Show ${Math.min(12,homes.length-visibleCount)} more homes ↓`;
    el('reset-home-filters')?.addEventListener('click', resetFilters);
    updateSaved(); bindImageFallback(el('home-grid'));
  }
  function resetFilters() {
    cancelSearch(); kind = 'All'; savedOnly = false;
    el('home-search').value = ''; el('home-style').value = 'All';
    document.querySelectorAll('[data-home-type]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.homeType === kind)));
    renderHomes();
  }
  async function searchSource(event) {
    event.preventDefault();
    controller?.abort(); controller = new AbortController();
    const version = ++searchVersion;
    savedOnly = false; visibleCount = 12;
    el('search-source').disabled = true; el('search-source').textContent = 'Finding inspiration…';
    el('source-search-status').hidden = false; el('source-search-message').textContent = 'Searching the source collection…'; el('source-search-link').hidden = true;
    try {
      const query = new URLSearchParams({q:el('home-search').value.trim(),style:el('home-style').value,kind});
      const response = await fetch('/api/inspiration/search?' + query, {signal:controller.signal});
      if (!response.ok) throw new Error('Source search unavailable');
      const result = await response.json();
      if (version !== searchVersion) return;
      live = result; merge(result.projects);
      el('source-search-message').textContent = result.message + (result.sourceTotal != null ? ` ${result.sourceTotal.toLocaleString()} results at Qanvast.` : '');
      el('source-search-link').href = result.sourceUrl; el('source-search-link').hidden = false;
      renderHomes();
    } catch (error) {
      if (version !== searchVersion || error.name === 'AbortError') return;
      el('source-search-message').textContent = 'Search is temporarily unavailable. Your current collection is still here; try again shortly.';
    } finally {
      if (version === searchVersion) { el('search-source').disabled = false; el('search-source').textContent = 'Search more homes ↗'; }
    }
  }
  function openHome(id) {
    const home = find(id); if (!home) return;
    el('home-detail').innerHTML = `${imageMarkup(home,'eager')}<div class="detail-body"><p class="eyebrow">${esc(home.style)}</p><h2 id="home-dialog-title">${esc(home.title)}</h2><p>Design by ${esc(home.designer)} · Qanvast</p><div class="style-reading"><h3>What to notice</h3><p>${esc(home.styleCue)}</p><small>A style observation prompt from AlignSpace; decide what applies to this image.</small></div><h3>Source image tags</h3><div class="works-tags">${home.features.map(tag => `<span>${esc(tag)}</span>`).join('') || '<span>No image tags supplied</span>'}</div><div class="detail-stats"><div><span>Home type</span><strong>${esc(home.flatType)}</strong></div><div><span>Home area</span><strong>${esc(area(home))}</strong></div><div><span>Completed</span><strong>${esc(home.year || 'Not listed')}</strong></div></div>${home.rooms.length ? `<h3>Spaces photographed</h3><div class="works-tags">${home.rooms.map(room => `<span>${esc(room)}</span>`).join('')}</div>` : ''}<div class="detail-prompt"><span>MAKE IT YOURS</span><p>${esc(home.prompt)}</p></div><div class="detail-actions"><button type="button" class="button ghost" data-save-home="${esc(home.id)}">♡ Save</button><button type="button" class="button primary" data-use-home="${esc(home.id)}">Start with this inspiration ↗</button></div><a class="detail-source" href="${esc(home.sourceUrl)}" target="_blank" rel="noopener noreferrer">View original project & photos on Qanvast ↗</a><p class="source-note">Photo: ${esc(home.designer)} via Qanvast · Preview checked ${esc(home.checkedAt)}</p></div>`;
    bindImageFallback(el('home-detail')); updateSaved(); el('home-dialog').showModal();
  }
  function updateComparison() {
    el('compare-tray').hidden = !compared.length;
    el('compare-label').textContent = `${compared.length}/3 homes selected`;
    el('compare-open').disabled = compared.length < 2;
  }
  function openComparison() {
    if (compared.length < 2) return;
    const homes = compared.map(find).filter(Boolean);
    const fields = [['Style',h=>h.style],['What to notice',h=>h.styleCue],['Source image tags',h=>h.features.join(', ')],['Spaces photographed',h=>h.rooms.join(', ') || 'Not listed'],['Home type',h=>h.flatType],['Area',area]];
    el('compare-content').innerHTML = `<p class="source-note">Which details do you want to combine? Use the images to explain your own preferences.</p><div class="compare-scroll" tabindex="0" role="region" aria-label="Home comparison table"><table><caption>Compare your design references</caption><thead><tr><th>Home</th>${homes.map(h=>`<th>${imageMarkup(h)}${esc(h.title)}</th>`).join('')}</tr></thead><tbody>${fields.map(([label,get])=>`<tr><th scope="row">${label}</th>${homes.map(h=>`<td>${esc(get(h))}</td>`).join('')}</tr>`).join('')}<tr><th scope="row">Original source</th>${homes.map(h=>`<td><a href="${esc(h.sourceUrl)}" target="_blank" rel="noopener noreferrer">${esc(h.designer)} · Qanvast ↗</a></td>`).join('')}</tr></tbody></table></div>`;
    bindImageFallback(el('compare-content'));
    el('compare-dialog').showModal();
  }
  document.addEventListener('click', event => {
    const save = event.target.closest('[data-save-home]'); if (save) toggleSave(save.dataset.saveHome);
    const detail = event.target.closest('[data-detail-home]'); if (detail) openHome(detail.dataset.detailHome);
    const use = event.target.closest('[data-use-home]');
    if (use) {
      const home = find(use.dataset.useHome);
      if (!saved.includes(home.id)) {
        if (saved.length >= 6) { toast('Unsave a home first; your collection holds up to 6.'); return; }
        saved.push(home.id); persist(); updateSaved();
      }
      const housing = home.propertyType === 'Condo' ? 'Condo / EC' : home.propertyType === 'Landed' ? 'Landed' : `HDB ${home.flatType.slice(0,6)}`;
      document.querySelector('#project-form [name="housingType"]').value = housing;
      el('home-dialog').close(); el('start-project').scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'});
    }
  });
  el('home-grid').addEventListener('change', event => {
    const box = event.target.closest('[data-compare-home]'); if (!box) return;
    if (box.checked && compared.length >= 3) { box.checked = false; toast('Compare up to 3 homes at a time.'); return; }
    compared = box.checked ? [...compared,box.dataset.compareHome] : compared.filter(id=>id!==box.dataset.compareHome); updateComparison();
  });
  document.querySelectorAll('[data-home-type]').forEach(button => button.addEventListener('click', () => {
    cancelSearch(); kind = button.dataset.homeType; savedOnly = false;
    document.querySelectorAll('[data-home-type]').forEach(b => b.setAttribute('aria-pressed', String(b === button))); renderHomes();
  }));
  el('home-search').addEventListener('input', () => { cancelSearch(); renderHomes(); });
  el('home-style').addEventListener('change', () => { cancelSearch(); renderHomes(); });
  el('home-search-form').addEventListener('submit', searchSource);
  el('saved-filter').addEventListener('click', () => { savedOnly = !savedOnly; cancelSearch(); renderHomes(); });
  el('more-homes').addEventListener('click', () => { visibleCount += 12; renderHomes(); });
  el('compare-clear').addEventListener('click', () => { compared = []; updateComparison(); renderHomes(); });
  el('compare-open').addEventListener('click', openComparison);
  document.querySelectorAll('.dialog-close').forEach(b => b.addEventListener('click', () => b.closest('dialog').close()));
  async function load() {
    try {
      const response = await fetch('/assets/singapore.json');
      if (!response.ok) throw new Error('Collection unavailable');
      data = await response.json();
      if (saved.length) {
        const resolved = await fetch('/api/inspiration/resolve', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ids:saved})});
        if (resolved.ok) merge((await resolved.json()).projects);
      }
      saved = saved.filter(id=>find(id)); persist(); renderHomes();
    } catch {
      el('collection-status').textContent = 'The collection couldn’t load. You can still start a room brief below.';
      el('home-grid').innerHTML = '<button class="button ghost" id="retry-collection" type="button">Retry collection</button>';
      el('retry-collection').addEventListener('click', load);
    }
  }
  window.AlignDiscovery = {selectedIds: () => data ? [...saved] : []};
  load();
})();
