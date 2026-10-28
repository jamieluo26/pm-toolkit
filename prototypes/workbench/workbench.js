/* Browser-only demonstration. No runtime or pm_task input compatibility is claimed. */
(() => {
  'use strict';
  const FORMAT = 'pm-toolkit-workbench-draft';
  const VERSION = '1.0';
  const STORAGE_KEY = 'pm_toolkit_workbench_draft_v1';
  const PREF_KEY = 'pm_toolkit_workbench_storage_v1';
  const MAX_BYTES = 256 * 1024;
  const MAX_FIELDS = 16;
  const MAX_FEEDBACK = 30;
  const BASIC_KEYS = ['title', 'audience', 'problem', 'goal', 'included', 'excluded'];
  const LABELS = { title: '任务标题', audience: '面向谁', problem: '要解决的问题', goal: '这次希望达到什么', included: '本轮纳入范围', excluded: '本轮不做什么' };
  const TYPE_LABELS = { text: '短文本', longtext: '长文本', number: '数值', date: '日期', choice: '单选' };
  const DECISIONS = { pending: '待定', accepted: '采纳', rejected: '不采纳', conflict: '冲突' };
  const OBSERVATIONS = { unexecuted: '未执行', observed: '有观察', issues: '发现问题', retested: '已复验' };
  const $ = id => document.getElementById(id);
  const clone = value => JSON.parse(JSON.stringify(value));
  const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
  const freeze = value => {
    if (value && typeof value === 'object' && !Object.isFrozen(value)) {
      Object.values(value).forEach(freeze);
      Object.freeze(value);
    }
    return value;
  };
  const uid = prefix => prefix + '_' + Date.now().toString(36) + '_' + Math.random().toString(36).slice(2, 8);
  const dateText = value => new Date(value).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false });
  function node(tag, attrs = {}, children = []) {
    const item = document.createElement(tag);
    Object.entries(attrs).forEach(([key, value]) => {
      if (value === undefined || value === null) return;
      if (key === 'text') item.textContent = String(value);
      else if (key === 'class') item.className = value;
      else if (key === 'value') item.value = value;
      else if (key === 'checked' || key === 'disabled' || key === 'hidden' || key === 'readOnly') item[key] = value;
      else if (key.startsWith('on')) item.addEventListener(key.slice(2), value);
      else item.setAttribute(key, value);
    });
    (Array.isArray(children) ? children : [children]).forEach(child => {
      if (child !== null && child !== undefined) item.append(typeof child === 'string' ? document.createTextNode(child) : child);
    });
    return item;
  }
  const button = (text, onClick, className = 'button', attrs = {}) => node('button', { type: 'button', class: className, text, onclick: onClick, ...attrs });
  const pill = (text, mode = '') => node('span', { class: 'pill ' + mode, text });
  const emptySpec = () => ({ kind: 'collection', title: '', audience: '', problem: '', goal: '', included: '', excluded: '', pending: [], fieldsPending: false, fields: [] });
  const emptyState = () => ({ taskId: uid('task'), stage: 'create', current: emptySpec(), baseline: null, revision: null, feedback: [], observation: { status: 'unexecuted', text: '' } });
  let state = emptyState();
  let revisionTab = 'feedback';
  let storageAvailable = false;
  let storageEnabled = true;
  let storageFault = '';
  let savedAt = '';
  let savedSignature = JSON.stringify(state);
  let undoAction = null;
  let errors = [];
  const isDirty = () => JSON.stringify(state) !== savedSignature;
  const hasContent = () => state.baseline || state.current.fields.length || BASIC_KEYS.some(key => state.current[key].trim()) || state.current.pending.length || state.current.fieldsPending;

  function notice(text, warning = false) {
    $('persistent-notice').textContent = text;
    $('persistent-notice').className = 'notice' + (warning ? ' warning' : '');
    $('persistent-notice').hidden = !text;
  }
  function toast(text, undo = null) {
    undoAction = undo;
    $('toast-text').textContent = text;
    $('toast-undo').hidden = !undo;
    $('toast').hidden = false;
  }
  async function ask(title, message, action = '继续') {
    const dialog = $('confirm-dialog');
    if (dialog.open) return false;
    $('confirm-title').textContent = title;
    $('confirm-message').textContent = message;
    $('confirm-action').textContent = action;
    dialog.returnValue = '';
    return new Promise(resolve => {
      dialog.addEventListener('close', () => resolve(dialog.returnValue === 'confirm'), { once: true });
      dialog.showModal();
    });
  }
  function changed(content = true) {
    if (content) {
      state.revision = null;
      if (state.observation.status !== 'unexecuted' || state.observation.text.trim()) {
        state.observation = { status: 'unexecuted', text: '' };
        toast('任务或反馈已修改，上一轮观察已失效。请对新内容重新记录实际观察。');
      }
    }
    errors = [];
    $('validation-errors').hidden = true;
    updateSummary();
  }
  function focusStage() {
    $('main').focus({ preventScroll: true });
    $('main').scrollIntoView({ behavior: 'auto', block: 'start' });
  }
  function showErrors(list) {
    errors = list;
    const box = $('validation-errors');
    box.replaceChildren(node('strong', { text: '还有几处需要说明，已填内容都保留着。' }), node('ul', {}, list.map(error => node('li', {}, button(error.message, () => {
      if (error.tab && revisionTab !== error.tab) { revisionTab = error.tab; renderStage(); }
      const target = $(error.target);
      if (target) { target.scrollIntoView({ behavior: 'auto', block: 'center' }); target.focus({ preventScroll: true }); }
    }, '')))));
    box.hidden = false;
    box.scrollIntoView({ behavior: 'auto', block: 'center' });
  }

  // Strict format validation runs before any imported state is installed.
  function insist(test, message) { if (!test) throw new Error(message); }
  function object(value) { return value !== null && typeof value === 'object' && !Array.isArray(value) && Object.getPrototypeOf(value) === Object.prototype; }
  function keys(value, required, where) {
    insist(object(value), where + '应为对象。');
    insist(Object.keys(value).length === required.length && required.every(key => Object.hasOwn(value, key)), where + '的结构不符合本原型格式。');
  }
  function textValue(value, length, where) { insist(typeof value === 'string' && value.length <= length, where + '超出长度或不是文字。'); }
  function arrayValue(value, max, where) { insist(Array.isArray(value) && value.length <= max, where + '数量超出范围。'); }
  function identifier(value, where) { insist(typeof value === 'string' && /^[a-z][a-z0-9_]{1,79}$/.test(value), where + '的标识无效。'); }
  function dateValue(value, where) { insist(typeof value === 'string' && /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$/.test(value) && Number.isFinite(Date.parse(value)) && new Date(value).toISOString() === value, where + '的日期无效。'); }
  function validateSpec(spec, where) {
    keys(spec, ['kind', ...BASIC_KEYS, 'pending', 'fieldsPending', 'fields'], where);
    insist(['collection', 'form'].includes(spec.kind), where + '的任务类型无效。');
    BASIC_KEYS.forEach(key => textValue(spec[key], key === 'title' ? 120 : 2000, where + ' / ' + LABELS[key]));
    arrayValue(spec.pending, BASIC_KEYS.length, where + ' / 待补充项');
    insist(spec.pending.every(key => BASIC_KEYS.includes(key)) && new Set(spec.pending).size === spec.pending.length, where + '的待补充项无效或重复。');
    insist(typeof spec.fieldsPending === 'boolean', where + '的字段待补状态无效。');
    arrayValue(spec.fields, MAX_FIELDS, where + ' / 字段');
    const ids = new Set(), fieldKeys = new Set();
    spec.fields.forEach((field, index) => {
      const at = where + ' / 字段 ' + (index + 1);
      keys(field, ['id', 'key', 'label', 'type', 'required', 'min', 'max', 'options', 'pending'], at);
      identifier(field.id, at); identifier(field.key, at);
      insist(!ids.has(field.id) && !fieldKeys.has(field.key), at + '的标识重复。');
      ids.add(field.id); fieldKeys.add(field.key);
      textValue(field.label, 80, at + '名称');
      insist(Object.hasOwn(TYPE_LABELS, field.type), at + '的类型无效。');
      insist(typeof field.required === 'boolean' && typeof field.pending === 'boolean', at + '的勾选状态无效。');
      [field.min, field.max].forEach(value => insist(value === null || (typeof value === 'number' && Number.isFinite(value) && Math.abs(value) <= 1e9), at + '的数值边界无效（限正负十亿内）。'));
      insist(field.min === null || field.max === null || field.min <= field.max, at + '的最小值不能大于最大值。');
      insist(field.type === 'number' || (field.min === null && field.max === null), at + '仅数值类型可带数值边界。');
      arrayValue(field.options, 12, at + '的选项');
      field.options.forEach(value => { textValue(value, 80, at + '的选项'); insist(value.trim().length > 0, at + '含空选项。'); });
      insist(new Set(field.options).size === field.options.length, at + '的选项不能重复。');
      insist(field.type === 'choice' || field.options.length === 0, at + '仅单选类型可带选项。');
    });
  }
  function validateFeedback(items, where) {
    arrayValue(items, MAX_FEEDBACK, where);
    const ids = new Set();
    items.forEach((item, index) => {
      const at = where + ' ' + (index + 1);
      keys(item, ['id', 'text', 'source', 'decision', 'reason', 'changeId'], at);
      identifier(item.id, at); insist(!ids.has(item.id), at + '标识重复。'); ids.add(item.id);
      textValue(item.text, 2000, at + '内容'); textValue(item.source, 160, at + '来源'); textValue(item.reason, 1200, at + '理由'); textValue(item.changeId, 180, at + '关联变化');
      insist(Object.hasOwn(DECISIONS, item.decision), at + '的处理状态无效。');
    });
  }
  function validateEnvelope(payload) {
    keys(payload, ['type', 'schema_version', 'prototype_demo', 'not_runtime_verified', 'exported_at', 'state'], '文件');
    insist(payload.type === FORMAT, '这不是本原型的草案文件，未替换当前任务。');
    insist(payload.schema_version === VERSION, '草案版本不受支持；当前只读取 1.0。');
    insist(payload.prototype_demo === true && payload.not_runtime_verified === true, '文件缺少原型与未实跑标记，未替换当前任务。');
    dateValue(payload.exported_at, '文件');
    const s = payload.state;
    keys(s, ['taskId', 'stage', 'current', 'baseline', 'revision', 'feedback', 'observation'], '任务');
    identifier(s.taskId, '任务');
    insist(['create', 'revise', 'handoff'].includes(s.stage), '任务阶段无效。');
    validateSpec(s.current, '当前任务'); validateFeedback(s.feedback, '反馈');
    keys(s.observation, ['status', 'text'], '观察记录');
    insist(Object.hasOwn(OBSERVATIONS, s.observation.status), '观察状态无效。'); textValue(s.observation.text, 4000, '观察记录');
    if (s.baseline !== null) {
      keys(s.baseline, ['version', 'created_at', 'task'], '首版快照');
      insist(s.baseline.version === 'v1', '首版版本无效。'); dateValue(s.baseline.created_at, '首版'); validateSpec(s.baseline.task, '首版');
      insist(completeness(s.baseline.task).length === 0, '首版快照未满足最低说明要求。');
    } else {
      insist(s.stage === 'create' && s.revision === null && s.feedback.length === 0 && s.observation.status === 'unexecuted' && s.observation.text === '', '没有首版时不能包含修订或交接记录。');
    }
    if (s.revision !== null) {
      keys(s.revision, ['version', 'created_at', 'task', 'feedback'], '修订快照');
      insist(s.baseline !== null && s.revision.version === 'v1.1', '修订版本无效。');
      dateValue(s.revision.created_at, '修订'); validateSpec(s.revision.task, '修订'); validateFeedback(s.revision.feedback, '修订反馈');
      insist(same(s.current, s.revision.task) && same(s.feedback, s.revision.feedback), '修订快照与当前内容不一致。');
      insist(completeness(s.current).length === 0 && feedbackErrors(s).length === 0, '修订快照仍有缺失的决定依据。');
    }
    insist(s.stage !== 'handoff' || s.revision !== null, '交接阶段缺少修订快照。');
    return clone(s);
  }
  function envelope() {
    return { type: FORMAT, schema_version: VERSION, prototype_demo: true, not_runtime_verified: true, exported_at: new Date().toISOString(), state: clone(state) };
  }
  function completeness(spec) {
    const list = [];
    BASIC_KEYS.forEach(key => {
      if (!spec[key].trim() && !spec.pending.includes(key)) list.push({ message: LABELS[key] + '：请填写内容，或勾选「待补充」。', target: 'spec-' + key, tab: 'edit' });
    });
    if (!spec.fields.length && !spec.fieldsPending) list.push({ message: '信息字段：至少添加一个字段，或标记「字段待补充」。', target: 'add-field', tab: 'edit' });
    spec.fields.forEach((field, index) => {
      if (!field.label.trim() && !field.pending) list.push({ message: '字段 ' + (index + 1) + '：填写名称，或勾选「待补充」。', target: 'field-label-' + field.id, tab: 'edit' });
      if (field.type === 'choice' && field.options.length < 2 && !field.pending) list.push({ message: '字段 ' + (index + 1) + '：单选至少需要两个选项，或标记待补充。', target: 'field-options-' + field.id, tab: 'edit' });
      if (field.type === 'number' && field.min !== null && field.max !== null && field.min > field.max) list.push({ message: '字段 ' + (index + 1) + '：最小值不能大于最大值。', target: 'field-min-' + field.id, tab: 'edit' });
      if ((field.min !== null && Math.abs(field.min) > 1e9) || (field.max !== null && Math.abs(field.max) > 1e9)) list.push({ message: '字段 ' + (index + 1) + '：数值边界须在正负十亿内。', target: 'field-min-' + field.id, tab: 'edit' });
      if (field.options.length > 12 || field.options.some(item => item.length > 80) || new Set(field.options).size !== field.options.length) list.push({ message: '字段 ' + (index + 1) + '：选项最多12个，每项80字以内，且不能重复。', target: 'field-options-' + field.id, tab: 'edit' });
    });
    return list;
  }

  function displayValue(value) {
    if (value === null) return '未设置';
    if (typeof value === 'boolean') return value ? '是' : '否';
    if (Array.isArray(value)) return value.length ? value.join('、') : '未设置';
    return value === '' || value === undefined ? '未填写' : String(value);
  }
  function differences(s = state) {
    if (!s.baseline) return [];
    const old = s.baseline.task, current = s.current, list = [];
    const add = (id, label, before, after) => { if (!same(before, after)) list.push({ id, label, before: displayValue(before), after: displayValue(after) }); };
    add('kind', '任务形态', old.kind === 'form' ? '申请表单' : '集合列表', current.kind === 'form' ? '申请表单' : '集合列表');
    BASIC_KEYS.forEach(key => { add(key, LABELS[key], old[key], current[key]); add(key + '_pending', LABELS[key] + ' · 待补状态', old.pending.includes(key), current.pending.includes(key)); });
    add('fields_pending', '信息字段 · 待补状态', old.fieldsPending, current.fieldsPending);
    const beforeIds = old.fields.map(field => field.id), afterIds = current.fields.map(field => field.id);
    old.fields.forEach(field => {
      if (!afterIds.includes(field.id)) list.push({ id: 'remove_' + field.id, label: '移除字段 · ' + (field.label || '待补充字段'), before: (field.label || '待补充字段') + ' / ' + TYPE_LABELS[field.type], after: '已移除' });
    });
    current.fields.forEach((field, index) => {
      const before = old.fields.find(item => item.id === field.id);
      const name = field.label || '字段 ' + (index + 1);
      if (!before) list.push({ id: 'add_' + field.id, label: '新增字段 · ' + name, before: '无此字段', after: name + ' / ' + TYPE_LABELS[field.type] + (field.required ? ' / 必填' : ' / 选填') + (field.pending ? ' / 待补充' : '') + (field.type === 'number' ? ' / 范围：' + displayValue(field.min) + ' 至 ' + displayValue(field.max) : '') + (field.type === 'choice' ? ' / 选项：' + displayValue(field.options) : '') });
      else {
        add('field_' + field.id + '_label', '字段名称 · ' + (before.label || name), before.label, field.label);
        add('field_' + field.id + '_type', '字段类型 · ' + name, TYPE_LABELS[before.type], TYPE_LABELS[field.type]);
        [['required', '是否必填'], ['min', '最小值'], ['max', '最大值'], ['options', '选项'], ['pending', '是否待补充']].forEach(([key, label]) => add('field_' + field.id + '_' + key, name + ' · ' + label, before[key], field[key]));
        add('field_' + field.id + '_key', '字段内部标识 · ' + name, before.key, field.key);
      }
    });
    if (same([...beforeIds].sort(), [...afterIds].sort()) && !same(beforeIds, afterIds)) list.push({ id: 'fields_order', label: '字段顺序', before: old.fields.map(field => field.label || '待补充字段').join(' → '), after: current.fields.map(field => field.label || '待补充字段').join(' → ') });
    return list;
  }
  function feedbackErrors(s = state) {
    const changeIds = new Set(differences(s).map(change => change.id)), list = [];
    s.feedback.forEach((item, index) => {
      if (!item.text.trim()) list.push({ message: '反馈 ' + (index + 1) + '：请填写反馈内容，或移除这张空卡。', target: 'feedback-text-' + item.id, tab: 'feedback' });
      if (!item.source.trim()) list.push({ message: '反馈 ' + (index + 1) + '：请说明来源；尚未确认可写「来源待补充」。', target: 'feedback-source-' + item.id, tab: 'feedback' });
      if (['accepted', 'rejected'].includes(item.decision) && !item.reason.trim()) list.push({ message: '反馈 ' + (index + 1) + '：' + DECISIONS[item.decision] + '需要说明理由。', target: 'feedback-reason-' + item.id, tab: 'feedback' });
      if (item.decision === 'accepted' && !changeIds.has(item.changeId)) list.push({ message: '反馈 ' + (index + 1) + '：采纳需要关联一条当前实际变化，请先修改任务再选择。', target: 'feedback-change-' + item.id, tab: 'feedback' });
    });
    return list;
  }
  function pendingItems(s = state) {
    const result = s.current.pending.map(key => LABELS[key] + '待补充');
    BASIC_KEYS.forEach(key => { if (!s.current[key].trim() && !s.current.pending.includes(key)) result.push(LABELS[key] + '尚未填写'); });
    if (s.current.fieldsPending) result.push('信息字段定义待补充');
    if (!s.current.fields.length && !s.current.fieldsPending) result.push('信息字段尚未定义');
    s.current.fields.forEach((field, index) => { if (field.pending || !field.label.trim()) result.push((field.label || '字段 ' + (index + 1)) + '待补充'); });
    s.feedback.forEach((item, index) => { if (['pending', 'conflict'].includes(item.decision)) result.push('反馈 ' + (index + 1) + ' · ' + DECISIONS[item.decision] + '：' + (item.text || '内容待补充')); if (!item.source.trim() || item.source.trim() === '来源待补充') result.push('反馈 ' + (index + 1) + '的来源待补充'); });
    if (s.baseline) {
      if (!differences(s).length) result.push('尚无任务内容变化，请核对本次修订意图');
      if (s.observation.status === 'unexecuted') result.push('尚未执行实际检查');
      else if (!s.observation.text.trim()) result.push('人工观察缺少记录');
      if (s.observation.status === 'issues') result.push('人工观察记录中仍有问题，需后续复验');
    }
    return result;
  }

  function updateSummary() {
    const spec = state.current, diff = differences(), pending = pendingItems();
    $('summary-title').textContent = spec.title || '你的下一份产品任务';
    $('summary-kind').textContent = (spec.kind === 'form' ? '申请表单' : '集合列表') + ' · ' + (state.baseline ? '同一任务，继续修订' : '从一个具体问题开始');
    $('summary-version').textContent = state.baseline ? (state.revision ? 'v1.1 草案' : 'v1.1 修订中') : '首版草案';
    $('summary-fields').textContent = spec.fields.length + ' 个';
    $('summary-changes').textContent = state.baseline ? diff.length + ' 处' : '—';
    $('summary-pending').textContent = pending.length + ' 项';
    $('summary-pending').className = pending.length ? 'has-pending' : '';
    $('summary-note').textContent = state.baseline ? (state.stage === 'handoff' ? '这是一份交接草案。请接手人核对内容与未决项，实际检查另外确认。' : '首版 v1 已保留。每一次修改都会和首版比较，反馈决定单独记录。') : '先形成首版，再讨论修改。后续修订会保留首版内容。';
    $('version-trail').replaceChildren(...(state.baseline ? [node('b', { text: 'v1 已保留' }), node('span', { text: '→' }), node('b', { text: state.revision ? 'v1.1 草案' : 'v1.1 修订中' })] : [node('span', { text: '首版尚未形成' })]));
    $('save-status').textContent = isDirty() ? '有未保存修改' : (savedAt ? '已保存 ' + dateText(savedAt) : '尚未保存');
    $('save-status').className = 'save-status' + (isDirty() ? ' dirty' : '');
    const available = storageAvailable && storageEnabled;
    $('storage-title').textContent = !storageAvailable ? '浏览器留存不可用' : (storageEnabled ? '浏览器留存已开启' : '浏览器留存已关闭');
    $('storage-description').textContent = !storageAvailable ? '此浏览器未允许保存。当前内容只在本页，请导出草案文件另行留存。' : storageEnabled ? '点击「保存草案」后，可在这个浏览器中恢复。导出文件能帮助你另外留一份。' : '当前内容只在本页；离开前请导出草案。也可重新开启浏览器留存。';
    $('storage-dot').className = 'storage-dot' + (available ? '' : ' off');
    $('toggle-storage').textContent = available ? '关闭留存' : '开启留存';
    $('step-create-state').textContent = state.baseline ? '首版已保留' : '进行中';
    $('step-revise-state').textContent = state.revision ? '已整理' : state.baseline ? '修订中' : '待开始';
    $('step-handoff-state').textContent = state.revision ? '交接草案' : '待开始';
    document.querySelectorAll('[data-stage]').forEach(item => {
      const active = item.dataset.stage === state.stage;
      item.classList.toggle('active', active);
      item.classList.toggle('past', !!state.baseline && item.dataset.stage === 'create');
      if (active) item.setAttribute('aria-current', 'step'); else item.removeAttribute('aria-current');
    });
    if (state.stage === 'handoff') updateHandoffStatus();
  }

  function sectionHead(number, title, description, action = null) {
    return node('div', { class: 'section-title' }, [node('div', {}, [node('h2', { text: title }), node('p', { text: description })]), action || node('span', { class: 'section-index', text: number })]);
  }
  function basicField(key, placeholder, wide = false) {
    const spec = state.current;
    const group = node('div', { class: 'field-group' + (wide ? ' wide' : '') + (spec.pending.includes(key) ? ' pending-input' : '') });
    const pending = node('input', { type: 'checkbox', checked: spec.pending.includes(key), 'aria-label': LABELS[key] + '待补充', onchange: event => {
      if (event.target.checked) spec.pending.push(key); else spec.pending = spec.pending.filter(item => item !== key);
      group.classList.toggle('pending-input', event.target.checked); changed();
    } });
    const label = node('label', { for: 'spec-' + key }, [LABELS[key], node('span', { class: 'required-mark', text: '·' })]);
    group.append(node('div', { class: 'field-label' }, [label, node('label', { class: 'pending-check' }, [pending, '待补充'])]));
    const input = node(key === 'title' ? 'input' : 'textarea', { id: 'spec-' + key, value: spec[key], maxlength: key === 'title' ? 120 : 2000, placeholder, rows: key === 'audience' ? 2 : 3, class: key === 'audience' ? 'short' : '', oninput: event => { spec[key] = event.target.value; changed(); } });
    group.append(input);
    if (key === 'title') group.append(node('p', { class: 'field-hint', text: '一个具体、容易被记住的名字。最多 120 字。' }));
    return group;
  }
  async function setKind(kind) {
    if (state.current.kind === kind) return;
    if (hasContent() && !await ask('切换任务形态？', '已填的背景、范围和字段都会保留；切换后请重新核对字段是否适合。', '保留内容并切换')) return;
    state.current.kind = kind; changed(); renderStage();
  }
  function nextField() {
    const used = new Set(state.current.fields.map(field => field.key));
    let index = 1;
    while (used.has('field_' + String(index).padStart(2, '0'))) index++;
    return { id: uid('f'), key: 'field_' + String(index).padStart(2, '0'), label: '', type: 'text', required: false, min: null, max: null, options: [], pending: false };
  }
  function addField() {
    if (state.current.fields.length >= MAX_FIELDS) return toast('这一版最多配置 16 个字段。');
    const field = nextField(); state.current.fields.push(field); changed(); renderStage();
    $('field-label-' + field.id)?.focus({ preventScroll: false });
    toast('已新增一个空白字段。', () => { state.current.fields = state.current.fields.filter(item => item.id !== field.id); changed(); renderStage(); });
  }
  function removeField(id) {
    const index = state.current.fields.findIndex(item => item.id === id), field = clone(state.current.fields[index]);
    state.current.fields.splice(index, 1); changed(); renderStage();
    toast('已移除「' + (field.label || '未命名字段') + '」。', () => {
      if (state.current.fields.length >= MAX_FIELDS || state.current.fields.some(item => item.key === field.key)) return toast('当前字段数量或标识已变化，无法直接撤销；可从已存草案恢复。');
      state.current.fields.splice(index, 0, field); changed(); renderStage();
    });
  }
  function fieldEditor(field, index) {
    const card = node('div', { class: 'field-config' });
    const pending = node('input', { type: 'checkbox', checked: field.pending, 'aria-label': '字段 ' + (index + 1) + '待补充', onchange: event => { field.pending = event.target.checked; changed(); } });
    card.append(node('div', { class: 'field-config-head' }, [node('span', { class: 'field-counter', text: '字段 ' + String(index + 1).padStart(2, '0') }), node('div', { class: 'field-config-tools' }, [node('label', { class: 'pending-check' }, [pending, '待补充']), button('移除', () => removeField(field.id), 'delete-button')])]));
    const name = node('div', {}, [node('label', { class: 'mini-label', for: 'field-label-' + field.id, text: '字段名称' }), node('input', { id: 'field-label-' + field.id, value: field.label, maxlength: 80, placeholder: '例如：反馈主题', oninput: event => { field.label = event.target.value; changed(); } })]);
    const typeSelect = node('select', { id: 'field-type-' + field.id, 'aria-label': '字段 ' + (index + 1) + '类型' }, Object.entries(TYPE_LABELS).map(([value, label]) => node('option', { value, text: label })));
    typeSelect.value = field.type;
    typeSelect.addEventListener('change', async () => {
      const previous = field.type, next = typeSelect.value;
      if (((previous === 'number' && (field.min !== null || field.max !== null)) || (previous === 'choice' && field.options.length)) && !await ask('切换字段类型？', '切换后会清除这个字段现有的数值边界或单选选项，字段名称与必填设置会保留。', '切换类型')) { typeSelect.value = previous; return; }
      field.type = next; field.min = null; field.max = null; field.options = []; changed(); renderStage();
    });
    card.append(node('div', { class: 'field-config-grid' }, [name, node('div', {}, [node('label', { class: 'mini-label', for: typeSelect.id, text: '填写方式' }), typeSelect]), node('label', { class: 'required-toggle' }, [node('input', { type: 'checkbox', checked: field.required, 'aria-label': '字段 ' + (index + 1) + '必填', onchange: event => { field.required = event.target.checked; changed(); } }), '必填'])]));
    if (field.type === 'number') {
      card.append(node('div', { class: 'number-bounds' }, ['min', 'max'].map(key => node('div', {}, [node('label', { class: 'mini-label', for: 'field-' + key + '-' + field.id, text: (key === 'min' ? '最小值' : '最大值') + '（选填）' }), node('input', { type: 'number', step: 'any', min: -1e9, max: 1e9, id: 'field-' + key + '-' + field.id, value: field[key] === null ? '' : field[key], placeholder: '不限', oninput: event => { field[key] = event.target.value === '' ? null : event.target.valueAsNumber; if (!Number.isFinite(field[key])) field[key] = null; changed(); } })]))));
    }
    if (field.type === 'choice') card.append(node('div', { class: 'field-group', style: 'margin-top:12px' }, [node('label', { class: 'mini-label', for: 'field-options-' + field.id, text: '可选内容（每行一项，最多 12 项）' }), node('textarea', { id: 'field-options-' + field.id, rows: 3, maxlength: 1000, value: field.options.join('\n'), placeholder: '待处理\n跟进中\n已回复', oninput: event => { field.options = event.target.value.split(/\r?\n/).map(value => value.trim()).filter(Boolean); changed(); } })]));
    return card;
  }
  function specEditor() {
    const card = node('div', { class: 'editor-card' });
    const typeSection = node('section', { class: 'editor-section' }, [sectionHead('01', '这次要做什么？', '先选一种任务形态，之后也可以调整。'), node('div', { class: 'type-options' }, ['collection', 'form'].map(kind => button('', () => setKind(kind), 'type-option' + (state.current.kind === kind ? ' selected' : ''), { 'aria-pressed': String(state.current.kind === kind), 'aria-label': kind === 'form' ? '申请表单' : '集合列表' }))) ]);
    [...typeSection.querySelectorAll('.type-option')].forEach((item, index) => item.append(node('span', { class: 'type-symbol', 'aria-hidden': 'true', text: index === 0 ? '☷' : '▤' }), node('span', {}, [node('strong', { text: index === 0 ? '集合列表' : '申请表单' }), node('small', { text: index === 0 ? '整理、查找一组信息' : '收集一份完整的请求' })]), node('span', { class: 'radio-mark', 'aria-hidden': 'true' })));
    card.append(typeSection);
    card.append(node('section', { class: 'editor-section' }, [sectionHead('02', '把问题与目标写下来', '确定的写清楚；不确定的，可以先标记待补充。'), node('div', { class: 'form-grid' }, [basicField('title', '例如：客户反馈跟进台', true), basicField('audience', '谁会使用？在什么情况下使用？'), basicField('problem', '现在怎么做？最不顺的地方是什么？'), basicField('goal', '这一轮做完，希望使用者能做到什么？', true)])]));
    card.append(node('section', { class: 'editor-section' }, [sectionHead('03', '给这一轮画个边界', '写下会做什么，也说清楚暂时不做什么。'), node('div', { class: 'form-grid' }, [basicField('included', '例如：记录反馈、标记处理状态、查看跟进记录'), basicField('excluded', '例如：自动回复、多人权限、与外部系统同步')])]));
    const fieldSection = node('section', { class: 'editor-section' }, [sectionHead('04', '需要记录哪些信息？', '像搭表格一样添加字段，内部标识会自动维护。', node('span', { class: 'limit-counter', text: state.current.fields.length + ' / ' + MAX_FIELDS }))]);
    if (state.current.fields.length) state.current.fields.forEach((field, index) => fieldSection.append(fieldEditor(field, index)));
    else fieldSection.append(node('div', { class: 'empty-fields' }, [node('span', { class: 'empty-icon', 'aria-hidden': 'true', text: '⊞' }), node('p', { text: '从你想收集的第一项信息开始。' }), button('＋ 添加一个字段', addField, 'button small', { id: 'empty-add-field' })]));
    fieldSection.append(node('div', { class: 'field-actions' }, [button('＋ 添加字段', addField, 'button small', { id: 'add-field', disabled: state.current.fields.length >= MAX_FIELDS }), node('label', { class: 'pending-check' }, [node('input', { type: 'checkbox', checked: state.current.fieldsPending, onchange: event => { state.current.fieldsPending = event.target.checked; changed(); } }), '字段待补充'])]), node('p', { class: 'subtle-note', text: '字段只用于表达需求。这里不会生成真实业务页面，也不会向任何服务提交数据。' }));
    card.append(fieldSection);
    return card;
  }
  function snapshotView() {
    const spec = state.baseline.task;
    const surface = node('div', { class: 'snapshot-surface' }, [node('div', { class: 'snapshot-banner' }, [node('span', { class: 'snapshot-symbol', 'aria-hidden': 'true', text: '▧' }), node('div', {}, [node('b', { text: '首版 v1 已保留，内容不会随修订改变。' }), node('p', { text: '形成于 ' + dateText(state.baseline.created_at) + '。新的想法请在「修订」中继续编辑。' })])]), node('div', { class: 'snapshot-grid' }, BASIC_KEYS.map(key => node('div', { class: 'snapshot-item' + (key === 'title' || key === 'goal' ? ' wide' : '') }, [node('small', { text: LABELS[key] + (spec.pending.includes(key) ? ' · 待补充' : '') }), node('p', { text: spec[key] || '待补充' })])))]);
    const fields = node('div', { class: 'snapshot-fields' }, [node('p', { class: 'frozen-note', text: (spec.kind === 'form' ? '申请表单' : '集合列表') + ' · ' + spec.fields.length + ' 个字段' + (spec.fieldsPending ? ' · 字段定义待补充' : '') })]);
    spec.fields.forEach(field => fields.append(node('div', { class: 'snapshot-field' }, [node('span', { text: field.label || '待补充字段' }), ...(field.required ? [pill('必填')] : []), ...(field.pending ? [pill('待补充', 'amber')] : []), node('small', { text: TYPE_LABELS[field.type] + (field.type === 'number' ? ' / ' + displayValue(field.min) + ' 至 ' + displayValue(field.max) : '') })])));
    surface.append(fields); return surface;
  }
  function addFeedback() {
    if (state.feedback.length >= MAX_FEEDBACK) return toast('本轮最多记录 30 条反馈。');
    const item = { id: uid('fb'), text: '', source: '', decision: 'pending', reason: '', changeId: '' };
    state.feedback.push(item); changed(); renderStage();
    $('feedback-text-' + item.id)?.focus({ preventScroll: false });
    toast('已新增一张反馈卡。', () => { state.feedback = state.feedback.filter(feedback => feedback.id !== item.id); changed(); renderStage(); });
  }
  function removeFeedback(id) {
    const index = state.feedback.findIndex(item => item.id === id), item = clone(state.feedback[index]);
    state.feedback.splice(index, 1); changed(); renderStage();
    toast('已移除反馈 ' + (index + 1) + '。', () => { if (state.feedback.length >= MAX_FEEDBACK) return toast('当前反馈已达 30 条，无法撤销。'); state.feedback.splice(index, 0, item); changed(); renderStage(); });
  }
  function feedbackCard(item, index) {
    const card = node('article', { class: 'feedback-card' });
    card.append(node('div', { class: 'feedback-header' }, [node('strong', { text: '反馈 ' + String(index + 1).padStart(2, '0') }), button('移除', () => removeFeedback(item.id), 'delete-button')]));
    card.append(node('div', { class: 'field-group' }, [node('label', { for: 'feedback-text-' + item.id, text: '反馈说了什么？' }), node('textarea', { id: 'feedback-text-' + item.id, maxlength: 2000, value: item.text, rows: 3, placeholder: '尽量记录具体问题或期待，先不急着给结论。', oninput: event => { item.text = event.target.value; changed(); } })]));
    const decision = node('select', { id: 'feedback-decision-' + item.id }, Object.entries(DECISIONS).map(([value, label]) => node('option', { value, text: label })));
    decision.value = item.decision;
    decision.addEventListener('change', () => { item.decision = decision.value; changed(); renderStage(); });
    card.append(node('div', { class: 'feedback-meta' }, [node('div', { class: 'field-group' }, [node('label', { for: 'feedback-source-' + item.id, text: '来自哪里？' }), node('input', { id: 'feedback-source-' + item.id, maxlength: 160, value: item.source, placeholder: '例如：合成评审记录 / 来源待补充', oninput: event => { item.source = event.target.value; changed(); } })]), node('div', { class: 'field-group' }, [node('label', { for: decision.id, text: '这次如何处理？' }), decision])]));
    const reasonLabel = item.decision === 'pending' ? '先记下考虑或待确认的问题（选填）' : item.decision === 'conflict' ? '冲突在哪里？接下来要确认什么？（选填）' : '为什么这样处理？';
    card.append(node('div', { class: 'field-group' }, [node('label', { for: 'feedback-reason-' + item.id, text: reasonLabel }), node('textarea', { id: 'feedback-reason-' + item.id, maxlength: 1200, value: item.reason, rows: 2, placeholder: ['accepted', 'rejected'].includes(item.decision) ? '采纳与不采纳，都需要留下具体理由。' : '可以保留待定，交接时会单独列出。', oninput: event => { item.reason = event.target.value; changed(); } })]));
    if (item.decision === 'accepted') {
      const diff = differences(), select = node('select', { id: 'feedback-change-' + item.id }, [node('option', { value: '', text: diff.length ? '选择这条反馈对应的实际变化' : '先修改任务，才会出现可关联的变化' }), ...diff.map(change => node('option', { value: change.id, text: change.label }))]);
      select.value = diff.some(change => change.id === item.changeId) ? item.changeId : '';
      select.addEventListener('change', () => { item.changeId = select.value; changed(); });
      card.append(node('div', { class: 'field-group' }, [node('label', { for: select.id, text: '对应哪一处实际修改？' }), select]));
      if (!diff.length) card.append(node('p', { class: 'feedback-note' }, ['采纳需要有实际变化。', button('去修改任务 ↗', () => { revisionTab = 'edit'; renderStage(); }, 'inline-button')]));
    } else if (['pending', 'conflict'].includes(item.decision)) card.append(node('p', { class: 'feedback-note', text: item.decision === 'conflict' ? '冲突会保留为未决项，需要人工协调后再确认。' : '待定不会被视为已处理；它会跟随交接草案一起保留。' }));
    return card;
  }
  function feedbackView() {
    const surface = node('section', { class: 'feedback-surface' }, [node('div', { class: 'feedback-top' }, [node('div', {}, [node('h2', { text: '让每一条反馈，都有去向。' }), node('p', { text: '记录原话与来源，再决定要改什么、为什么。' })]), button('＋ 添加反馈', addFeedback, 'button small', { disabled: state.feedback.length >= MAX_FEEDBACK })])]);
    if (!state.feedback.length) surface.append(node('div', { class: 'empty-feedback' }, [node('span', { class: 'empty-icon', 'aria-hidden': 'true', text: '☷' }), node('h3', { text: '从一次具体的讨论开始。' }), node('p', { text: '这里还没有反馈。你可以添加一条，也可以先修改任务；没有结论的内容保留待定。' }), button('记录第一条反馈', addFeedback, 'button small')]));
    else state.feedback.forEach((item, index) => surface.append(feedbackCard(item, index)));
    return surface;
  }
  function diffList(items) {
    return node('ul', { class: 'diff-list' }, items.map(change => node('li', { class: 'diff-item' }, [node('p', { class: 'diff-label', text: change.label }), node('div', { class: 'diff-values' }, [node('div', { class: 'diff-value' }, [node('small', { text: '首版 v1' }), change.before]), node('div', { class: 'diff-value new' }, [node('small', { text: '当前 v1.1' }), change.after])])])));
  }
  function changesView() {
    const diff = differences();
    const surface = node('section', { class: 'feedback-surface' }, [node('div', { class: 'diff-overview' }, [node('h2', { text: '和首版相比，改了什么？' }), pill(diff.length + ' 处变化')])]);
    if (diff.length) surface.append(diffList(diff));
    else surface.append(node('div', { class: 'empty-diff' }, [node('h3', { text: '还没有任务内容变化。' }), node('p', { text: '反馈卡会单独保留；实际任务变化从当前内容自动比较。' }), button('去修改任务 ↗', () => { revisionTab = 'edit'; renderStage(); }, 'button small')]));
    surface.append(node('p', { class: 'subtle-note', text: '这是本页面按字段计算的内容比较，便于人工核对；不代表实际工具审计或业务验收。' }));
    return surface;
  }
  function handoffStatus() {
    const pending = pendingItems();
    return pending.length ? { title: '待补充 / 含未决项', note: '可以导出交接草案。还有 ' + pending.length + ' 项需要后续确认，未标记为全部完成。', pending } : { title: '可供核对的交接草案', note: '已记录给定信息与人工观察；仍需接手人核对，不代表工具认证或业务验收。', pending };
  }
  function updateHandoffStatus() {
    if (!$('handoff-status-title')) return;
    const status = handoffStatus();
    $('handoff-status-title').textContent = status.title;
    $('handoff-status-note').textContent = status.note;
    $('handoff-status').className = 'handoff-status' + (status.pending.length ? '' : ' neutral');
    $('handoff-pending-list').replaceChildren(...(status.pending.length ? status.pending.map(text => node('li', { text })) : [node('li', { text: '当前未登记待补项；实际完整性仍需人工核对。' })]));
    const observation = $('observation-current-status');
    if (observation) observation.textContent = state.observation.status === 'unexecuted' ? '尚未执行实际检查' : OBSERVATIONS[state.observation.status] + ' · 仅为人工记录';
  }
  function handoffView() {
    const surface = node('div', { class: 'handoff-surface' });
    surface.append(node('div', { class: 'handoff-status', id: 'handoff-status' }, [node('b', { id: 'handoff-status-title' }), node('p', { id: 'handoff-status-note' })]));
    surface.append(node('div', { class: 'version-comparison' }, [node('div', {}, [node('small', { text: '保留的首版' }), node('strong', { text: 'v1' }), node('p', { text: dateText(state.baseline.created_at) })]), node('span', { 'aria-hidden': 'true', text: '→' }), node('div', {}, [node('small', { text: '本轮修订草案' }), node('strong', { text: 'v1.1' }), node('p', { text: dateText(state.revision.created_at) })])]));
    const diff = differences();
    surface.append(node('section', { class: 'handoff-block' }, [node('h3', { text: '01 / 本轮发生的变化' }), ...(diff.length ? [diffList(diff)] : [node('p', { text: '尚无任务内容变化。请在交接时说明本轮修订意图。' })])]));
    const feedback = node('section', { class: 'handoff-block' }, [node('h3', { text: '02 / 反馈去了哪里' })]);
    if (!state.feedback.length) feedback.append(node('p', { text: '本轮未登记反馈。' }));
    state.feedback.forEach((item, index) => {
      const associated = diff.find(change => change.id === item.changeId);
      feedback.append(node('div', { class: 'feedback-outcome' }, [node('div', {}, [node('p', { text: (index + 1) + '. ' + item.text }), node('small', { text: '来源：' + item.source }), node('small', { text: '理由 / 考虑：' + (item.reason || '尚未填写') }), ...(associated && item.decision === 'accepted' ? [node('small', { text: '关联变化：' + associated.label })] : [])]), pill(DECISIONS[item.decision], ['pending', 'conflict'].includes(item.decision) ? 'amber' : 'muted')]));
    });
    surface.append(feedback, node('section', { class: 'handoff-block' }, [node('h3', { text: '03 / 继续接住的待补事项' }), node('ul', { id: 'handoff-pending-list' })]));
    const select = node('select', { id: 'observation-status' }, Object.entries(OBSERVATIONS).map(([value, label]) => node('option', { value, text: label })));
    select.value = state.observation.status;
    select.addEventListener('change', () => { state.observation.status = select.value; changed(false); });
    surface.append(node('section', { class: 'handoff-block observation-form' }, [node('h3', { text: '04 / 人工观察与实际检查' }), node('p', { id: 'observation-current-status' }), node('label', { for: select.id, text: '目前记录到哪一步？' }), select, node('label', { for: 'observation-text', text: '观察到了什么？还有哪些限制？' }), node('textarea', { id: 'observation-text', maxlength: 4000, rows: 4, value: state.observation.text, placeholder: '请记录操作、看到的现象、问题与复验结果。尚未实际检查可留空。', oninput: event => { state.observation.text = event.target.value; changed(false); } }), node('p', { class: 'subtle-note', text: '此处仅记录你提供的观察，不会执行检查，也不认证审批、测试或业务验收。' })]));
    surface.append(node('section', { class: 'handoff-block' }, [node('h3', { text: '交出去之前，留一份可继续的材料。' }), node('p', { text: 'JSON 用于回到本原型继续编辑；Markdown 适合交给下一位阅读。文件会保留原型与未实跑标记。' }), node('div', { class: 'handoff-actions' }, [button('下载交接 Markdown ↓', exportMarkdown, 'button primary', { id: 'download-handoff' }), button('下载草案 JSON ↓', exportJSON, 'button')])]));
    return surface;
  }

  function renderStage() {
    const content = $('stage-content'); content.replaceChildren();
    $('load-sample').hidden = !!state.baseline;
    if (state.stage === 'create') {
      $('stage-eyebrow').textContent = state.baseline ? 'A CLEAR PLACE TO START' : 'YOUR NEXT PRODUCT DECISION';
      $('stage-title').textContent = state.baseline ? '首版留在这里，修改向前走。' : '先把问题，说清楚。';
      $('stage-description').textContent = state.baseline ? '这份首版作为后续讨论的参照，不会随新一轮编辑改变。' : '不用先想完整。把确定的写下来，没确定的留作待补充。';
      content.append(state.baseline ? snapshotView() : specEditor());
      content.append(node('div', { class: 'stage-actions' }, [node('p', { text: state.baseline ? '首版已保留，当前修订内容也会保留。' : '形成首版后会留下一份不可变快照，之后的修改都进入修订版。' }), button(state.baseline ? '继续修订 →' : '形成首版，进入修订 →', state.baseline ? () => navigate('revise') : createFirstVersion, 'button primary', { id: 'create-version' })]));
    } else if (state.stage === 'revise') {
      $('stage-eyebrow').textContent = 'MAKE THE NEXT VERSION CLEARER';
      $('stage-title').textContent = '把反馈，变成有依据的修改。';
      $('stage-description').textContent = '首版 v1 已保留。这一轮形成 v1.1，待定与冲突会继续被看见。';
      const tabs = node('div', { class: 'tabs', role: 'tablist', 'aria-label': '修订工作区' });
      [['feedback', '反馈与去向', state.feedback.length], ['edit', '修改任务', ''], ['diff', '查看变化', differences().length]].forEach(([key, label, count]) => {
        const tab = button(label, () => { revisionTab = key; renderStage(); }, 'tab' + (revisionTab === key ? ' active' : ''), { role: 'tab', 'aria-selected': String(revisionTab === key), id: 'tab-' + key, 'aria-controls': 'revision-panel' });
        if (count !== '') tab.append(node('span', { class: 'tab-count', text: count }));
        tabs.append(tab);
      });
      tabs.addEventListener('keydown', event => {
        if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
        event.preventDefault(); const order = ['feedback', 'edit', 'diff'];
        const index = order.indexOf(revisionTab);
        revisionTab = event.key === 'Home' ? order[0] : event.key === 'End' ? order[2] : order[(index + (event.key === 'ArrowRight' ? 1 : 2)) % 3];
        renderStage(); $('tab-' + revisionTab).focus();
      });
      content.append(tabs, node('div', { id: 'revision-panel', role: 'tabpanel', 'aria-labelledby': 'tab-' + revisionTab }, [revisionTab === 'feedback' ? feedbackView() : revisionTab === 'edit' ? specEditor() : changesView()]));
      content.append(node('div', { class: 'stage-actions' }, [button('← 查看首版', () => navigate('create'), 'text-button'), button('整理交接草案 →', prepareHandoff, 'button primary', { id: 'prepare-handoff' })]));
    } else {
      $('stage-eyebrow').textContent = 'LEAVE A USEFUL HANDOFF';
      $('stage-title').textContent = '让下一位，接得住。';
      $('stage-description').textContent = '把版本、变化、反馈决定和未决项放在一起，带着真实状态交接。';
      content.append(handoffView(), node('div', { class: 'stage-actions' }, [button('← 回到修订', () => navigate('revise'), 'text-button'), node('p', { text: '导出不会改变首版快照。回到修订后，修改仍会重新计算。' })]));
    }
    updateSummary();
  }
  function navigate(stage) {
    if (stage === 'handoff') return prepareHandoff();
    if (stage === 'revise' && !state.baseline) return toast('先形成一份首版，再进入修订。当前填写内容已保留。');
    if (state.stage === stage) return;
    state.stage = stage; errors = []; $('validation-errors').hidden = true; renderStage(); focusStage();
  }
  function createFirstVersion() {
    const list = completeness(state.current);
    if (list.length) return showErrors(list);
    try { validateSpec(state.current, '当前任务'); } catch (error) { return notice(error.message, true); }
    state.baseline = freeze({ version: 'v1', created_at: new Date().toISOString(), task: clone(state.current) });
    state.current = clone(state.baseline.task); state.stage = 'revise'; state.revision = null; revisionTab = 'feedback';
    errors = []; $('validation-errors').hidden = true; renderStage(); focusStage();
    toast('首版 v1 已在当前页面保留。点击「保存草案」可留在本浏览器。');
  }
  function prepareHandoff() {
    if (!state.baseline) return toast('先形成首版，才能整理交接草案。');
    const list = [...completeness(state.current), ...feedbackErrors()];
    if (list.length) {
      state.stage = 'revise'; revisionTab = list[0].tab || 'feedback'; renderStage(); showErrors(list); return;
    }
    try { validateSpec(state.current, '当前任务'); } catch (error) { return notice(error.message, true); }
    if (!state.revision) state.revision = freeze({ version: 'v1.1', created_at: new Date().toISOString(), task: clone(state.current), feedback: clone(state.feedback) });
    state.stage = 'handoff'; errors = []; $('validation-errors').hidden = true; renderStage(); focusStage();
  }

  function download(content, filename, type) {
    const blob = new Blob(['\ufeff', content], { type: type + ';charset=utf-8' });
    const url = URL.createObjectURL(blob), anchor = node('a', { href: url, download: filename });
    anchor.hidden = true; document.body.append(anchor); anchor.click(); anchor.remove();
    setTimeout(() => URL.revokeObjectURL(url), 30000);
    toast('已准备下载「' + filename + '」。请在浏览器下载位置核对文件。');
  }
  function filename(extension, handoff = false) {
    const title = (state.current.title || '未命名任务').replace(/[<>:"/\\|?*\u0000-\u001f]/g, '_').replace(/\s+/g, '-').slice(0, 45);
    return 'PMToolkit-' + title + '-' + (state.baseline ? 'v1.1' : 'v1-draft') + (handoff ? '-交接草案' : '-原型草案') + '.' + extension;
  }
  function exportJSON() {
    try { const payload = envelope(); validateEnvelope(payload); const content = JSON.stringify(payload, null, 2) + '\n'; insist(new Blob(['\ufeff', content]).size <= MAX_BYTES, '草案超过 256 KB，请精简内容后再导出，以便之后能恢复。'); download(content, filename('json'), 'application/json'); }
    catch (error) { notice('暂不能导出：' + error.message + ' 当前编辑内容未被替换。', true); }
  }
  const mdText = text => String(text).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/([\\`*_{}\[\]#|])/g, '\\$1').replace(/\r\n?/g, '\n');
  function markdown() {
    const diff = differences(), pending = pendingItems(), spec = state.current;
    const lines = ['# ' + mdText(spec.title || '未命名任务') + ' · 交接草案', '', '> 交互原型 / 本地草案。未认证实际检查、审批或业务验收。', '', '- prototype_demo: true', '- not_runtime_verified: true', '- 草案格式：' + FORMAT + ' / ' + VERSION, '- 任务标识：' + state.taskId, '- 整理时间：' + new Date().toISOString(), '- 版本：v1 → v1.1', '- 当前状态：' + handoffStatus().title, '', '## 当前任务', ''];
    BASIC_KEYS.forEach(key => lines.push('### ' + LABELS[key] + (spec.pending.includes(key) ? '（待补充）' : ''), '', mdText(spec[key] || '待补充'), ''));
    lines.push('### 信息字段', '', '- 任务形态：' + (spec.kind === 'form' ? '申请表单' : '集合列表'));
    if (spec.fieldsPending) lines.push('- 字段定义待补充。');
    spec.fields.forEach(field => lines.push('- ' + mdText(field.label || '待补充字段') + '：' + TYPE_LABELS[field.type] + ' / ' + (field.required ? '必填' : '选填') + (field.pending ? ' / 待补充' : '') + (field.type === 'number' ? ' / 最小值 ' + displayValue(field.min) + ' / 最大值 ' + displayValue(field.max) : '') + (field.type === 'choice' ? ' / 选项 ' + mdText(field.options.join('、')) : '')));
    lines.push('', '## 新旧版本与变化', '', '- 首版 v1：' + state.baseline.created_at, '- 本轮 v1.1：' + state.revision.created_at, '');
    if (!diff.length) lines.push('尚无任务内容变化，需核对本次修订意图。', '');
    diff.forEach(change => lines.push('### ' + mdText(change.label), '', '首版：' + mdText(change.before), '', '修订：' + mdText(change.after), ''));
    lines.push('## 反馈去向', '');
    if (!state.feedback.length) lines.push('本轮未登记反馈。', '');
    state.feedback.forEach((item, index) => {
      const change = diff.find(value => value.id === item.changeId);
      lines.push('### 反馈 ' + (index + 1) + ' · ' + DECISIONS[item.decision], '', mdText(item.text), '', '- 来源：' + mdText(item.source), '- 理由 / 考虑：' + mdText(item.reason || '未填写'));
      if (change && item.decision === 'accepted') lines.push('- 对应实际修改：' + mdText(change.label));
      lines.push('');
    });
    lines.push('## 待补与未决', '');
    lines.push(...(pending.length ? pending.map(item => '- ' + mdText(item)) : ['当前未登记待补项；实际完整性仍需人工核对。']));
    lines.push('', '## 人工观察记录', '', '- 记录状态：' + OBSERVATIONS[state.observation.status], '- 记录性质：人工提供，不是工具执行或认证。', '', mdText(state.observation.text || '尚未记录实际观察。'), '', '## 使用边界', '', '本页面只在浏览器模拟创建、修订与交接；不调用现有 Python，不生成实际 DOCX，不进行真实审批。差异为本原型字段比较，不替代实际工具审计。JSON 仅供本原型恢复，不能直接作为 pm_task 输入。', '');
    return lines.join('\n');
  }
  function exportMarkdown() {
    if (!state.baseline || !state.revision || state.stage !== 'handoff') return toast('请先整理交接草案，再下载文字交接。');
    try { validateEnvelope(envelope()); download(markdown(), filename('md', true), 'text/markdown'); }
    catch (error) { notice('暂不能导出：' + error.message, true); }
  }
  function saveDraft() {
    if (!storageAvailable || !storageEnabled) { notice(storageEnabled ? '保存没有成功：浏览器留存不可用。当前内容仍在本页，请导出草案 JSON。' : '浏览器留存已关闭，尚未保存。可先导出草案 JSON，或在右侧开启留存。', true); return; }
    try {
      const payload = envelope(); validateEnvelope(payload);
      const serialized = JSON.stringify(payload);
      insist(new Blob([serialized]).size <= MAX_BYTES, '草案超过 256 KB，请精简内容后再保存，以便之后能恢复。');
      localStorage.setItem(STORAGE_KEY, serialized);
      savedSignature = JSON.stringify(state); savedAt = payload.exported_at;
      notice('草案已保存在这个浏览器。下次打开相同地址时会恢复；建议同时导出一份文件。');
      updateSummary(); toast('草案已保存。首版与修订记录一起留存。');
    } catch (error) {
      notice('保存没有成功：' + error.message + ' 当前内容仍在本页，可修正后重试或导出草案。', true);
      // Do not mark content as saved on a failed storage write.
      updateSummary();
    }
  }
  async function importFile(file) {
    if (!file) return;
    if (file.size > MAX_BYTES) { notice('未导入：文件超过 256 KB。当前任务保持原样。', true); return; }
    let loaded;
    try { const raw = (await file.text()).replace(/^\ufeff/, ''); const payload = JSON.parse(raw); loaded = validateEnvelope(payload); }
    catch (error) { notice('未导入：' + error.message + ' 当前任务保持原样。', true); return; }
    if (hasContent() && !await ask('从文件恢复这份草案？', '文件格式已核对。恢复会替换当前页面中的任务、版本和观察记录；本浏览器已存草案要到再次保存时才会被替换。', '恢复草案')) return;
    state = loaded; if (state.baseline) freeze(state.baseline); if (state.revision) freeze(state.revision);
    revisionTab = 'feedback'; errors = []; $('validation-errors').hidden = true; $('toast').hidden = true; undoAction = null;
    renderStage(); focusStage(); notice('已从文件恢复草案。内容尚未保存到本浏览器，请核对后点击「保存草案」。');
  }
  async function toggleStorage() {
    if (storageAvailable && storageEnabled) {
      if (!await ask('关闭浏览器留存？', '这会清除本原型在此浏览器中已保存的草案。当前页面内容仍保留；需要留档请先取消并导出文件。', '清除留存并关闭')) return;
      try { localStorage.removeItem(STORAGE_KEY); localStorage.setItem(PREF_KEY, 'off'); storageEnabled = false; savedAt = ''; savedSignature = ''; notice('浏览器留存已关闭并清除。当前内容只在本页，请在离开前导出文件。', true); }
      catch (error) { notice('无法确认留存已关闭：' + error.message + '。请使用浏览器站点数据设置核对。', true); }
    } else {
      try { localStorage.setItem(PREF_KEY, 'on'); const test = STORAGE_KEY + '_test'; localStorage.setItem(test, '1'); localStorage.removeItem(test); storageAvailable = true; storageEnabled = true; notice('浏览器留存已开启。当前内容尚未保存，请点击「保存草案」。'); }
      catch (error) { storageAvailable = false; storageFault = error.message; notice('浏览器仍不允许留存，尚未保存。请导出草案文件。', true); }
    }
    updateSummary();
  }
  async function resetTask() {
    if (!await ask('清除这份草案，重新开始？', '将清除当前页面和本浏览器中保存的任务、首版、反馈与观察。无法从本页面撤回；需要保留请先取消并导出文件。', '清除并新建')) return;
    if (storageAvailable) {
      try { localStorage.removeItem(STORAGE_KEY); }
      catch (error) { notice('无法清除浏览器中已存草案，当前任务保持原样。请核对浏览器存储设置。', true); return; }
    }
    state = emptyState(); savedSignature = JSON.stringify(state); savedAt = ''; revisionTab = 'feedback'; errors = []; undoAction = null; $('toast').hidden = true; $('validation-errors').hidden = true;
    renderStage(); focusStage(); notice('已清除本原型的已存草案，开始一份空白任务。');
  }
  async function loadSample() {
    if (hasContent() && !await ask('载入人工合成样例？', '这会替换当前页面的填写内容；浏览器中已存的草案会保留到你再次保存。样例不含真实公司或人物资料。', '载入样例')) return;
    state = emptyState();
    state.current = { kind: 'collection', title: '客户反馈跟进台', audience: '负责记录与跟进反馈的产品同学，以及需要了解处理进展的协作成员。', problem: '合成场景：反馈分散在讨论记录中，下一位接手时难以知道哪些已处理、哪些还在等待确认。', goal: '让每条反馈有清晰的主题、状态与后续动作，便于一次讨论后继续跟进。', included: '登记反馈主题与内容；标记处理状态；记录下一步与预计跟进天数。', excluded: '自动回复、真实客户资料、多人账号、消息推送和外部系统同步。', pending: [], fieldsPending: false, fields: [ { id: uid('f'), key: 'field_01', label: '反馈主题', type: 'text', required: true, min: null, max: null, options: [], pending: false }, { id: uid('f'), key: 'field_02', label: '处理状态', type: 'choice', required: true, min: null, max: null, options: ['待讨论', '跟进中', '已记录处理'], pending: false }, { id: uid('f'), key: 'field_03', label: '预计跟进天数', type: 'number', required: false, min: 0, max: 30, options: [], pending: false } ] };
    revisionTab = 'feedback'; errors = []; undoAction = null; $('toast').hidden = true; $('validation-errors').hidden = true;
    renderStage(); notice('已载入全新人工合成样例。可直接修改，也可先形成首版；内容尚未保存。');
  }
  function restoreStorage() {
    try {
      const test = STORAGE_KEY + '_test'; localStorage.setItem(test, '1'); localStorage.removeItem(test); storageAvailable = true;
      storageEnabled = localStorage.getItem(PREF_KEY) !== 'off';
      if (!storageEnabled) return;
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return;
      insist(new Blob([raw]).size <= MAX_BYTES, '已存草案超过格式上限。');
      const payload = JSON.parse(raw); state = validateEnvelope(payload);
      if (state.baseline) freeze(state.baseline); if (state.revision) freeze(state.revision);
      savedAt = payload.exported_at; savedSignature = JSON.stringify(state);
      notice('已恢复 ' + dateText(savedAt) + ' 保存的草案。请继续上次的任务。');
    } catch (error) {
      storageFault = error.message;
      if (!storageAvailable) notice('此浏览器不允许本地留存，保存尚不可用。可使用文件导入和导出。', true);
      else notice('已存草案未能恢复：' + storageFault + ' 原内容未被自动清除。可从文件恢复，或明确清除后新建。', true);
    }
  }

  document.querySelectorAll('[data-stage]').forEach(item => item.addEventListener('click', () => navigate(item.dataset.stage)));
  $('save-draft').addEventListener('click', saveDraft);
  $('export-json').addEventListener('click', exportJSON);
  $('import-json').addEventListener('click', () => $('import-file').click());
  $('import-file').addEventListener('change', event => { const file = event.target.files[0]; event.target.value = ''; importFile(file); });
  $('toggle-storage').addEventListener('click', toggleStorage);
  $('reset-task').addEventListener('click', resetTask);
  $('load-sample').addEventListener('click', loadSample);
  $('show-details').addEventListener('click', () => $('details-dialog').showModal());
  $('close-details').addEventListener('click', () => $('details-dialog').close());
  $('details-done').addEventListener('click', () => $('details-dialog').close());
  $('toast-close').addEventListener('click', () => { $('toast').hidden = true; undoAction = null; });
  $('toast-undo').addEventListener('click', () => { const action = undoAction; undoAction = null; $('toast').hidden = true; if (action) action(); });
  window.addEventListener('beforeunload', event => { if (isDirty()) { event.preventDefault(); event.returnValue = ''; } });
  document.addEventListener('keydown', event => { if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') { event.preventDefault(); saveDraft(); } });
  restoreStorage(); renderStage();
})();
