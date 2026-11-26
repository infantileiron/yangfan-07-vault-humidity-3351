import { api } from '../api/workspace.js';
import { resultChart } from '../components/chart.js';
import { empty, exportButton, heading } from '../components/common/heading.js';
import { status } from '../components/common/status.js';
import { table } from '../components/common/table.js';
import { escapeHtml as e, shortId, timeText } from '../utils/format.js';

export async function resultsPage(profile, account, id) {
  const runs = await api.runs();
  const chosen = id || runs[0]?.id;
  if (!chosen) return { html: heading(profile.labels.results, profile.algorithm) +
    empty('还没有计算结果', '创建计算单，等待后台完成计算。', '<a href="#runs">回计算页面</a>') };
  const run = await api.run(chosen);
  const selector = runs.map(item => `<option value="${item.id}" ${item.id === run.id ? 'selected' : ''}>
      ${e(item.label)} · ${e(shortId(item.id))}</option>`).join('');
  const actions = run.result ? exportButton('/runs/' + run.id + '/csv', 'analysis.csv', '导出计算结果') : '';
  const intro = heading(profile.labels.results, profile.labels.action, actions) +
    `<div class="result-pick"><label>计算单<select id="choose-result">${selector}</select></label>
    ${status(run.status)}<span class="muted">${e(timeText(run.created_at))}</span></div>`;
  const mount = root => {
    root.querySelector('#choose-result').onchange = event => { location.hash = '#results/' + event.target.value; };
  };
  if (!run.result) {
    return {
      html: intro + (run.status === 'failed' ?
        empty('计算失败', run.error, '<a href="#runs">调整输入后重试</a>') :
        `<div class="empty"><h2>等待后台计算</h2><p>页面会自动更新当前计算状态。</p></div>`),
      mount,
      poll: ['queued', 'running'].includes(run.status),
    };
  }
  const result = run.result;
  const recheckRows = result.rows.filter(row => row.manual_recheck);
  const staleBanner = run.calibration_stale ?
    `<div class="banner banner-warn"><strong>该计算单已被换表校准作废。</strong>
      其训练或发报使用了校准前口径，请用同一数据版本和阈值<a href="#runs/${encodeURIComponent(run.dataset_id)}">重新提交计算</a>；未受影响的库房仍可照常排班。</div>` : '';
  const recheckBanner = recheckRows.length ?
    `<div class="banner banner-recheck"><strong>${recheckRows.length} 个库房待人工复测：</strong>
      ${recheckRows.map(row => e(row.room)).join('、')}。这些库房未做自动更正，也不纳入优先排序，请到<a href="#calibrations">换表校准</a>页查看原因。</div>` : '';
  return {
    html: intro + staleBanner + `<div class="board results-board"><aside class="side">
      <h2>本次口径</h2><dl class="meta"><dt>${e(profile.parameter.label)}</dt><dd>${e(run.parameter)}</dd>
      <dt>数据版本</dt><dd><a href="#datasets/${run.dataset_id}">${shortId(run.dataset_id)}</a></dd>
      </dl><p class="muted">${e(profile.downstream)}</p>
      <a class="button" href="#handoff/${run.id}">查看签审</a>
      </aside><section class="work">
      <h2>${e(result.summary)}</h2>
      ${recheckBanner}
      <dl class="metrics">${result.metrics.map(metric => `<div><dt>${e(metric.label)}</dt><dd>${e(metric.value)}</dd></div>`).join('')}</dl>
      ${resultChart(result.rows, profile.chart)}
      <h3>${e(profile.labels.action)}</h3>
      ${table(profile.result_columns, result.rows, (row, column, value) => {
        if (column.key === 'manual_recheck') return row.manual_recheck ? '<span class="status s-hold">待复测</span>' : '—';
        if (column.key === 'calibrated') return row.calibrated ? '<span class="status s-succeeded">已校准</span>' : '—';
        if (column.key === 'disposition' && row.manual_recheck) return `<span class="status s-hold">${e(value)}</span>`;
        return e(value);
      })}
      <details class="details"><summary>计算说明</summary><ul>${result.notes.map(note => '<li>' + e(note) + '</li>').join('')}</ul></details>
      </section></div>`,
    mount,
  };
}
