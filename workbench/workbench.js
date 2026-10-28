/* The UI edits drafts; only the local Python API can generate or verify files. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const clone = value => JSON.parse(JSON.stringify(value));
  const signature = value => JSON.stringify(value);
  const lines = value => String(value).split(/\r?\n/).map(x => x.trim()).filter(Boolean);
  const types = { text: '文本', number: '数值', choice: '单选', tags: '标签' };
  const levels = { browser: '浏览器实测', manual: '人工检查', content: '内容核对', static: '静态核对' };
  const decisions = { pending: '待决 · 未确认', proposed: '提议 · 待确认', declared: '已声明决定', conflict: '存在冲突' };
  const feedbackStatuses = { pending: '待决', adopted: '采纳', declined: '不采纳', conflict: '冲突' };
  const kinds = { build: '生成', preparation: '变化准备', review: '修订核对', delivery: '交接', observations: '观察记录' };
  const statusMeanings = {
    GENERATED_NOT_ACCEPTED: '文件已经生成，尚未完成验收。',
    CONSISTENT: '当前产物和绑定的材料一致；业务确认与观察真实性仍由使用者负责。',
    HOLD: '存在待补、未决或证据缺口。可下载当前真实文件继续处理。',
    ERROR: '实际运行未完成，请按错误信息修正后重试。',
    PREPARED: '变化已准备，请逐条记录反馈处理。',
    DECLARED_CHANGE_COVERED: '给定的变更与反馈关系已覆盖，仍不认证实际执行或完整业务批准。',
    SUPPLIED_EVIDENCE_COVERED: '本版给定观察满足对应检查，仍不认证执行真实性或完整业务批准；修订 HOLD 仍以实际交接核对结果为准。'
  };
  const blankDraft = () => ({
    kind: 'collection', title: '', audience: '', problem: '', positioning: '', value_hypothesis: '', goal: '', priority_basis: '',
    source_kind: 'user-supplied', source_note: '', success_metric: { statement: '', baseline: '', target: '', measurement: '' },
    included: [], excluded: [], pending: [], decision_status: 'pending', fields: [],
    collection: { search_fields: [], filters: [], layout: 'sidebar', items: [] },
    form: { initial_values: {}, initial_state: 'draft' },
    requirement: { statement: '', priority: 'must', checks: [{ condition: '', expected: '', evidence_level: 'browser' }] },
    rule: { statement: '', default: '', exception: '', boundary: '' }, legacy_notes: []
  });
  const state = {
    stage: 'create', draft: blankDraft(), project: null, projects: [], csrf: '', online: false, busy: false,
    saved: '', draftTick: 0, resultId: '', baseId: '', buildId: '', preparationId: '',
    version: '1.0', nextVersion: '1.1', feedback: [], feedbackDirty: false,
    observationEdits: {}, observationDirty: false, conflict: false
  };
  let uniqueCounter = 0;
  const uid = prefix => prefix + '_' + Date.now().toString(36) + '_' + (++uniqueCounter);
  const dirty = () => state.saved !== signature(state.draft);
  const runs = () => state.project?.runs || [];
  const builds = () => runs().filter(r => r.kind === 'build');
  const findRun = id => runs().find(r => r.id === id);
  const currentBuild = () => findRun(state.buildId || state.project?.latest_build_run_id);
  const currentPreparation = () => findRun(state.preparationId);
  const actionable = () => state.online && !state.busy;
  const currentEvidence = run => !!run?.current_source && !dirty() && run.id === state.project?.latest_build_run_id;

  function el(tag, attrs = {}, children = []) {
    const item = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs)) {
      if (value === undefined || value === null) continue;
      if (key === 'text') item.textContent = String(value);
      else if (key === 'class') item.className = value;
      else if (key === 'value') item.value = value;
      else if (['checked', 'disabled', 'hidden', 'readOnly', 'open'].includes(key)) item[key] = !!value;
      else if (key.startsWith('on')) item.addEventListener(key.slice(2), value);
      else item.setAttribute(key, value);
    }
    for (const child of Array.isArray(children) ? children : [children]) {
      if (child !== null && child !== undefined) item.append(typeof child === 'string' ? document.createTextNode(child) : child);
    }
    return item;
  }
  const button = (text, click, className = 'button', attrs = {}) => el('button', { type: 'button', class: className, text, onclick: click, ...attrs });
  const optionList = (map, selected) => Object.entries(map).map(([value, label]) => el('option', { value, text: label, selected: value === selected ? '' : null }));
  function select(id, value, map, update, disabled = false) {
    const node = el('select', { id, disabled }, optionList(map, value));
    node.value = value;
    node.addEventListener('change', () => update(node.value));
    return node;
  }
  function field(label, id, value, update, opts = {}) {
    const node = opts.options ? select(id, value, opts.options, update, opts.disabled) : el(opts.multiline ? 'textarea' : 'input', {
      id, value: value ?? '', type: opts.type || 'text', maxlength: opts.maxlength || 1000, rows: opts.multiline ? '3' : null,
      placeholder: opts.placeholder, disabled: opts.disabled, min: opts.min, max: opts.max,
      oninput: event => update(opts.type === 'number' ? (event.target.value === '' ? null : Number(event.target.value)) : event.target.value)
    });
    const wrapper = el('div', { class: 'field-group' + (opts.wide ? ' wide' : '') }, [el('label', { for: id, text: label }), node]);
    if (opts.hint) wrapper.append(el('p', { class: 'field-hint', text: opts.hint }));
    return wrapper;
  }
  function draftField(label, id, key, opts = {}) {
    return field(label, id, state.draft[key], value => { state.draft[key] = value; changed(); }, opts);
  }
  function listField(label, id, key, opts = {}) {
    return field(label, id, state.draft[key].join('\n'), value => { state.draft[key] = lines(value); changed(); }, { multiline: true, hint: '每行一项；未确定的内容请写入待补 / 未决。', ...opts });
  }
  function section(title, description, index, children) {
    return el('section', { class: 'editor-section' }, [el('div', { class: 'section-title' }, [el('div', {}, [el('h2', { text: title }), el('p', { text: description })]), el('span', { class: 'section-index', text: index })]), ...children]);
  }
  function advanced(title, children, open = false) {
    return el('details', { class: 'advanced', open }, [el('summary', { text: title }), ...children]);
  }
  const grid = children => el('div', { class: 'form-grid' }, children);
  function notify(message, warning = false) {
    $('notice').textContent = message;
    $('notice').className = 'notice' + (warning ? ' warning' : '');
    $('notice').hidden = !message;
  }
  function error(message) {
    $('validation-errors').textContent = message;
    $('validation-errors').hidden = !message;
  }
  function changed() {
    state.draftTick++;
    error('');
    if (state.preparationId) notify('当前草案已改变；已准备的反馈路径已陈旧。当前输入保留，请重新准备变化并重新核对关联。', true);
    updateSummary();
    if ($('build-first')) $('build-first').disabled = !actionable() || !state.project || dirty();
    if ($('run-review')) $('run-review').disabled = !actionable() || preparationStale();
    // Evidence state changes immediately even when the handoff panel is not active.
    if (state.stage === 'handoff') renderStage();
  }
  function feedbackChanged() { state.feedbackDirty = true; error(''); updateSummary(); }
  function observationChanged() { state.observationDirty = true; error(''); updateSummary(); }
  function safeUrl(raw) {
    const url = new URL(raw, location.href);
    if (url.origin !== location.origin || !['http:', 'https:'].includes(url.protocol) || !url.pathname.startsWith('/api/projects/')) throw new Error('服务返回了不受支持的文件地址。');
    return url;
  }
  async function api(path, payload) {
    let response;
    try {
      response = await fetch(path, {
        method: payload === undefined ? 'GET' : 'POST', credentials: 'same-origin', cache: 'no-store',
        headers: payload === undefined ? { Accept: 'application/json' } : { Accept: 'application/json', 'Content-Type': 'application/json', 'X-Workbench-Token': state.csrf },
        body: payload === undefined ? undefined : JSON.stringify(payload)
      });
    } catch (_) {
      state.online = false; state.csrf = ''; updateConnection();
      throw new Error('需启动本地服务。当前输入仍在页面中，连接恢复前无法保存或生成。');
    }
    let data;
    try { data = await response.json(); } catch (_) { throw new Error('本地服务未返回有效数据，请检查服务是否正确启动。'); }
    if (!response.ok || data.ok !== true) {
      const failure = new Error(data.error?.message || '操作未完成，当前输入已保留。');
      failure.code = data.error?.code; failure.fields = data.error?.fields; failure.status = response.status;
      if (response.status === 409) state.conflict = true;
      throw failure;
    }
    return data;
  }
  function showFailure(failure) {
    const details = Array.isArray(failure.fields) && failure.fields.length ? '\n需要检查：' + failure.fields.join('、') : '';
    const conflictText = failure.status === 409 ? '\n当前编辑与处理记录均已保留，未覆盖服务器材料。请刷新项目状态或重新准备变化后再提交。' : '';
    error((failure.code ? failure.code + '：' : '') + failure.message + details + conflictText);
  }
  function updateConnection() {
    $('connection-status').textContent = state.online ? '真实本地连接' : '需启动本地服务';
    $('connection-status').className = 'connection' + (state.online ? '' : ' offline');
    $('service-notice').hidden = state.online;
    $('save-draft').disabled = !actionable();
    $('refresh-projects').disabled = !actionable();
    $('project-select').disabled = !actionable();
    ['new-project', 'load-sample', 'import-json'].forEach(id => $(id).disabled = state.busy);
  }
  async function connect() {
    try {
      const data = await api('/api/session');
      if (typeof data.csrf_token !== 'string' || !data.csrf_token) throw new Error('服务未提供有效会话，请重新启动本地服务。');
      state.csrf = data.csrf_token; state.online = true; state.projects = data.projects || [];
      updateConnection(); renderProjects(); renderStage();
      notify('已连接本地服务。草案会保存到项目目录，运行结果与下载文件由 Python 实际生成。');
    } catch (failure) { state.online = false; updateConnection(); showFailure(failure); renderStage(); }
  }
  function installProject(project, preserveDraft = false) {
    const sameProject = state.project?.id === project.id;
    const restorePreparation = !sameProject || !state.preparationId;
    state.project = project;
    state.saved = signature(project.draft);
    if (!preserveDraft) state.draft = clone(project.draft);
    if (!sameProject || !findRun(state.baseId)) state.baseId = project.latest_build_run_id || '';
    state.buildId = project.latest_build_run_id || '';
    if (!state.preparationId && project.latest_preparation_run_id) state.preparationId = project.latest_preparation_run_id;
    if (state.preparationId && !findRun(state.preparationId)) state.preparationId = '';
    const restoredPreparation = findRun(state.preparationId);
    if (restorePreparation && restoredPreparation) {
      state.baseId = restoredPreparation.base_run_id;
      state.nextVersion = restoredPreparation.version;
      if (!state.feedbackDirty && !state.feedback.length) {
        const submittedReview = runs().slice().reverse().find(run => run.kind === 'review' && run.preparation_run_id === restoredPreparation.id && Array.isArray(run.feedback));
        if (submittedReview) state.feedback = clone(submittedReview.feedback);
      }
    }
    state.conflict = false;
    const summary = { id: project.id, title: project.title, revision: project.revision };
    const existing = state.projects.findIndex(p => p.id === project.id);
    if (existing >= 0) state.projects[existing] = summary; else state.projects.unshift(summary);
    renderProjects(); updateSummary();
  }
  async function perform(path, payload, onSuccess, message) {
    if (!actionable()) return;
    state.busy = true; const beforeTick = state.draftTick;
    error(''); notify(message || '本地 Python 正在执行，请稍候。'); updateConnection(); renderStage();
    try {
      const data = await api(path, payload);
      if (data.project) installProject(data.project, state.draftTick !== beforeTick);
      if (data.operation) { state.resultId = data.operation.id; state.lastOperation = data.operation; }
      if (onSuccess) onSuccess(data);
      if (state.draftTick !== beforeTick) notify('本次运行已完成。运行期间的新编辑仍保留在当前草案中，请再次保存。', true);
    } catch (failure) { showFailure(failure); notify('操作未成功；当前输入和未提交记录均已保留。', true); }
    finally { state.busy = false; updateConnection(); renderAll(); }
  }
  async function saveDraft() {
    const path = state.project ? '/api/projects/' + state.project.id + '/save' : '/api/projects';
    const payload = { draft: clone(state.draft) };
    if (state.project) payload.expected_revision = state.project.revision;
    await perform(path, payload, () => notify('草案已真实保存到本地项目目录。' + (state.draft.pending.length ? ' 待补内容继续保留。' : '')), '正在保存当前草案…');
  }
  function renderProjects() {
    $('project-select').replaceChildren(el('option', { value: '', text: '选择本地项目' }), ...state.projects.map(p => el('option', { value: p.id, text: p.title || p.id })));
    $('project-select').value = state.project?.id || '';
  }
  async function allowReplace(title) {
    if (!dirty() && !state.feedbackDirty && !state.observationDirty) return true;
    $('replace-title').textContent = title;
    const dialog = $('replace-dialog'); dialog.returnValue = '';
    return new Promise(resolve => { dialog.addEventListener('close', () => resolve(dialog.returnValue === 'replace'), { once: true }); dialog.showModal(); });
  }
  function resetLocal(draft = blankDraft()) {
    state.draft = draft; state.project = null; state.saved = ''; state.resultId = ''; state.baseId = ''; state.buildId = ''; state.preparationId = '';
    state.feedback = []; state.feedbackDirty = false; state.observationEdits = {}; state.observationDirty = false; state.stage = 'create'; state.version = '1.0'; state.nextVersion = '1.1'; state.draftTick++;
    renderAll();
  }
  async function loadProject(id) {
    if (!id || !actionable()) return;
    if (!(await allowReplace('恢复另一个项目？'))) { renderProjects(); return; }
    state.busy = true; updateConnection();
    try {
      const data = await api('/api/projects/' + encodeURIComponent(id));
      state.preparationId = ''; state.feedback = []; state.feedbackDirty = false; state.observationEdits = {}; state.observationDirty = false;
      installProject(data.project); state.resultId = data.project.latest_build_run_id || ''; state.stage = 'create';
      notify('已恢复实际保存的项目与历史版本。旧观察按版本保留，不会自动迁移到新版本。'); error('');
    } catch (failure) { showFailure(failure); }
    finally { state.busy = false; renderAll(); }
  }
  function updateSummary() {
    $('summary-title').textContent = state.draft.title || '你的下一份产品任务';
    $('summary-kind').textContent = (state.draft.kind === 'form' ? '表单 / 请求' : '集合 / 列表') + ' · ' + (state.draft.source_kind === 'synthetic' ? '合成材料' : '用户提供材料');
    $('summary-fields').textContent = state.draft.fields.length + ' 个';
    $('summary-checks').textContent = state.draft.requirement.checks.length + ' 条';
    $('summary-pending').textContent = state.draft.pending.length + (state.draft.decision_status !== 'declared' ? ' 项 + 决定未明确' : ' 项');
    $('summary-version').textContent = state.project ? '修订号 ' + state.project.revision : '未保存';
    const build = findRun(state.project?.latest_build_run_id);
    $('summary-evidence').textContent = build ? ('最近生成 ' + build.version + ' · ' + build.status + (dirty() || !build.current_source ? '。当前材料已变，旧观察仅作历史记录。' : '。生成与业务验收分别记录。')) : '先保存草案，再生成真实原型、PRD 与 Word。';
    $('save-status').textContent = state.busy ? '本地服务处理中…' : !state.project ? '草案尚未保存' : dirty() ? '当前草案未保存' : '已保存 · 修订号 ' + (state.project?.revision ?? '—');
    $('save-status').className = 'save-status' + (dirty() ? ' dirty' : '');
    $('version-trail').replaceChildren(...builds().slice(-4).map(run => el('b', { text: run.version })));
    $('save-draft').disabled = !actionable();
  }
  function renderAll() {
    document.querySelectorAll('[data-stage]').forEach(item => { const active = item.dataset.stage === state.stage; item.classList.toggle('active', active); if (active) item.setAttribute('aria-current', 'step'); else item.removeAttribute('aria-current'); });
    const headings = {
      create: ['YOUR NEXT PRODUCT DECISION', '先把问题，说清楚。', '确定的写下来，未决的保留。保存后生成真实原型与需求文档。'],
      revise: ['EVERY FEEDBACK HAS A PLACE', '每一条反馈，都有去向。', '从已生成版本开始修改，使用真实变化路径记录处理，再生成新版本。'],
      handoff: ['MAKE THE NEXT STEP CLEAR', '让下一位，接得住。', '打开选定版本，逐条记录观察。缺口与失败留在交接包中。']
    }[state.stage];
    ['stage-eyebrow', 'stage-title', 'stage-description'].forEach((id, i) => $(id).textContent = headings[i]);
    $('load-sample').hidden = state.stage !== 'create';
    updateConnection(); updateSummary(); renderStage(); renderResult();
  }
  function renderStage() {
    const content = $('stage-content');
    content.replaceChildren(state.stage === 'create' ? createPanel() : state.stage === 'revise' ? revisionPanel() : handoffPanel());
  }
  function createPanel() {
    const d = state.draft;
    const card = el('div', { class: 'editor-card' });
    card.append(section('先选一个任务载体', '保持范围具体。本轮只支持集合和表单两种原型。', '01', [
      el('div', { class: 'type-options' }),
      grid([draftField('任务标题', 'task-title', 'title', { maxlength: 120, placeholder: '一个具体、可讨论的产品问题', wide: true }), draftField('面向谁', 'audience', 'audience'), draftField('要解决的问题 / 痛点', 'problem', 'problem'), draftField('产品定位', 'positioning', 'positioning'), draftField('产品价值假设', 'value', 'value_hypothesis'), draftField('这次希望达到什么', 'goal', 'goal', { wide: true })]),
      advanced('补充优先级依据与成功指标', [grid([
        draftField('优先级依据', 'priority-basis', 'priority_basis', { multiline: true, wide: true }),
        ...[['statement', '衡量什么'], ['baseline', '当前基线'], ['target', '希望达到'], ['measurement', '如何测量']].map(([key, label]) => field(label, 'metric-' + key, d.success_metric[key], value => { d.success_metric[key] = value; changed(); }))
      ])])
    ]));
    // Type cards are built as DOM nodes; no supplied content is treated as HTML.
    const typeContainer = card.querySelector('.type-options');
    for (const [value, title, detail] of [['collection', '集合 / 列表', '浏览、筛选与维护信息'], ['form', '表单 / 请求', '填写、校验与提交状态']]) {
      typeContainer.append(button('', () => {
        if (state.project && builds().length && d.kind !== value) { error('已有生成版本的项目不能更换载体。请新建任务以保留当前版本链。'); return; }
        d.kind = value; changed(); renderStage();
      }, 'type-option' + (d.kind === value ? ' selected' : ''), { 'aria-pressed': String(d.kind === value) }));
      typeContainer.lastChild.append(el('strong', { text: title }), el('small', { text: detail }));
    }
    card.append(section('来源、范围与决定', '来源类型和决定状态由你明确声明。未决事项不会自动变成已审批。', '02', [
      grid([
        draftField('材料来源类型', 'source-kind', 'source_kind', { options: { synthetic: '人工合成材料', 'user-supplied': '用户提供材料' } }),
        draftField('本次决定状态', 'decision-status', 'decision_status', { options: decisions, hint: '“已声明”表示你声明已有决定；工具不认证审批真实性。' }),
        draftField('来源说明', 'source-note', 'source_note', { multiline: true, wide: true, hint: '合成样例请写明为合成；用户材料请记录来源与时点。' }),
        listField('本轮纳入范围', 'included', 'included'), listField('本轮不做什么', 'excluded', 'excluded'),
        listField('待补 / 未决', 'pending', 'pending', { wide: true })
      ])
    ]));
    card.append(section('主需求、规则与检查', '一个主需求，配一组规则；检查条件与预期会进入实际 PRD 和验收模板。', '03', [
      grid([field('主需求', 'main-requirement', d.requirement.statement, value => { d.requirement.statement = value; changed(); }, { multiline: true, wide: true }), field('主需求优先级', 'main-priority', d.requirement.priority, value => { d.requirement.priority = value; changed(); }, { options: { must: '必须 · must', should: '应该 · should', could: '可选 · could' } })]),
      advanced('展开业务规则（默认 / 例外 / 边界）', [grid([...[['statement', '规则内容'], ['default', '默认行为'], ['exception', '例外情况'], ['boundary', '边界与限制']].map(([key, label]) => field(label, 'rule-' + key, d.rule[key], value => { d.rule[key] = value; changed(); }, { multiline: true }))])]),
      el('h3', { text: '逐条验收检查（' + d.requirement.checks.length + ' / 20）', style: 'margin-top:24px' }),
      ...d.requirement.checks.map((check, index) => el('div', { class: 'check-config' }, [
        el('div', { class: 'row-head' }, [el('strong', { text: '检查 ' + (index + 1) }), button('移除检查', () => { d.requirement.checks.splice(index, 1); changed(); renderStage(); }, 'delete-button', { disabled: d.requirement.checks.length <= 1 })]),
        grid([field('执行条件', 'check-condition-' + index, check.condition, value => { check.condition = value; changed(); }, { multiline: true, maxlength: 450 }), field('预期结果', 'check-expected-' + index, check.expected, value => { check.expected = value; changed(); }, { multiline: true, maxlength: 450 }), field('要求的证据层级', 'check-level-' + index, check.evidence_level, value => { check.evidence_level = value; changed(); }, { options: levels })])
      ])),
      button('＋ 添加一条检查', () => { d.requirement.checks.push({ condition: '', expected: '', evidence_level: 'browser' }); changed(); renderStage(); }, 'button small', { disabled: d.requirement.checks.length >= 20 })
    ]));
    card.append(section('配置实际信息字段', '字段、选项与样例值将直接进入生成规格。类型不匹配时会明确阻止生成。', '04', [
      ...(d.fields.length ? d.fields.map((f, i) => fieldConfig(f, i)) : [el('div', { class: 'empty-state' }, [el('p', { text: '还没有信息字段。至少配置 1 个，最多 16 个。' }), button('＋ 添加第一个字段', addField, 'button small')])]),
      d.fields.length ? button('＋ 添加字段', addField, 'button small', { disabled: d.fields.length >= 16 }) : null,
      advanced(d.kind === 'collection' ? '样例记录、搜索、筛选与布局' : '表单初始值', [d.kind === 'collection' ? collectionConfig() : formConfig()], d.fields.length > 0)
    ].filter(Boolean)));
    if (d.legacy_notes.length) card.append(section('旧材料留存', '仅保留为未核验备注，不计入观察、通过或审批。', '05', [el('ul', { class: 'issue-list' }, d.legacy_notes.map(text => el('li', { text })))]));
    const exists = builds().length > 0;
    const actions = el('div', { class: 'stage-actions' }, [
      el('p', { text: exists ? '当前项目已有首版。修改草案后到「修订」选择准确前版，准备并关联反馈。' : '先保存草案，再生成首版。GENERATED_NOT_ACCEPTED 表示已生成、尚未验收。' }),
      exists ? button('前往修订 →', () => setStage('revise'), 'button primary') : button('保存后生成首版 →', buildFirst, 'button primary', { id: 'build-first', disabled: !actionable() || !state.project || dirty() })
    ]);
    const container = el('div', {}, [card, !exists ? field('首版版本号', 'first-version', state.version, value => { state.version = value; }, { hint: '与生成文件及后续版本链绑定，例如 1.0。' }) : null, actions]);
    return container;
  }
  function defaultValue(type) { return type === 'number' ? null : type === 'tags' ? [] : ''; }
  function addField() {
    const d = state.draft; if (d.fields.length >= 16) return;
    let i = d.fields.length + 1; while (d.fields.some(f => f.key === 'field_' + i)) i++;
    const key = 'field_' + i;
    d.fields.push({ key, label: '', type: 'text', required: false, choices: [], minimum: null, maximum: null });
    d.form.initial_values[key] = '';
    for (const item of d.collection.items) item.values[key] = '';
    if (!d.collection.search_fields.length) d.collection.search_fields.push(key);
    changed(); renderStage();
  }
  function fieldConfig(f, i) {
    const d = state.draft;
    const unsupported = !Object.hasOwn(types, f.type) || (d.kind === 'collection' && (f.minimum !== null || f.maximum !== null));
    const typeOptions = Object.hasOwn(types, f.type) ? types : { [f.type]: '不支持：' + f.type + '（请修正）', ...types };
    const wrapper = el('div', { class: 'field-config' + (unsupported ? ' unsupported' : '') }, [
      el('div', { class: 'row-head' }, [el('strong', { text: '字段 ' + (i + 1) }), button('移除字段', () => {
        d.fields.splice(i, 1); delete d.form.initial_values[f.key]; for (const item of d.collection.items) delete item.values[f.key];
        d.collection.search_fields = d.collection.search_fields.filter(key => key !== f.key); d.collection.filters = d.collection.filters.filter(key => key !== f.key);
        changed(); renderStage();
      }, 'delete-button')]),
      grid([
        field('字段名称', 'field-label-' + i, f.label, value => { f.label = value; changed(); }, { maxlength: 80 }),
        field('字段标识', 'field-key-' + i, f.key, value => {
          const old = f.key; f.key = value;
          for (const item of d.collection.items) { item.values[value] = item.values[old]; delete item.values[old]; }
          d.form.initial_values[value] = d.form.initial_values[old]; delete d.form.initial_values[old];
          d.collection.search_fields = d.collection.search_fields.map(key => key === old ? value : key); d.collection.filters = d.collection.filters.map(key => key === old ? value : key); changed();
        }, { maxlength: 40, hint: '小写字母开头，只含字母、数字和下划线。' }),
        field('字段类型', 'field-type-' + i, f.type, value => { f.type = value; changed(); renderStage(); }, { options: typeOptions }),
        el('label', { class: 'checkbox-label', for: 'field-required-' + i }, [el('input', { type: 'checkbox', id: 'field-required-' + i, checked: f.required, onchange: event => { f.required = event.target.checked; changed(); } }), '必填字段'])
      ])
    ]);
    if (['choice', 'tags'].includes(f.type) || f.choices.length) wrapper.append(field('允许选项', 'field-choices-' + i, f.choices.join('\n'), value => { f.choices = lines(value); changed(); }, { multiline: true, hint: ['choice', 'tags'].includes(f.type) ? '每行一个选项，最多 30 个。样例值必须来自这些选项。' : '当前类型不接受选项；请明确清空此栏后保存。' }));
    if ((f.type === 'number' && d.kind === 'form') || f.minimum !== null || f.maximum !== null) wrapper.append(grid([
      field('数值最小值', 'field-min-' + i, f.minimum, value => { f.minimum = value; changed(); }, { type: 'number' }), field('数值最大值', 'field-max-' + i, f.maximum, value => { f.maximum = value; changed(); }, { type: 'number' })
    ]));
    if (unsupported) wrapper.append(el('p', { class: 'small-note', text: '导入的类型或数值边界不受本轮生成能力支持，原值已保留。请明确更换类型 / 清空集合上下限后保存，系统不会自动降级。' }));
    return wrapper;
  }
  function valueControl(f, value, id, update) {
    if (f.type === 'choice') {
      const choices = { '': '请选择 / 留空' };
      for (const choice of f.choices) choices[choice] = choice;
      if (value && !Object.hasOwn(choices, value)) choices[value] = '待修正的旧值：' + value;
      return select(id, value ?? '', choices, update);
    }
    if (f.type === 'tags') {
      if (!Array.isArray(value)) return el('div', {}, [el('p', { class: 'small-note', text: '当前旧值不是标签数组：' + printable(value) }), button('明确重置为空标签', () => { update([]); renderStage(); }, 'text-button')]);
      let selectedValues = [...value];
      const result = el('div', { class: 'choice-list', role: 'group', 'aria-label': f.label || f.key });
      [...new Set([...f.choices, ...value])].forEach((choice, n) => result.append(el('label', { for: id + '-' + n }, [el('input', { type: 'checkbox', id: id + '-' + n, checked: value.includes(choice), onchange: event => { selectedValues = event.target.checked ? [...selectedValues, choice] : selectedValues.filter(x => x !== choice); update([...selectedValues]); } }), choice + (!f.choices.includes(choice) ? '（旧值待修正）' : '')])));
      if (!f.choices.length && !value.length) result.append(el('span', { class: 'small-note', text: '请先填写允许选项。' }));
      return result;
    }
    return el('input', { id, 'aria-label': f.label || f.key, type: f.type === 'number' ? 'number' : 'text', value: value ?? '', maxlength: 1000, oninput: event => update(f.type === 'number' ? (event.target.value === '' ? null : Number(event.target.value)) : event.target.value) });
  }
  function collectionConfig() {
    const d = state.draft;
    if (!d.fields.length) return el('p', { class: 'small-note', text: '先添加字段，再用表格维护样例。' });
    const pick = (title, key, candidates) => el('fieldset', { class: 'path-picks' }, [el('legend', { text: title }), ...candidates.map((f, i) => el('label', { class: 'checkbox-label', for: key + '-' + i }, [el('input', { id: key + '-' + i, type: 'checkbox', checked: d.collection[key].includes(f.key), onchange: event => { d.collection[key] = event.target.checked ? [...d.collection[key], f.key] : d.collection[key].filter(x => x !== f.key); changed(); } }), f.label || f.key]))]);
    const result = el('div', {}, [
      field('筛选布局', 'collection-layout', d.collection.layout, value => { d.collection.layout = value; changed(); }, { options: { sidebar: '侧栏筛选', toolbar: '顶部工具栏' } }),
      pick('搜索字段（当前生成器至少需要一个）', 'search_fields', d.fields),
      pick('可选筛选字段（单选 / 标签）', 'filters', d.fields.filter(f => ['choice', 'tags'].includes(f.type)))
    ]);
    if (d.collection.filters.some(key => !d.fields.some(f => f.key === key && ['choice', 'tags'].includes(f.type)))) result.append(el('p', { class: 'small-note', text: '旧筛选中包含类型已变更的字段。请明确清空不支持的筛选后再保存。' }), button('清除不受支持的筛选', () => { d.collection.filters = d.collection.filters.filter(key => d.fields.some(f => f.key === key && ['choice', 'tags'].includes(f.type))); changed(); renderStage(); }, 'text-button'));
    const table = el('table', {}, [el('caption', { text: '集合样例记录（' + d.collection.items.length + ' 条，最多 500 条）' }), el('thead', {}, [el('tr', {}, [el('th', { scope: 'col', text: '记录标识' }), ...d.fields.map(f => el('th', { scope: 'col', text: f.label || f.key })), el('th', { scope: 'col', text: '操作' })])])]);
    table.append(el('tbody', {}, d.collection.items.map((item, i) => el('tr', {}, [
      el('td', {}, [el('input', { value: item.id, 'aria-label': '第 ' + (i + 1) + ' 条记录标识', maxlength: 40, oninput: event => { item.id = event.target.value; changed(); } })]),
      ...d.fields.map((f, j) => el('td', {}, [valueControl(f, item.values[f.key], 'item-' + i + '-' + j, value => { item.values[f.key] = value; changed(); })])),
      el('td', {}, [button('移除', () => { d.collection.items.splice(i, 1); changed(); renderStage(); }, 'delete-button', { 'aria-label': '移除第 ' + (i + 1) + ' 条样例记录' })])
    ]))));
    result.append(el('div', { class: 'table-wrap', tabindex: '0', 'aria-label': '样例数据表，可横向滚动' }, [table]), el('div', { class: 'field-actions' }, [button('＋ 添加样例记录', () => { let i = d.collection.items.length + 1; while (d.collection.items.some(x => x.id === 'item_' + i)) i++; d.collection.items.push({ id: 'item_' + i, values: Object.fromEntries(d.fields.map(f => [f.key, defaultValue(f.type)])) }); changed(); renderStage(); }, 'button small', { disabled: d.collection.items.length >= 500 })]), el('p', { class: 'small-note', text: '集合只支持浏览器内的演示维护，不连接业务数据库。样例内容将进入生成文件。' }));
    return result;
  }
  function formConfig() {
    const d = state.draft;
    if (!d.fields.length) return el('p', { class: 'small-note', text: '先添加字段，再填写表单初始值。' });
    return el('div', { class: 'table-wrap', tabindex: '0', 'aria-label': '表单初始值表' }, [el('table', {}, [el('caption', { text: '表单初始值 · 初始状态为草稿' }), el('thead', {}, [el('tr', {}, [el('th', { scope: 'col', text: '字段' }), el('th', { scope: 'col', text: '初始值' })])]), el('tbody', {}, d.fields.map((f, i) => el('tr', {}, [el('th', { scope: 'row', text: f.label || f.key }), el('td', {}, [valueControl(f, d.form.initial_values[f.key], 'form-value-' + i, value => { d.form.initial_values[f.key] = value; changed(); })])])) )])]);
  }
  async function buildFirst() {
    if (!state.project || dirty()) { error('请先保存当前草案，再生成首版。'); return; }
    await perform('/api/projects/' + state.project.id + '/build', { draft: clone(state.draft), expected_revision: state.project.revision, version: state.version }, data => {
      state.buildId = data.project.latest_build_run_id; state.baseId = state.buildId;
      notify('首版已实际运行。请查看核对状态，再打开原型记录观察。');
    }, '正在实际运行 build 与 check，并生成 PRD / Word…');
  }
  function preparationStale() {
    const prep = currentPreparation();
    return !prep || dirty() || (prep.source_revision !== undefined && prep.source_revision !== state.project?.revision) || prep.base_run_id !== state.baseId || prep.version !== state.nextVersion || prep.id !== state.project?.latest_preparation_run_id;
  }
  function buildOptions(forRevision = false) {
    return Object.fromEntries(builds().map(run => [run.id, run.version + ' · ' + run.status + ' · ' + run.id + (forRevision && currentPreparation()?.base_run_id === run.id ? '（当前准备材料前版）' : run.id === state.project.latest_build_run_id ? '（最近生成）' : '（历史只读）')]));
  }
  function pathLabel(change) {
    const words = { brief: '产品资料', audience: '目标用户', problem: '痛点', positioning: '产品定位', value_hypothesis: '价值假设', pain: '痛点', value: '价值', goal: '目标', priority_basis: '优先级依据', success_metric: '成功指标', statement: '内容', baseline: '基线', target: '目标', measurement: '测量方法', title: '标题', scope: '范围', included: '纳入范围', excluded: '排除范围', pending: '未决项', rules: '规则', rule_main: '主规则', default: '默认行为', exception: '例外', boundary: '边界', requirements: '需求', main: '主需求', checks: '检查', condition: '执行条件', expected: '预期', evidence_level: '证据层级', prototype: '原型', fields: '信息字段', label: '字段名称', type: '字段类型', required: '必填', choices: '选项', search_fields: '搜索字段', filters: '筛选字段', layout: '筛选布局', items: '样例记录', values: '样例值', initial_values: '表单初值', decisions: '决定', decision_main: '主决定', status: '状态', evidence: '来源证据', source_note: '来源说明', minimum: '最小值', maximum: '最大值' };
    if (change.label && change.label !== change.path && !change.label.startsWith('/')) return change.label;
    return change.path.split('/').filter(Boolean).map(part => words[part] || (part.startsWith('main_c') ? '检查 ' + part.slice(6) : part)).join(' › ');
  }
  function printable(value) { return value === undefined ? '（不存在）' : value === null ? '（空值）' : typeof value === 'string' ? value : JSON.stringify(value, null, 2); }
  function revisionPanel() {
    if (!builds().length) return el('section', { class: 'surface empty-state' }, [el('h2', { text: '先形成一个真实首版' }), el('p', { text: '创建页保存草案并完成生成后，才能选定前版、准备变化与处理反馈。' }), button('回到创建任务 →', () => setStage('create'), 'button primary')]);
    const prep = currentPreparation();
    const selectedBase = findRun(state.baseId);
    const stale = preparationStale();
    const result = el('div', {}, [el('section', { class: 'surface' }, [
      el('h2', { text: '从准确的已生成版本开始' }), el('p', { class: 'muted', text: '先在当前草案中修改，再准备真实差异。一个页面变化可能对应多条技术路径。' }),
      grid([field('修订前版', 'base-run', state.baseId, value => { state.baseId = value; renderStage(); }, { options: buildOptions(true) }), field('新版本号', 'next-version', state.nextVersion, value => { state.nextVersion = value; if ($('run-review')) $('run-review').disabled = !actionable() || preparationStale(); if (currentPreparation() && preparationStale()) notify('修订版本号已改变，现有反馈输入保留。请重新准备变化后再提交。', true); })]),
      el('div', { class: 'stage-actions' }, [button('编辑当前草案', () => setStage('create'), 'button'), button('准备真实变化 →', prepareReview, 'button primary', { disabled: !actionable() || selectedBase?.id !== state.project.latest_build_run_id })]),
      selectedBase?.id !== state.project.latest_build_run_id ? el('p', { class: 'small-note', text: '已准备材料保留其准确前版，可继续修正同一准备版的反馈。要开始下一轮新修订，请显式选择最近生成版本并设置新版本号后重新准备。' }) : null,
      dirty() ? el('p', { class: 'small-note', text: '当前有未保存编辑。“准备真实变化”会将当前草案真实保存，并绑定本次前后版。' }) : null
    ])]);
    if (!prep) { result.append(el('section', { class: 'surface empty-state' }, [el('h3', { text: '准备后，变化会出现在这里' }), el('p', { text: '系统只提供实际变化路径，反馈不会被自动采纳或自动关联。' })])); return result; }
    const changes = prep.changes || [];
    result.append(el('section', { class: 'surface' }, [el('div', { class: 'status-heading' }, [el('h2', { text: '实际变化 · ' + changes.length + ' 条路径' }), el('span', { class: 'pill' + (stale ? ' warning' : ''), text: stale ? '已陈旧 · 请重新准备' : '已绑定准备版本 ' + prep.version })]),
      stale ? el('p', { class: 'notice warning', text: '当前草案、版本或前版已变化；此处记录保留，但不能直接提交。请重新准备后逐条检查关联。' }) : null,
      ...changes.map(change => el('div', { class: 'change-card' }, [el('strong', { text: pathLabel(change) }), el('div', { class: 'change-values' }, [el('p', {}, [el('small', { text: '前版' }), printable(change.before)]), el('p', {}, [el('small', { text: '候选版' }), printable(change.after)])]), el('details', {}, [el('summary', { text: '查看技术路径' }), el('p', { class: 'tech-path', text: change.path })])]))
    ].filter(Boolean)));
    const feedbackSurface = el('section', { class: 'surface' }, [el('h2', { text: '逐条保存反馈处理' }), el('p', { class: 'muted', text: '每条填写原意、来源、处理状态与理由；采纳时显式多选关联路径。未决与冲突会保留为 HOLD。' })]);
    if (!state.feedback.length) feedbackSurface.append(el('p', { class: 'empty-state', text: '尚未填写反馈处理记录。不会自动将全部变化设为采纳。' }));
    state.feedback.forEach((row, index) => {
      const card = el('article', { class: 'feedback-card' }, [
        el('div', { class: 'row-head' }, [el('strong', { text: '反馈 ' + (index + 1) }), button('移除反馈', () => { state.feedback.splice(index, 1); feedbackChanged(); renderStage(); }, 'delete-button')]),
        grid([field('反馈原意', 'feedback-text-' + index, row.text, value => { row.text = value; feedbackChanged(); }, { multiline: true, wide: true, maxlength: 3000 }), field('反馈来源', 'feedback-source-' + index, row.source, value => { row.source = value; feedbackChanged(); }), field('处理状态', 'feedback-status-' + index, row.status, value => { row.status = value; feedbackChanged(); renderStage(); }, { options: feedbackStatuses }), field('处理理由', 'feedback-reason-' + index, row.rationale, value => { row.rationale = value; feedbackChanged(); }, { multiline: true, wide: true, maxlength: 3000 })])
      ]);
      const paths = el('fieldset', { class: 'path-picks' }, [el('legend', { text: '关联实际变化（可多选）' })]);
      changes.forEach((change, ci) => paths.append(el('div', { class: 'path-choice' }, [el('input', { type: 'checkbox', id: 'feedback-path-' + index + '-' + ci, checked: row.paths.includes(change.path), disabled: row.status !== 'adopted' && !row.paths.includes(change.path), onchange: event => { row.paths = event.target.checked ? [...row.paths, change.path] : row.paths.filter(p => p !== change.path); feedbackChanged(); } }), el('div', {}, [el('label', { for: 'feedback-path-' + index + '-' + ci, text: pathLabel(change) }), el('details', {}, [el('summary', { text: '技术路径' }), el('p', { class: 'tech-path', text: change.path })])])])));
      row.paths.filter(path => !changes.some(change => change.path === path)).forEach(path => paths.append(el('div', { class: 'notice warning' }, [el('p', { text: '旧关联已不在本次实际变化中：' + path }), button('移除此旧关联', () => { row.paths = row.paths.filter(p => p !== path); feedbackChanged(); renderStage(); }, 'text-button')])));
      if (row.status !== 'adopted') paths.append(el('p', { class: 'small-note', text: '只有采纳反馈可以关联变化；改成其他状态后，请明确取消原关联。' }));
      card.append(paths); feedbackSurface.append(card);
    });
    feedbackSurface.append(button('＋ 添加一条反馈', () => { state.feedback.push({ id: uid('feedback'), text: '', source: '', status: 'pending', rationale: '', paths: [] }); feedbackChanged(); renderStage(); }, 'button small', { disabled: state.feedback.length >= 100 }), el('p', { class: 'small-note', text: state.feedbackDirty ? '处理记录尚未提交。下方按钮会真实保存处理记录，并运行修订核对与新版本生成。' : '已提交的处理记录会保留在对应修订运行的文件中。' }), el('div', { class: 'stage-actions' }, [el('p', { text: '请逐条核对，没有已选路径的改动会继续出现在实际核对缺口中。' }), button('保存处理记录并生成修订 →', runReview, 'button primary', { id: 'run-review', disabled: !actionable() || stale })]));
    result.append(feedbackSurface); return result;
  }
  async function prepareReview() {
    if (!state.project) return;
    await perform('/api/projects/' + state.project.id + '/prepare-review', { draft: clone(state.draft), expected_revision: state.project.revision, base_run_id: state.baseId, version: state.nextVersion }, data => {
      state.preparationId = data.operation.id;
      notify('已从真实前后版准备变化。请逐条填写反馈并显式选择关联；已有反馈材料保留，请重新核对路径。', true);
    }, '正在保存候选草案，并运行 prepare-review / check 获取真实变化路径…');
  }
  async function runReview() {
    if (preparationStale()) { error('准备材料已陈旧。请重新准备后再核对反馈关联。'); return; }
    if (!state.feedback.length) { error('请至少添加并处理一条真实反馈。系统不会代替你自动采纳全部变化。'); return; }
    const submittedFeedback = signature(state.feedback);
    await perform('/api/projects/' + state.project.id + '/review', { preparation_run_id: state.preparationId, expected_revision: state.project.revision, feedback: clone(state.feedback) }, data => {
      state.feedbackDirty = signature(state.feedback) !== submittedFeedback; state.buildId = data.operation.build_run_id || data.project.latest_build_run_id;
      // The prepared before/after pair stays fixed when only feedback processing changes.
      // Starting another revision requires an explicit latest-build selection and a new preparation.
      notify(state.feedbackDirty ? '本次反馈处理已提交。请求期间的新反馈编辑仍保留，尚未再次提交。' : '反馈处理记录已提交，实际修订运行已结束。查看结果状态；新版本不会继承前版的通过观察。');
    }, '正在保存反馈处理记录，运行 review / review-check 与新版本 build / check…');
  }
  function observationKey(run, row) { return run.id + ':' + row.check_id; }
  function observationValue(run, row) {
    return state.observationEdits[observationKey(run, row)] || {
      check_id: row.check_id, status: row.latest?.status || 'not_run', level: row.latest?.level || row.evidence_level,
      observed: row.latest?.observed || '', evidence_ref: row.latest?.evidence_ref || '', defect: row.latest?.defect || ''
    };
  }
  function changeObservation(run, row, key, value) {
    const id = observationKey(run, row);
    if (!state.observationEdits[id]) state.observationEdits[id] = clone(observationValue(run, row));
    state.observationEdits[id][key] = value; observationChanged();
    const note = $('observation-state-' + row.check_id); if (note) note.textContent = '这条观察有未提交编辑。';
    const deliver = $('deliver-build'); if (deliver) deliver.disabled = true;
  }
  function handoffPanel() {
    if (!builds().length) return el('section', { class: 'surface empty-state' }, [el('h2', { text: '先生成一个真实版本' }), el('p', { text: '交接检查来自已生成版本的实际模板，不能凭空创建通过记录。' }), button('回到创建任务 →', () => setStage('create'), 'button primary')]);
    const run = currentBuild() || builds()[builds().length - 1];
    const editable = currentEvidence(run);
    const unsavedForRun = Object.keys(state.observationEdits).some(key => key.startsWith(run.id + ':'));
    const result = el('div', {}, [el('section', { class: 'surface' }, [
      el('h2', { text: '选定本次要交接的实际版本' }),
      field('观察与交接版本', 'handoff-build', run.id, value => { state.buildId = value; renderStage(); }, { options: buildOptions() }),
      el('p', { class: 'small-note', text: editable ? '当前版本与已保存草案一致。先打开原型完成实际检查，再逐条保存观察。' : '此版本为历史只读，或当前草案已有变化。观察仍保留供查阅；请完成当前修订并选最新版本后再记录与交接。' }),
      artifactActions(run),
      el('div', { class: 'notice' + (editable ? '' : ' warning'), style: 'margin-top:18px', text: '版本 ' + run.version + ' · ' + run.status + '。' + (statusMeanings[run.status] || '请查看实际核对结果。') })
    ])]);
    const observations = el('section', { class: 'surface' }, [el('h2', { text: '逐条检查与观察' }), el('p', { class: 'muted', text: '状态默认未执行。保存的是使用者提供的观察，工具不会自动执行或认证其真实性；失败后的复验会由服务器追加 supersedes 链。' })]);
    if (!run.checks?.length) observations.append(el('p', { class: 'notice warning', text: '此运行没有可用的检查模板，请检查生成结果，不能补造通过记录。' }));
    for (const [index, row] of (run.checks || []).entries()) {
      const value = observationValue(run, row);
      const card = el('article', { class: 'observation-card' + (editable ? '' : ' read-only') }, [
        el('div', { class: 'row-head' }, [el('strong', { text: '检查 ' + (index + 1) + ' · ' + row.check_id }), el('span', { class: 'pill' + (row.status === 'fail' ? ' error' : row.status === 'not_run' ? ' warning' : ''), text: { pass: '已记录通过', fail: '已记录失败', not_run: '未执行' }[row.status] || row.status })]),
        el('h3', { text: row.condition || row.statement || row.check_id }), el('p', { text: '预期：' + (row.expected || '请查阅本版验收模板') }),
        el('span', { class: 'required-level', text: '要求证据层级：' + (levels[row.evidence_level] || row.evidence_level) }),
        grid([
          field('本次实际状态', 'obs-status-' + index, value.status, v => changeObservation(run, row, 'status', v), { options: { not_run: '未执行', pass: '通过', fail: '失败' }, disabled: !editable }),
          field('本次实际证据层级', 'obs-level-' + index, value.level, v => changeObservation(run, row, 'level', v), { options: levels, disabled: !editable }),
          field('实际观察', 'obs-observed-' + index, value.observed, v => changeObservation(run, row, 'observed', v), { multiline: true, disabled: !editable, maxlength: 3000 }),
          field('证据引用', 'obs-evidence-' + index, value.evidence_ref, v => changeObservation(run, row, 'evidence_ref', v), { multiline: true, disabled: !editable, maxlength: 3000, hint: '例如截图 / 运行记录的位置；此栏不上传文件。' }),
          field('缺陷描述', 'obs-defect-' + index, value.defect, v => changeObservation(run, row, 'defect', v), { multiline: true, wide: true, disabled: !editable, maxlength: 3000, hint: '失败时需写明缺陷；复验通过后历史失败仍会保留。' })
        ]),
        el('p', { id: 'observation-state-' + row.check_id, class: 'small-note', text: state.observationEdits[observationKey(run, row)] ? '这条观察有未提交编辑。' : row.latest ? '当前显示的是已保存的最近一条观察。' : '此检查尚未记录实际执行。' }),
        button('保存这条实际观察', () => saveObservation(run, row), 'button small', { disabled: !actionable() || !editable }),
        observationHistory(row)
      ]);
      observations.append(card);
    }
    result.append(observations, el('section', { class: 'surface' }, [el('h2', { text: '生成真实交接包' }), el('p', { class: 'muted', text: '将调用 deliver / deliver-check。即使存在缺口，HOLD 包也保留可下载文件、缺陷与待补项；不会替你把检查设为通过。' }), unsavedForRun ? el('p', { class: 'notice warning', text: '本版仍有未提交观察，请逐条保存后再生成交接包。' }) : null, el('div', { class: 'stage-actions' }, [el('p', { text: '只能交接与当前已保存草案一致的最新生成版本。' }), button('生成交接包并核对 →', () => deliver(run), 'button primary', { id: 'deliver-build', disabled: !actionable() || !editable || unsavedForRun })])].filter(Boolean)));
    return result;
  }
  function observationHistory(row) {
    return el('details', { class: 'history' }, [el('summary', { text: '已保存历史 / 复验链（' + (row.history?.length || 0) + '）' }), el('ol', {}, (row.history || []).map(item => el('li', {}, [el('strong', { text: item.id + ' · ' + item.status + ' · ' + (levels[item.level] || item.level) }), el('p', { text: item.observed || '未执行' }), item.evidence_ref ? el('p', { text: '证据：' + item.evidence_ref }) : null, item.defect ? el('p', { text: '缺陷：' + item.defect }) : null, item.supersedes ? el('p', { text: '复验承接：' + item.supersedes }) : null].filter(Boolean))))]);
  }
  async function saveObservation(run, row) {
    if (!currentEvidence(run)) { error('此版本观察只读。请选中与已保存草案一致的最新生成版本。'); return; }
    const submittedObservation = signature(observationValue(run, row));
    const payloadRow = clone(observationValue(run, row));
    payloadRow.defect = payloadRow.defect?.trim() ? payloadRow.defect : null;
    await perform('/api/projects/' + state.project.id + '/observations', { build_run_id: run.id, rows: [payloadRow] }, () => {
      if (signature(observationValue(run, row)) === submittedObservation) delete state.observationEdits[observationKey(run, row)];
      state.observationDirty = Object.keys(state.observationEdits).length > 0;
      notify('这一条观察已真实追加保存。历史失败与复验承接保留，不会改写旧记录。');
    }, '正在追加保存这条实际观察…');
  }
  async function deliver(run) {
    if (!currentEvidence(run)) { error('当前材料已变化，请完成修订后再交接。'); return; }
    if (Object.keys(state.observationEdits).some(key => key.startsWith(run.id + ':'))) { error('本版还有未提交观察，请逐条保存后再交接。'); return; }
    await perform('/api/projects/' + state.project.id + '/deliver', { build_run_id: run.id }, () => notify('实际交接运行已结束。请查看返回的核对状态、缺口和下载文件。'), '正在运行 deliver / deliver-check 并生成真实交接包…');
  }
  function downloadLink(artifact, label) {
    try { return el('a', { class: 'button', href: safeUrl(artifact.url).href, download: artifact.name, text: label || artifact.name }); }
    catch (_) { return el('span', { class: 'small-note', text: '文件地址无效：' + artifact.name }); }
  }
  function previewArtifact(artifact) {
    try {
      const url = safeUrl(artifact.url); url.searchParams.set('preview', '1');
      $('prototype-frame').src = url.href; $('preview-dialog').showModal();
    } catch (failure) { error(failure.message); }
  }
  function artifactActions(run) {
    const items = run.artifacts || [];
    const result = el('div', { class: 'artifact-actions' });
    const prototype = items.find(item => item.name === 'prototype.html');
    if (prototype) result.append(button('打开真实原型 ↗', () => previewArtifact(prototype), 'button'));
    for (const item of items.filter(item => /\.docx$/i.test(item.name))) result.append(downloadLink(item, '下载 Word · ' + item.name));
    for (const item of items.filter(item => /PRD.*\.md$/i.test(item.name))) result.append(downloadLink(item, '下载 PRD · ' + item.name));
    if (run.package_url && items.length) {
      try { result.append(el('a', { class: 'button', href: safeUrl(run.package_url).href, download: 'package.zip', text: '下载本次真实文件包 ↓' })); } catch (_) { /* No unsafe link is rendered. */ }
    }
    return result;
  }
  function renderResult() {
    const box = $('operation-result');
    const run = findRun(state.resultId) || (state.lastOperation?.id === state.resultId ? state.lastOperation : null);
    box.replaceChildren(); box.hidden = !run && !runs().length;
    if (run) {
      const mode = run.status === 'ERROR' ? ' error' : run.status === 'HOLD' ? ' warning' : '';
      box.append(el('div', { class: 'status-heading' }, [el('h2', { text: '实际运行结果 · ' + (kinds[run.kind] || run.kind) }), el('span', { class: 'pill status-code' + mode, text: run.status })]), el('p', { class: 'status-description', text: statusMeanings[run.status] || '请依据本次实际核对结果继续处理。' }), el('p', { class: 'small-note', text: (run.version ? '版本 ' + run.version + ' · ' : '') + '运行 ' + run.id + ' · 退出码 ' + run.exit_code + (run.check ? ' · 核对 ' + run.check.status + ' / ' + run.check.exit_code : '') }));
      if (run.issues?.length) box.append(el('ul', { class: 'issue-list' }, run.issues.map(issue => el('li', { text: typeof issue === 'string' ? issue : printable(issue) }))));
      box.append(artifactActions(run));
      if (run.artifacts?.length) box.append(el('details', { class: 'artifact-list' }, [el('summary', { text: '所有实际文件与校验值（' + run.artifacts.length + '）' }), el('ul', {}, run.artifacts.map(item => el('li', {}, [downloadLink(item), el('small', { text: item.bytes + ' bytes · SHA256 ' + item.sha256 })])))]));
      if (run.steps?.length) box.append(el('details', { class: 'artifact-list' }, [el('summary', { text: '实际命令步骤与退出码' }), el('ul', {}, run.steps.map(step => el('li', { text: typeof step === 'string' ? step : printable(step) })))]));
    }
    if (runs().length) box.append(el('details', { class: 'run-history' }, [el('summary', { text: '保留的实际运行历史（' + runs().length + '）' }), ...runs().slice().reverse().map(item => el('div', { class: 'run-item' }, [el('strong', { text: (kinds[item.kind] || item.kind) + ' · ' + item.version }), el('span', { text: item.status + ' · ' + item.id }), button('查看结果', () => { state.resultId = item.id; renderResult(); }, 'button small')]))]));
  }
  function setStage(stage) {
    state.stage = stage; error(''); renderAll();
    $('main').focus({ preventScroll: true }); $('main').scrollIntoView({ block: 'start', behavior: 'auto' });
  }
  function syntheticDraft() {
    return {
      kind: 'collection', title: '微光工坊 · 共创材料清单', audience: '参加周末共创活动的组织者',
      problem: '活动准备材料分散，组织者反复确认每项材料的准备阶段与用途。',
      positioning: '用于小型共创活动筹备的材料清单原型', value_hypothesis: '通过集中浏览和筛选降低材料核对的重复沟通。',
      goal: '在同一清单内查看材料，并按准备阶段与用途筛选。', priority_basis: '优先验证集中浏览与筛选是否能支持一次活动的准备核对。',
      source_kind: 'synthetic', source_note: '全新人工合成练习，人物、活动、材料与数量均为虚构；没有真实客户或业务数据。',
      success_metric: { statement: '完成指定材料查找与筛选任务', baseline: '尚未实测，初始为三条合成材料', target: '检查者能找到指定材料并恢复全部记录', measurement: '打开生成原型，按本任务三条浏览器检查逐项记录实际观察' },
      included: ['材料列表、关键词搜索、准备阶段和用途筛选', '浏览器内新增、编辑和详情演示'],
      excluded: ['真实库存、采购、多人协作与持久化业务数据库', '自动审批和自动验收'], pending: [], decision_status: 'pending',
      fields: [
        { key: 'name', label: '材料名称', type: 'text', required: true, choices: [], minimum: null, maximum: null },
        { key: 'phase', label: '准备阶段', type: 'choice', required: true, choices: ['待准备', '已备齐'], minimum: null, maximum: null },
        { key: 'usage', label: '用途', type: 'tags', required: true, choices: ['绘画', '装饰'], minimum: null, maximum: null },
        { key: 'quantity', label: '件数', type: 'number', required: true, choices: [], minimum: null, maximum: null }
      ],
      collection: { search_fields: ['name'], filters: ['phase', 'usage'], layout: 'sidebar', items: [
        { id: 'material_a', values: { name: '晨光画纸', phase: '待准备', usage: ['绘画'], quantity: 12 } },
        { id: 'material_b', values: { name: '苔绿丝带', phase: '已备齐', usage: ['装饰'], quantity: 6 } },
        { id: 'material_c', values: { name: '小岛彩笔', phase: '已备齐', usage: ['绘画', '装饰'], quantity: 8 } }
      ] },
      form: { initial_values: { name: '', phase: '', usage: [], quantity: null }, initial_state: 'draft' },
      requirement: { statement: '组织者能够浏览材料清单，通过关键词与准备阶段、用途交集筛选找到材料，并查看详情。', priority: 'must', checks: [
        { condition: '打开生成原型，保持默认筛选', expected: '显示三条合成材料，数量为 3 / 3', evidence_level: 'browser' },
        { condition: '搜索“晨光”，再清空搜索并选择“已备齐”与“绘画”', expected: '搜索时只显示晨光画纸；交集筛选时只显示小岛彩笔', evidence_level: 'browser' },
        { condition: '恢复全部后打开苔绿丝带详情', expected: '列表恢复三条，详情显示已备齐、装饰和件数 6', evidence_level: 'browser' }
      ] },
      rule: { statement: '关键词搜索与多个筛选条件按交集生效。', default: '默认显示全部三条合成材料。', exception: '没有匹配项时显示空结果与恢复全部入口。', boundary: '修改仅用于当前浏览器演示；刷新后重新载入源样例。' }, legacy_notes: []
    };
  }
  function insist(ok, message) { if (!ok) throw new Error(message); }
  function plain(value) { return value !== null && typeof value === 'object' && !Array.isArray(value); }
  function exactKeys(value, expected, label) { insist(plain(value) && Object.keys(value).length === expected.length && expected.every(key => Object.hasOwn(value, key)), label + '结构不符合本轮草案格式。'); }
  function text(value, limit, label) { insist(typeof value === 'string' && value.length <= limit, label + '需要合法文字且不能超过 ' + limit + ' 字。'); }
  function nativeDraft(payload) {
    const d = clone(payload);
    exactKeys(d, Object.keys(blankDraft()), '草案');
    insist(['collection', 'form'].includes(d.kind), '只接受集合或表单草案。');
    for (const key of ['title', 'audience', 'problem', 'positioning', 'value_hypothesis', 'goal', 'priority_basis', 'source_note']) text(d[key], key === 'title' ? 120 : 1000, key);
    insist(['synthetic', 'user-supplied'].includes(d.source_kind), '请保留明确的来源类型。');
    insist(Object.hasOwn(decisions, d.decision_status), '决定状态不受支持。');
    exactKeys(d.success_metric, ['statement', 'baseline', 'target', 'measurement'], '成功指标');
    for (const value of Object.values(d.success_metric)) text(value, 1000, '成功指标');
    for (const key of ['included', 'excluded', 'pending', 'legacy_notes']) { insist(Array.isArray(d[key]) && d[key].length <= 50, key + '最多 50 项。'); d[key].forEach(value => text(value, 1000, key)); }
    insist(Array.isArray(d.fields) && d.fields.length <= 16, '字段最多 16 个。');
    const keys = new Set();
    d.fields.forEach(f => {
      exactKeys(f, ['key', 'label', 'type', 'required', 'choices', 'minimum', 'maximum'], '字段');
      insist(typeof f.key === 'string' && /^[a-z][a-z0-9_]{0,39}$/.test(f.key) && !keys.has(f.key), '字段标识必须安全且唯一。'); keys.add(f.key);
      text(f.label, 80, '字段名称'); text(f.type, 40, '字段类型'); insist(Object.hasOwn(types, f.type), '字段类型 ' + f.type + ' 不受支持，请在原文件中明确修正为文本、数值、单选或标签；当前材料未替换。'); insist(typeof f.required === 'boolean', '必填需要布尔值。');
      insist(Array.isArray(f.choices) && f.choices.length <= 30, '选项最多 30 条。'); f.choices.forEach(value => text(value, 80, '选项'));
      [f.minimum, f.maximum].forEach(value => insist(value === null || (typeof value === 'number' && Number.isFinite(value)), '数值边界需要有限数值或 null。'));
      if (d.kind === 'collection') insist(f.minimum === null && f.maximum === null, '集合不支持数值上下限。请在原文件中明确修正；当前材料未替换。');
    });
    exactKeys(d.collection, ['search_fields', 'filters', 'layout', 'items'], '集合配置');
    for (const key of ['search_fields', 'filters']) { insist(Array.isArray(d.collection[key]) && d.collection[key].length <= 16, '搜索 / 筛选字段最多 16 个。'); d.collection[key].forEach(value => text(value, 40, '字段标识')); }
    insist(['sidebar', 'toolbar'].includes(d.collection.layout), '不支持的集合布局。');
    insist(Array.isArray(d.collection.items) && d.collection.items.length <= 500, '样例记录最多 500 条。');
    d.collection.items.forEach(item => { exactKeys(item, ['id', 'values'], '样例记录'); text(item.id, 40, '记录标识'); insist(plain(item.values), '样例值必须为对象。'); insist(Object.keys(item.values).every(key => keys.has(key)), '样例值包含未声明字段。'); });
    exactKeys(d.form, ['initial_values', 'initial_state'], '表单配置'); insist(plain(d.form.initial_values) && Object.keys(d.form.initial_values).every(key => keys.has(key)), '表单初值包含未声明字段。'); insist(d.form.initial_state === 'draft', '只接受初始为草稿的表单。');
    exactKeys(d.requirement, ['statement', 'priority', 'checks'], '主需求'); text(d.requirement.statement, 1000, '主需求'); insist(['must', 'should', 'could'].includes(d.requirement.priority), '不支持的优先级。');
    insist(Array.isArray(d.requirement.checks) && d.requirement.checks.length >= 1 && d.requirement.checks.length <= 20, '需保留 1–20 条检查。');
    d.requirement.checks.forEach(check => { exactKeys(check, ['condition', 'expected', 'evidence_level'], '检查'); text(check.condition, 450, '执行条件'); text(check.expected, 450, '预期结果'); insist(Object.hasOwn(levels, check.evidence_level), '不支持的证据层级。'); });
    exactKeys(d.rule, ['statement', 'default', 'exception', 'boundary'], '规则'); Object.values(d.rule).forEach(value => text(value, 1000, '规则'));
    return d;
  }
  function appendLegacyRecord(notes, label, value) {
    // Encode separators so each note stays a single line without changing the
    // decoded JSON content. Split on Unicode boundaries, never trim or truncate.
    const encoded = JSON.stringify(value).replace(/\u2028/g, '\\u2028').replace(/\u2029/g, '\\u2029');
    const chunks = []; let chunk = '';
    for (const character of encoded) {
      if (chunk.length + character.length > 900) { chunks.push(chunk); chunk = ''; }
      chunk += character;
    }
    if (chunk || !chunks.length) chunks.push(chunk);
    insist(notes.length + chunks.length <= 50, '旧材料完整留存需要超过 50 条备注。导入已拒绝，未截断原文，当前材料未替换；请先在原文件中明确精简。');
    chunks.forEach((part, index) => notes.push(label + ' [' + (index + 1) + '/' + chunks.length + ']：' + part));
  }
  function oldPrototypeDraft(payload) {
    insist(payload.type === 'pm-toolkit-workbench-draft' && payload.schema_version === '1.0' && payload.prototype_demo === true && payload.not_runtime_verified === true, '旧原型文件缺少可识别的格式与未实跑声明。');
    const s = payload.state; insist(plain(s) && plain(s.current), '旧原型缺少当前草案。');
    const old = s.current; const d = blankDraft();
    insist(['collection', 'form'].includes(old.kind), '旧原型载体类型不支持。'); d.kind = old.kind;
    for (const key of ['title', 'audience', 'problem', 'goal']) { text(old[key], key === 'title' ? 120 : 1000, key); d[key] = old[key]; }
    for (const key of ['included', 'excluded']) { text(old[key], 2000, key); d[key] = lines(old[key]); }
    insist(Array.isArray(old.fields) && old.fields.length <= 16, '旧原型字段最多 16 个。');
    d.fields = old.fields.map(f => ({ key: f.key, label: f.label, type: f.type, required: f.required, choices: Array.isArray(f.options) ? clone(f.options) : [], minimum: f.min ?? null, maximum: f.max ?? null }));
    d.collection.search_fields = d.fields.length ? [d.fields[0].key] : [];
    d.form.initial_values = Object.fromEntries(d.fields.map(f => [f.key, defaultValue(f.type)]));
    d.source_kind = 'user-supplied'; d.source_note = '使用者提供的旧版浏览器交互原型草案；prototype_demo 仅说明操作原型，不代表材料为合成。材料真实来源待确认，旧决定与观察均未认证。';
    d.pending = ['旧原型缺少产品定位、价值假设、优先级依据与成功指标，需明确补充', '旧原型缺少主需求、规则和逐条检查，需明确补充', '旧原型没有本轮样例记录，搜索默认列出首个字段待用户核对'];
    d.pending.push('旧原型材料来源尚未确认，请补充来源类型、真实来源与时点');
    if (Array.isArray(old.pending)) {
      insist(old.pending.length <= 40, '旧原型待补项过多。');
      old.pending.forEach(value => { text(value, 900, '旧原型待补项'); d.pending.push('旧原型待补：' + value); });
    }
    old.fields.forEach(f => {
      insist(f.pending === undefined || typeof f.pending === 'boolean', '旧原型逐字段待补标记无效。');
      if (f.pending === true) d.pending.push('旧原型字段待补：' + f.label + '（' + f.key + '）');
    });
    if (old.fieldsPending === true) d.pending.push('旧原型字段配置标记为待补，需逐项明确');
    d.decision_status = 'pending';
    d.legacy_notes = ['旧原型的全局观察和处理状态仅保留为待核验备注；本轮逐检查观察全部从未执行开始。'];
    if (s.observation !== undefined) {
      insist(plain(s.observation), '旧全局观察结构无效，未替换当前材料。');
      appendLegacyRecord(d.legacy_notes, '旧全局观察（未核验）', s.observation);
    }
    if (s.feedback !== undefined) {
      insist(Array.isArray(s.feedback) && s.feedback.length <= 30, '旧反馈最多 30 条；导入已拒绝，未截取记录，当前材料未替换。');
      s.feedback.forEach((row, index) => {
        insist(plain(row), '旧反馈结构无效，未替换当前材料。');
        appendLegacyRecord(d.legacy_notes, '旧反馈 ' + (index + 1) + '（需重新处理）', row);
      });
    }
    return nativeDraft(d);
  }
  async function importDraft(file) {
    if (!file || state.busy) return;
    try {
      insist(file.size <= 2 * 1024 * 1024, '导入文件最多 2 MB。当前材料未替换。');
      const payload = JSON.parse((await file.text()).replace(/^\ufeff/, ''));
      const legacy = payload.type === 'pm-toolkit-workbench-draft';
      const draft = legacy ? oldPrototypeDraft(payload) : nativeDraft(payload.format === 'pm-local-workbench-draft/v1' ? payload.draft : payload);
      if (!(await allowReplace('导入草案并替换当前材料？'))) return;
      resetLocal(draft); error('');
      notify(legacy ? '旧原型已转为未保存的本轮草案。缺失字段与原待补项继续保留，来源待确认；旧观察仅在备注中。' : '草案已读入当前编辑器，尚未保存到项目目录。请检查来源与决定状态后保存。', true);
    } catch (failure) { error('导入未成功，当前材料完整保留。' + failure.message); }
    finally { $('import-file').value = ''; }
  }
  function exportDraft() {
    const payload = { format: 'pm-local-workbench-draft/v1', draft: clone(state.draft) };
    const blob = new Blob([JSON.stringify(payload, null, 2) + '\n'], { type: 'application/json;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = el('a', { href: url, download: (state.draft.title || 'pm-task').replace(/[^\p{L}\p{N}_-]/gu, '_').slice(0, 60) + '-draft.json' });
    document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    notify('已导出当前原生草案 JSON。此文件只含编辑材料，不含会话令牌与观察通过记录；可再次导入恢复。');
  }
  document.querySelectorAll('[data-stage]').forEach(item => item.addEventListener('click', () => setStage(item.dataset.stage)));
  $('save-draft').addEventListener('click', saveDraft);
  $('reconnect').addEventListener('click', connect);
  $('project-select').addEventListener('change', event => loadProject(event.target.value));
  $('refresh-projects').addEventListener('click', async () => {
    if (!actionable()) return;
    try {
      const data = await api('/api/projects'); state.projects = data.projects || []; renderProjects();
      if (state.project) { const current = await api('/api/projects/' + state.project.id); installProject(current.project, true); renderAll(); notify('服务器状态已刷新；当前草案编辑与未提交记录保留。若与服务器不同，仍显示未保存。'); }
    } catch (failure) { showFailure(failure); }
  });
  $('new-project').addEventListener('click', async () => { if (!state.busy && await allowReplace('新建一份任务？')) { resetLocal(); state.saved = signature(state.draft); renderAll(); notify('已开始新任务，已有项目与历史版本仍保留。'); } });
  $('load-sample').addEventListener('click', async () => { if (!state.busy && await allowReplace('试填一份全新合成样例？')) { resetLocal(syntheticDraft()); notify('全新合成样例已填入，尚未保存。决定状态保留为待决；若你明确声明决定，请在来源与范围中选择后再保存。', true); } });
  $('import-json').addEventListener('click', () => { if (!state.busy) $('import-file').click(); });
  $('import-file').addEventListener('change', event => importDraft(event.target.files?.[0]));
  $('export-json').addEventListener('click', exportDraft);
  $('close-preview').addEventListener('click', () => $('preview-dialog').close());
  $('preview-dialog').addEventListener('close', () => { $('prototype-frame').src = 'about:blank'; });
  window.addEventListener('beforeunload', event => { if ((dirty() && (state.draftTick || state.project)) || state.feedbackDirty || state.observationDirty || state.busy) { event.preventDefault(); event.returnValue = ''; } });
  state.saved = signature(state.draft);
  renderAll();
  connect();
})();
