import {datasets} from '../api/entities.js';
import {workspace} from '../stores/workspace.js';
import {session} from '../stores/session.js';
import {heading} from '../components/common/shell.js';
import {table} from '../components/common/table.js';
import {esc,notify,date} from '../utils/dom.js';
import {submit} from '../hooks/forms.js';
import {parseCSV} from '../utils/csv.js';
function detailColumns(d,m){return d.provenance?[...m.columns,{key:'_source',label:'来源'}]:m.columns;}
function detailRows(d){
 const sources=d.provenance?.record_sources||{};
 return d.records.slice(0,30).map(r=>({...r,demand:r.demand===null?'缺报':r.demand,_source:sources[r.part+'|'+r.day]||'—'}));
}
function provenanceHTML(d){
 const p=d.provenance;
 if(!p)return '';
 const s=p.stats||{};
 return '<div class="section-title"><h2>接续来源与取舍</h2><span>每条记录的来源随批次保存</span></div><p class="hint">接续自批次 #'+p.base.id+' · '+esc(p.base.name)+'；补发文件 '+esc(p.upload)+'；'+esc(p.merged_by)+' 于 '+date(p.merged_at)+' 合并。新增 '+s.added+' 条，重复投递跳过 '+s.duplicates+' 条，补齐缺报 '+s.fills+' 天，断档标记缺报 '+s.holes+' 天。</p>'+(p.decisions?.length?table([{key:'part',label:'备件'},{key:'day',label:'日期'},{key:'existing',label:'原批次值'},{key:'candidates',label:'补发值'},{key:'adopted',label:'采用'},{key:'source',label:'采用来源'}],p.decisions.map(x=>({...x,candidates:x.candidates.join(' / ')})),'暂无冲突取舍。'):'');
}
export async function dataPage(){
 workspace.datasets=await datasets.list();let selected=workspace.datasets[0]?await datasets.get(workspace.datasets[0].id):null,m=workspace.meta;
 return heading('02 / DATA INTAKE','数据接入与批次追溯','保留原始业务字段、来源和内容指纹。分析任务始终绑定一个不可变数据批次；ERP 补发与更正在既有批次上接续合并，生成可试算的新批次，原批次、既有试算与简报仍按当时数据回看。')+'<div class="dataset-grid"><section class="panel"><div class="section-title"><h2>业务批次</h2><span>'+workspace.datasets.length+' 批</span></div><div class="batch-list">'+workspace.datasets.map(d=>'<button class="batch-item" data-dataset="'+d.id+'"><strong>'+esc(d.name)+'</strong><span>'+d.rows+' 条 · '+esc(d.source)+(d.missing?' · 缺报 '+d.missing+' 天':'')+'</span><small>SHA256 '+esc(d.checksum.slice(0,18))+'…'+(d.parent_id?' · 接续自批次 #'+d.parent_id:'')+'</small></button>').join('')+'</div><div class="section-title"><h2>接入新数据</h2></div><form id="dataset-form"><label>批次名称<input name="name" required minlength="2" placeholder="例如：11 月复测批次"></label><label>上传 CSV 或 JSON<input type="file" id="file-input" accept=".json,.csv"></label><label>记录 JSON<textarea name="records" rows="6" placeholder="粘贴 JSON 数组，或先选择上方文件" required></textarea></label><p class="hint">字段：'+m.columns.map(c=>esc(c.key)+' / '+esc(c.label)).join('，')+'。5–5,000 条记录；领用件数留空表示缺报，与明确零领用分开。</p><button type="submit" class="primary" '+(session.user.role==='viewer'?'disabled':'')+'>校验并接入批次</button></form></section><section class="panel"><div class="section-title"><h2 id="preview-name">'+esc(selected?.name||'尚无批次')+'</h2><span>预览前 30 条</span></div><div id="data-preview">'+(selected?table(detailColumns(selected,m),detailRows(selected)):'')+'</div><div id="data-lineage">'+(selected?provenanceHTML(selected):'')+'</div></section></div><section class="panel" id="merge-panel"><div class="section-title"><h2>接续补发 / 更正</h2><span>在已有批次上合并 ERP 重发日历，不改动原批次</span></div><form id="merge-form"><div class="parameter-grid"><label>基准批次<select name="base_id">'+workspace.datasets.map(d=>'<option value="'+d.id+'">'+esc(d.name)+'</option>').join('')+'</select></label><label>新批次名称<input name="name" minlength="2" placeholder="例如：2026Q3 领用 · 接续 0714 补发"></label></div><label>补发 CSV 或 JSON<input type="file" id="merge-file" accept=".json,.csv"></label><label>补发记录 JSON<textarea name="records" rows="5" placeholder="粘贴 ERP 补发的 JSON 数组，或先选择上方文件" required></textarea></label><p class="hint">按备件 + 日期合并：完全相同的重复投递自动跳过，不重复计算领用量；同日不同数量会列出冲突，确认采用哪份后才生成新批次；日历断档自动标记缺报，缺报未补齐时不参与预测。</p><button type="submit" class="primary" '+(session.user.role==='viewer'||!workspace.datasets.length?'disabled':'')+'>预检合并</button></form><div id="merge-result"></div></section>';
}
export function bindData(refresh){
 let source='manual.json';
 document.querySelector('#file-input').addEventListener('change',async e=>{try{const file=e.target.files[0];if(!file)return;source=file.name;const text=await file.text(),records=file.name.endsWith('.csv')?parseCSV(text):JSON.parse(text);document.querySelector('[name=records]').value=JSON.stringify(records,null,2);}catch(error){notify(error.message,true);}});
 document.querySelectorAll('[data-dataset]').forEach(button=>button.onclick=async()=>{try{const d=await datasets.get(button.dataset.dataset);document.querySelector('#preview-name').textContent=d.name;document.querySelector('#data-preview').innerHTML=table(detailColumns(d,workspace.meta),detailRows(d));document.querySelector('#data-lineage').innerHTML=provenanceHTML(d);}catch(error){notify(error.message,true);}});
 submit(document.querySelector('#dataset-form'),async f=>{await datasets.create({name:f.get('name'),source,records:JSON.parse(f.get('records'))});notify('数据已接入，可前往工作台执行分析');await refresh();});
 const mergeForm=document.querySelector('#merge-form'),resultBox=document.querySelector('#merge-result');
 let mergeSource='redelivery.json',mergeRecords=null,preview=null;
 mergeForm.querySelector('#merge-file').addEventListener('change',async e=>{try{const file=e.target.files[0];if(!file)return;mergeSource=file.name;const text=await file.text();mergeForm.querySelector('[name=records]').value=JSON.stringify(file.name.endsWith('.csv')?parseCSV(text):JSON.parse(text),null,2);}catch(error){notify(error.message,true);}});
 submit(mergeForm,async f=>{
   mergeRecords=JSON.parse(f.get('records'));
   const baseId=Number(f.get('base_id'));
   preview=await datasets.mergePreview(baseId,{source:mergeSource,records:mergeRecords});
   const c=preview.conflicts||[];
   let html='<div class="merge-summary">'+[['新增',preview.added],['重复跳过',preview.duplicates],['补齐缺报',preview.fills],['断档缺报',preview.holes.length],['冲突待决',c.length]].map(([k,v])=>'<div><span>'+k+'</span><strong>'+v+'</strong></div>').join('')+'</div><p class="hint">合并后共 '+preview.rows_after+' 条，其中缺报 '+preview.missing_total+' 天；缺报未补齐时不参与预测。</p>';
   if(preview.holes.length)html+='<p class="warning">日历断档将标记为缺报：'+preview.holes.slice(0,8).map(h=>esc(h.part)+' '+esc(h.day)).join('，')+(preview.holes.length>8?' 等 '+preview.holes.length+' 天':'')+'。</p>';
   if(c.length)html+='<div class="section-title"><h2>同日不同数量冲突</h2><span>确认采用哪份后才能生成新批次</span></div>'+c.map((x,i)=>'<div class="conflict-item"><strong>'+esc(x.part)+' · '+esc(x.day)+'</strong><label class="radio-row"><input type="radio" name="conflict-'+i+'" value="existing"> 保留原值 '+esc(x.existing)+'（'+esc(x.existing_source)+'）</label>'+x.candidates.map(v=>'<label class="radio-row"><input type="radio" name="conflict-'+i+'" value="'+esc(v)+'"> 采用补发值 '+esc(v)+'（'+esc(mergeSource)+'）</label>').join('')+'</div>').join('');
   if(preview.unchanged)html+='<p class="warning">补发内容与现有日历完全一致，无需生成新批次。</p>';
   else if(preview.over_limit)html+='<p class="warning">合并后超过单批次 5,000 条上限，请分批接续。</p>';
   else html+='<button class="primary" id="merge-commit">确认取舍并生成新批次</button>';
   resultBox.innerHTML=html;
   resultBox.querySelector('#merge-commit')?.addEventListener('click',async()=>{
     try{
       const name=mergeForm.querySelector('[name=name]').value.trim();
       if(name.length<2)throw new Error('请填写至少两个字符的新批次名称');
       const resolutions=c.map((x,i)=>{const picked=resultBox.querySelector('input[name=conflict-'+i+']:checked');if(!picked)throw new Error('还有冲突未确认采用哪份：'+x.part+' '+x.day);return {part:x.part,day:x.day,demand:picked.value==='existing'?x.existing:Number(picked.value)};});
       const result=await datasets.merge(baseId,{name,source:mergeSource,records:mergeRecords,resolutions});
       notify('已生成新批次「'+result.name+'」：新增 '+result.merge.added+' 条，缺报 '+result.merge.missing_total+' 天待补齐');
       await refresh();
     }catch(error){notify(error.message,true);}
   });
 });
}
