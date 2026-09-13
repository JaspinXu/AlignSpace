/* Curated Singapore discovery. Source facts stay separate from user preferences. */
(() => {
  const el = id => document.getElementById(id);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const money = n => n == null ? 'Not published' : `S$${Number(n).toLocaleString('en-SG')}`;
  let data = null, kind = 'All', savedOnly = false, expanded = false, compared = [], saved = [];
  try { const value = JSON.parse(localStorage.getItem('alignspaceSavedHomes') || '[]'); if (Array.isArray(value)) saved = [...new Set(value.filter(x => typeof x === 'string'))].slice(0,6); } catch { /* Start with an empty collection if browser storage is unavailable. */ }
  const find = id => data?.projects.find(home => home.id === id);
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
    const query = el('home-search').value.trim().toLowerCase();
    const budget = el('home-budget').value;
    let homes = data.projects.filter(home => {
      const typeMatch = kind === 'All' || (kind === 'BTO' ? home.propertyType === 'HDB' && home.condition === 'New' : kind === 'Resale' ? home.propertyType === 'HDB' && home.condition === 'Resale' : home.propertyType === kind);
      const budgetMatch = budget === 'all' || (home.cost != null && (budget === 'over' ? home.cost > 100000 : home.cost <= Number(budget)));
      return typeMatch && budgetMatch && (!savedOnly || saved.includes(home.id)) && [home.title,home.town,home.style,home.flatType,home.designer].join(' ').toLowerCase().includes(query);
    });
    if (el('home-sort').value === 'cost') homes.sort((a,b) => (a.cost ?? Infinity) - (b.cost ?? Infinity));
    if (el('home-sort').value === 'recent') homes.sort((a,b) => b.year - a.year);
    const visible = expanded ? homes : homes.slice(0,6);
    el('collection-status').textContent = `${homes.length} ${homes.length === 1 ? 'home' : 'homes'}${savedOnly ? ' in your saved collection' : ' in this edit'} · source-checked 13 Sep 2026`;
    el('home-grid').innerHTML = visible.map((home,index) => `<article class="home-card">
      <div class="home-cover"><button class="home-image-button" data-detail-home="${home.id}" type="button" aria-label="Explore ${esc(home.title)}">${imageMarkup(home)}</button><span class="property-badge ${home.propertyType.toLowerCase()}">${esc(home.flatType)}</span><button class="save-home" data-save-home="${home.id}" type="button" aria-pressed="false">♡ Save</button></div>
      <div class="home-card-body"><div class="home-eyebrow"><span>${esc(home.condition)} · ${home.year}</span><span>${home.area} m²</span></div><h3><button type="button" data-detail-home="${home.id}">${esc(home.title)} <span>↗</span></button></h3><p class="home-style">${esc(home.style)}</p><div class="home-card-bottom"><div><span>Published project cost</span><strong>${money(home.cost)}</strong></div><label class="compare-choice"><input type="checkbox" data-compare-home="${home.id}" ${compared.includes(home.id) ? 'checked' : ''}> Compare</label></div><a class="photo-credit" href="${esc(home.sourceUrl)}" target="_blank" rel="noopener noreferrer">${esc(home.designer)} · Qanvast ↗</a></div>
    </article>`).join('') || '<div class="collection-empty"><span>⌕</span><h3>A little too specific?</h3><p>Try another style, a wider budget, or explore the full collection.</p><button id="reset-home-filters" class="button primary" type="button">Reset filters</button></div>';
    el('more-homes').hidden = homes.length <= 6;
    el('more-homes').textContent = expanded ? 'Show fewer homes ↑' : 'Show the full collection ↓';
    el('reset-home-filters')?.addEventListener('click', resetFilters);
    updateSaved(); bindImageFallback(el('home-grid'));
  }
  function resetFilters() {
    kind = 'All'; savedOnly = false; expanded = false;
    el('home-search').value = ''; el('home-budget').value = 'all'; el('home-sort').value = 'featured';
    document.querySelectorAll('[data-home-type]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.homeType === kind)));
    renderHomes();
  }
  function openHome(id) {
    const home = find(id); if (!home) return;
    el('home-detail').innerHTML = `${imageMarkup(home,'eager')}<div class="detail-body"><p class="eyebrow">${esc(home.flatType)} · ${esc(home.condition)}</p><h2 id="home-dialog-title">${esc(home.title)}</h2><p>Design by ${esc(home.designer)}</p><div class="detail-stats"><div><span>Published cost</span><strong>${money(home.cost)}</strong></div><div><span>Home area</span><strong>${home.area} m²</strong></div><div><span>Completed</span><strong>${home.year}</strong></div></div><p class="source-note">Cost is for the published project scope, not this room alone. Furniture, appliances and tax inclusions are not verified. ${home.cost === null ? 'The source does not publish a renovation cost for this project.' : 'A historical example, not a current quote.'}</p><h3>Works listed in the source</h3><div class="works-tags">${home.works.map(work => `<span>${esc(work)}</span>`).join('')}</div><div class="detail-prompt"><span>MAKE IT YOURS</span><p>${esc(home.prompt)}</p><small>A conversation starter from AlignSpace.</small></div><div class="detail-actions"><button type="button" class="button ghost" data-save-home="${home.id}">♡ Save</button><button type="button" class="button primary" data-use-home="${home.id}">Start with this inspiration ↗</button></div><a class="detail-source" href="${esc(home.sourceUrl)}" target="_blank" rel="noopener noreferrer">View original project & photos on Qanvast ↗</a><p class="source-note">Photo: ${esc(home.designer)} via Qanvast · Source checked ${data.checkedAt}</p></div>`;
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
    const fields = [['Type',h=>h.flatType],['Condition',h=>h.condition],['Area',h=>`${h.area} m²`],['Published cost',h=>money(h.cost)],['Completed',h=>h.year],['Style',h=>h.style],['Listed works',h=>h.works.join(', ')]];
    el('compare-content').innerHTML = `<p class="source-note">Compare the scope as well as the price. These homes have different completion dates and specifications.</p><div class="compare-scroll" tabindex="0" role="region" aria-label="Home comparison table"><table><caption>Published project details</caption><thead><tr><th>Home</th>${homes.map(h=>`<th>${esc(h.title)}</th>`).join('')}</tr></thead><tbody>${fields.map(([label,get])=>`<tr><th scope="row">${label}</th>${homes.map(h=>`<td>${esc(get(h))}</td>`).join('')}</tr>`).join('')}<tr><th scope="row">Original source</th>${homes.map(h=>`<td><a href="${esc(h.sourceUrl)}" target="_blank" rel="noopener noreferrer">Qanvast ↗</a></td>`).join('')}</tr></tbody></table></div>`;
    el('compare-dialog').showModal();
  }
  function renderBudget() {
    if (!data) return;
    const type = el('estimate-type').value, condition = el('estimate-condition').value;
    const benchmark = data.budgets.find(b => b.type === type && b.condition === condition);
    el('estimate-buffer').disabled = !benchmark;
    if (!benchmark) {
      el('budget-result').innerHTML = '<span class="budget-year">LANDED HOMES</span><h3>Scope comes first.</h3><p>There isn’t a comparable landed-home benchmark in this collection. Explore the published case study, then ask a professional to price your specific scope.</p><a class="button primary" href="#discover" id="browse-landed">Explore the landed home ↗</a>';
      el('browse-landed').addEventListener('click', () => { kind = 'Landed'; savedOnly = false; el('home-search').value=''; el('home-budget').value='all'; document.querySelectorAll('[data-home-type]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.homeType===kind))); renderHomes(); });
      return;
    }
    const buffer = Number(el('estimate-buffer').value);
    el('budget-result').innerHTML = `<span class="budget-year">${benchmark.year} PUBLISHED GUIDE · WHOLE HOME</span><p class="budget-home">${condition === 'New' ? (type === 'Condo' ? 'New condo' : `${type} BTO`) : `${type} resale`}</p><h3>${money(benchmark.low)}<span>— ${money(benchmark.high)}</span></h3><div class="budget-scale" aria-hidden="true"><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i><i></i></div><div class="budget-summary"><span>Renovation duration<strong>${benchmark.weeks} weeks</strong></span><span>${buffer ? `With your ${buffer}% allowance` : 'Extra allowance'}<strong>${buffer ? `${money(Math.round(benchmark.low*(1+buffer/100)))}–${money(Math.round(benchmark.high*(1+buffer/100)))}` : 'Not added'}</strong></span></div><p class="source-note">${benchmark.year === 2025 ? 'Condo figures are from the 2025 guide, not updated to 2026. ' : ''}Published planning ranges, not a personalised quote. Your allowance is a simple addition to the range. Your living-room budget is set separately.</p><a href="${esc(benchmark.sourceUrl)}" target="_blank" rel="noopener noreferrer">Qanvast ${benchmark.year} guide · ${benchmark.sourceDate} ↗</a>`;
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
    kind = button.dataset.homeType; expanded = false;
    document.querySelectorAll('[data-home-type]').forEach(b => b.setAttribute('aria-pressed', String(b === button))); renderHomes();
  }));
  el('home-search').addEventListener('input', renderHomes);
  ['home-budget','home-sort'].forEach(id => el(id).addEventListener('change',renderHomes));
  el('saved-filter').addEventListener('click', () => { savedOnly = !savedOnly; renderHomes(); });
  el('more-homes').addEventListener('click', () => { expanded = !expanded; renderHomes(); });
  el('compare-clear').addEventListener('click', () => { compared = []; updateComparison(); renderHomes(); });
  el('compare-open').addEventListener('click', openComparison);
  document.querySelectorAll('.dialog-close').forEach(b => b.addEventListener('click', () => b.closest('dialog').close()));
  ['estimate-type','estimate-condition','estimate-buffer'].forEach(id => el(id).addEventListener('change',renderBudget));
  async function load() {
    try {
      const response = await fetch('/assets/singapore.json');
      if (!response.ok) throw new Error('Collection unavailable');
      data = await response.json(); saved = saved.filter(id=>find(id)); persist();
      renderHomes(); renderBudget();
    } catch {
      el('collection-status').textContent = 'The collection couldn’t load. You can still start a room brief below.';
      el('home-grid').innerHTML = '<button class="button ghost" id="retry-collection" type="button">Retry collection</button>';
      el('retry-collection').addEventListener('click', load);
      el('budget-result').textContent = 'Budget references are temporarily unavailable.';
    }
  }
  window.AlignDiscovery = {selectedIds: () => data ? [...saved] : []};
  load();
})();
