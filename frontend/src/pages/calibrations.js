import { api } from '../api/workspace.js';
import { table } from '../components/common/table.js';
import { empty, heading } from '../components/common/heading.js';
import { calibrationStates } from '../constants/enums.js';
import { bindForm, notice } from '../hooks/forms.js';
import { escapeHtml as e, shortId, timeText } from '../utils/format.js';

const ROOM_COLUMNS = [
  { key: 'room', label: '地下库房' },
  { key: 'switched_at', label: '换表端点' },
  { key: 'paired_shift_count', label: '同抄班次' },
  { key: 'bias', label: '估计偏差（百分点）' },
  { key: 'check_residual_max', label: '核验最大残差' },
  { key: 'state', label: '校准结论' },
];

function roomRows(result) {
  return result.rooms.map(room => ({
    ...room,
    state: room.manual_recheck ? calibrationStates.manual : calibrationStates.valid,
    bias: room.bias ?? '—',
    check_residual_max: room.check_residual_max ?? '—',
  }));
}

function roomCell(row, column, value) {
  if (column.key === 'state') {
    return row.manual_recheck
      ? `<span class="status s-hold">${e(value)}</span>`
      : `<span class="status s-succeeded">${e(value)}</span>`;
  }
  return e(value);
}

export async function calibrationsPage(profile, account, id) {
  const [items, datasets, recheck] = await Promise.all([
    api.calibrations(), api.datasets(), api.recheckRooms(),
  ]);
  const selected = items.find(item => item.id === id) || items[0];
  const detail = selected && await api.calibration(selected.id);
  const canCreate = account.role === 'analyst' && datasets.length > 0;

  const form = canCreate ? `<form id="calibration-form">
    <label>校准名称<input name="label" maxlength="100" placeholder="例如 C02 换表校准" required></label>
    <label>数据版本<select name="dataset_id">${datasets.map(row =>
      `<option value="${row.id}">${e(row.name)} · ${row.count} 行</option>`).join('')}</select></label>
    <label>校准说明<textarea name="note" minlength="2" maxlength="1000" required
      placeholder="说明更换的库房、表号与同抄安排"></textarea></label>
    <fieldset id="paired-readings">
      <legend>新旧表同抄读数（同一班只填一次，至少留两班）</legend>
      <div id="paired-rows"></div>
      <button type="button" class="quiet" id="add-paired">增加一班同抄</button>
    </fieldset>
    <div class="form-error" data-error role="alert"></div>
    <button type="submit">提交校准</button></form>` :
    '<p class="muted">分析员可在更换湿度计后录入新旧表同抄读数。</p>';

  const pendingCard = recheck.rooms.length ? `<section class="recheck-panel">
      <h2>待人工复测库房</h2>
      ${table([
        { key: 'room', label: '地下库房' },
        { key: 'switched_at', label: '换表端点' },
        { key: 'reason', label: '转人工原因' },
      ], recheck.rooms, (row, column, value) =>
        column.key === 'switched_at' ? e(value || '—') : e(value))}
    </section>` : '';

  const detailCard = detail ? `<section class="work">
      <div class="work-head"><div><h2>${e(detail.label)}</h2>
      <p class="muted">${e(timeText(detail.created_at))} · 数据版本 ${e(shortId(detail.dataset_id))} · ${e(detail.actor)}</p></div></div>
      <p>${e(detail.result.summary)}</p>
      <p class="muted">${e(detail.note)}</p>
      ${table(ROOM_COLUMNS, roomRows(detail.result), roomCell)}
      <details class="details"><summary>同抄读数明细</summary>
      ${table([
        { key: 'room', label: '地下库房' },
        { key: 'shift_at', label: '交班端点' },
        { key: 'old_rh', label: '旧表读数（%）' },
        { key: 'new_rh', label: '新表读数（%）' },
        { key: 'difference', label: '旧减新（百分点）' },
      ], detail.result.rooms.flatMap(room => room.readings.map(item => ({ ...item, room: room.room }))))}
      </details></section>` :
    empty('还没有校准记录', '更换湿度计后，录入新旧表同抄读数以估计偏差并核验。');

  return {
    html: heading(profile.labels.calibrations, '前段同抄估偏差、末段核验；留不出核验班次或单班误差超两个百分点的库房转人工复测。') +
      `<div class="board"><aside class="side"><h2>校准记录</h2>
      ${items.map(item => `<a class="version ${detail?.id === item.id ? 'current' : ''}" href="#calibrations/${item.id}">
        <strong>${e(item.label)}</strong><span>${e(timeText(item.created_at))}</span></a>`).join('') || '<p>暂无记录</p>'}
      <details class="intake" ${items.length ? '' : 'open'}><summary>录入同抄校准</summary>${form}</details></aside>
      <div class="work-stack">${pendingCard}${detailCard}</div></div>`,
    mount(root, refresh) {
      const holder = root.querySelector('#paired-rows');
      const addButton = root.querySelector('#add-paired');
      let rowIndex = 0;
      function addRow() {
        const index = rowIndex++;
        const wrap = document.createElement('div');
        wrap.className = 'paired-row';
        wrap.innerHTML = `<input name="room" maxlength="120" placeholder="库房" required>
          <input name="shift_at" placeholder="YYYY-MM-DD HH:MM" pattern="\\d{4}-\\d{2}-\\d{2} (00|08|16):00" required>
          <input name="old_rh" type="number" min="0" max="100" step="0.01" placeholder="旧表 %" required>
          <input name="new_rh" type="number" min="0" max="100" step="0.01" placeholder="新表 %" required>
          <button type="button" class="quiet remove-paired">移除</button>`;
        wrap.querySelector('.remove-paired').onclick = () => wrap.remove();
        holder.appendChild(wrap);
      }
      if (addButton) {
        addRow();
        addRow();
        addButton.onclick = addRow;
      }
      bindForm(root, 'calibration-form', async data => {
        const rows = [...root.querySelectorAll('.paired-row')].map(wrap => ({
          room: wrap.querySelector('[name=room]').value.trim(),
          shift_at: wrap.querySelector('[name=shift_at]').value.trim(),
          old_rh: Number(wrap.querySelector('[name=old_rh]').value),
          new_rh: Number(wrap.querySelector('[name=new_rh]').value),
        }));
        if (rows.length < 2) throw new Error('至少录入两班同抄，才能留出核验班次。');
        const saved = await api.createCalibration({
          label: data.get('label'), dataset_id: data.get('dataset_id'),
          note: data.get('note'), readings: rows,
        });
        notice(saved.result.manual_recheck_rooms.length
          ? '校准已保存，部分库房转人工复测。' : '校准已保存并通过核验。');
        location.hash = '#calibrations/' + saved.id;
        refresh();
      });
    },
  };
}
