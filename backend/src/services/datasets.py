from fastapi import HTTPException
from sqlalchemy import select
from src.models import Dataset
from src.services.business import metadata
from src.services.calendar_merge import plan_merge, finalize_merge, preview as merge_preview, UnchangedMerge
from src.utils.serialization import checksum
from datetime import date
import math, time
def _validate(records):
    for index,row in enumerate(records):
        for c in metadata()['columns']:
            value=row.get(c['key'])
            if c['key']=='demand' and (value is None or value==''):
                row[c['key']]=None # 缺报标记：与明确零领用分开，未补齐前不参与预测
                continue
            if value is None or value=='': raise HTTPException(422, f'第 {index+1} 行缺少字段 {c["label"]}')
            if c['type']=='number':
                try:
                    if isinstance(value,bool) or not math.isfinite(float(value)): raise ValueError()
                    row[c['key']]=float(value)
                except (TypeError, ValueError, OverflowError): raise HTTPException(422, f'第 {index+1} 行 {c["label"]} 必须为有限数值')
            if c.get('format')=='date':
                try: row[c['key']]=str(date.fromisoformat(str(value).strip()))
                except (TypeError, ValueError): raise HTTPException(422, f'第 {index+1} 行 {c["label"]} 必须是 ISO 日期（例如 2026-07-14）')
def _check_name(db,name):
    name=name.strip()
    if len(name)<2: raise HTTPException(422, '批次名称去除空格后至少需要两个字符')
    if db.scalar(select(Dataset).where(Dataset.name==name)):
        raise HTTPException(409, '该数据批次名已存在，请修改名称')
    return name
def create(db, data):
    name=_check_name(db,data.name)
    _validate(data.records)
    d=Dataset(name=name, source=data.source, records=data.records, checksum=checksum(data.records), created_at=time.time())
    db.add(d); db.flush()
    return d
def _base_labels(base):
    return f'批次 #{base.id} · {base.name}', (base.provenance or {}).get('record_sources', {})
def preview_merge(base, data):
    base_label, sources = _base_labels(base)
    try:
        plan = plan_merge(base.records, sources, base_label, data.records, f'补发 · {data.source}')
    except ValueError as e:
        raise HTTPException(422, str(e)) from None
    return merge_preview(plan)
def merge(db, base, data, user):
    name=_check_name(db,data.name)
    base_label, sources = _base_labels(base)
    upload_label=f'补发 · {data.source}'
    resolutions={}
    for r in data.resolutions:
        try: day=str(date.fromisoformat(r.day.strip()))
        except (TypeError, ValueError): raise HTTPException(422, f'取舍决定的日期不是 ISO 格式：{r.day}')
        resolutions[(r.part.strip(), day)]=r.demand
    try:
        plan = plan_merge(base.records, sources, base_label, data.records, upload_label)
        records, provenance, stats = finalize_merge(plan, resolutions, upload_label, user.email, time.time())
    except UnchangedMerge as e:
        raise HTTPException(409, str(e)) from None
    except ValueError as e:
        raise HTTPException(422, str(e)) from None
    provenance.update({'kind':'calendar-merge','base':{'id':base.id,'name':base.name},
                       'upload':data.source,'merged_by':user.email,'merged_at':time.time()})
    d=Dataset(name=name, source=data.source, records=records, checksum=checksum(records),
              created_at=time.time(), parent_id=base.id, provenance=provenance)
    db.add(d); db.flush()
    return d, stats
