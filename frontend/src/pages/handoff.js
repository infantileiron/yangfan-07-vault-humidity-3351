import { api } from '../api/workspace.js';
import { table } from '../components/common/table.js';
import { empty, exportButton, heading } from '../components/common/heading.js';
import { status } from '../components/common/status.js';
import { auditActions } from '../constants/enums.js';
import { bindForm, notice } from '../hooks/forms.js';
import { escapeHtml as e, shortId, timeText } from '../utils/format.js';

export async function handoffPage(profile, account, id) {
  const [runs, reviews, audit, recheck] = await Promise.all([
    api.runs(), api.reviews(), api.audit(), api.recheckRooms(),
  ]);
  const completed = runs.filter(run => run.status === 'succeeded');
  const selected = completed.find(run => run.id === id) || completed[0];
  const run = selected && await api.run(selected.id);
  const review = run?.review;
  const selector = completed.map(item => `<option value="${item.id}" ${item.id === selected?.id ? 'selected' : ''}>${e(item.label)}</option>`).join('');
  const actions = review?.decision === 'approve' ?
    exportButton('/runs/' + run.id + '/handoff.csv', 'handoff.csv', '下载签发清单') : '';
  const recheckRooms = new Set(recheck.rooms.map(item => item.room));
  const recheckBanner = run?.result?.rows?.some(row => row.manual_recheck) ?
    `<div class="banner banner-recheck"><strong>待人工复测库房：</strong>
      ${run.result.rows.filter(row => row.manual_recheck).map(row => e(row.room)).join('、')}
      。这些库房不参与自动优先排序，请安排现场人工复测。详见<a href="#calibrations">换表校准</a>。</div>` : '';
  const staleBanner = run?.calibration_stale ?
    `<div class="banner banner-warn"><strong>该计算单已被换表校准作废，待重算。</strong>请先到计算页重新提交，再签交。</div>` : '';
  const form = run && account.role === 'reviewer' && !review ? `
    <form id="review-form">
      <p>选择要交接的样本，再填写复核结论。暂缓可不选样本。待人工复测库房不建议纳入签发。</p>
      ${table(profile.result_columns, run.result.rows.slice(0, 500), (row, column, value) => {
        if (column.key === 'manual_recheck') return row.manual_recheck ? '<span class="status s-hold">待复测</span>' : '—';
        if (column.key === 'calibrated') return row.calibrated ? '<span class="status s-succeeded">已校准</span>' : '—';
        return e(value);
      }, true)}
      ${run.result.rows.length > 500 ? '<p>本页可签审前 500 条结果。完整计算结果可在结果页下载。</p>' : ''}
      <label>决定<select name="decision"><option value="approve">签发</option><option value="hold">暂缓</option></select></label>
      <label>复核说明<textarea name="note" minlength="2" maxlength="1000" required></textarea></label>
      <div class="form-error" data-error role="alert"></div><button type="submit">保存决定</button>
    </form>` : '';
  return {
    html: heading(profile.labels.handoff, profile.downstream, actions) +
      `<div class="board"><aside class="side"><h2>交接记录</h2>${reviews.map(item => `<a class="version" href="#handoff/${item.run_id}">
        <strong>${e(runs.find(candidate => candidate.id === item.run_id)?.label || shortId(item.run_id))}</strong><span>${status(item.decision)}</span></a>`).join('') || '<p>暂无记录</p>'}
      <h2>待人工复测</h2>${recheckRooms.size ? [...recheckRooms].map(room =>
        `<p class="recheck-tag"><span class="status s-hold">待复测</span> ${e(room)}</p>`).join('')
        : '<p class="muted">暂无</p>'}</aside>
      <section class="work">
      ${run ? `<label>已完成计算单<select id="choose-review">${selector}</select></label>
      <p><a href="#results/${run.id}">查看完整结果</a></p>${staleBanner}${recheckBanner}${review ? `<div class="review-record">${status(review.decision)}
        <strong>${e(review.reviewer)}</strong><p>${e(review.note)}</p>
        <p class="muted">${review.samples.length} 条交接样本 · ${e(timeText(review.created_at))}</p></div>` :
        form || '<p>此计算单等待复核员签审。</p>'}` :
        empty('还没有可签审的计算单', '后台完成计算后，复核员可选中样本并记录签审结果。')}
      <h3>审计流水</h3>
      ${audit.length ? table([
        {key:'action',label:'动作'}, {key:'actor',label:'操作者'}, {key:'subject',label:'对象'}, {key:'created_at',label:'时间'},
      ], audit, (row, column, value) => {
        if (column.key === 'action') return e(auditActions[value] || value);
        if (column.key === 'subject') return e(shortId(value));
        if (column.key === 'created_at') return e(timeText(value));
        return e(value);
      }) : '<p class="muted">暂无审计事件。</p>'}</section></div>`,
    mount(root, refresh) {
      const pick = root.querySelector('#choose-review');
      if (pick) pick.onchange = () => { location.hash = '#handoff/' + pick.value; };
      bindForm(root, 'review-form', async data => {
        await api.review(run.id, { decision: data.get('decision'), note: data.get('note'), samples: data.getAll('samples') });
        notice('已保存复核决定。');
        refresh();
      });
    },
  };
}
