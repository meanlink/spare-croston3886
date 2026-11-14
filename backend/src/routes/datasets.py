from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from src.config.database import get_db
from src.models import Dataset
from src.schemas.dataset import DatasetInput, MergePreviewInput, MergeCommitInput
from src.middlewares.auth import current_user, can_write
from src.services import datasets
from src.services.audit import record
from src.utils.serialization import dataset_dict
router=APIRouter(prefix='/datasets')
@router.get('')
def listing(db=Depends(get_db),u=Depends(current_user)):
    return [dataset_dict(d) for d in db.scalars(select(Dataset).order_by(Dataset.id.desc()))]
@router.post('',status_code=201)
def create(data:DatasetInput,db=Depends(get_db),u=Depends(can_write)):
    d=datasets.create(db,data); record(db,u.email,'dataset.create',{'id':d.id,'rows':len(d.records)})
    db.commit(); return dataset_dict(d)
@router.get('/{id}')
def detail(id:int,db=Depends(get_db),u=Depends(current_user)):
    d=db.get(Dataset,id)
    if not d:raise HTTPException(404,'数据批次不存在')
    return {**dataset_dict(d),'records':d.records,'provenance':d.provenance}
@router.post('/{id}/merge/preview')
def merge_preview(id:int,data:MergePreviewInput,db=Depends(get_db),u=Depends(can_write)):
    base=db.get(Dataset,id)
    if not base:raise HTTPException(404,'数据批次不存在')
    return datasets.preview_merge(base,data)
@router.post('/{id}/merge',status_code=201)
def merge(id:int,data:MergeCommitInput,db=Depends(get_db),u=Depends(can_write)):
    base=db.get(Dataset,id)
    if not base:raise HTTPException(404,'数据批次不存在')
    d,stats=datasets.merge(db,base,data,u)
    record(db,u.email,'dataset.merge',{'id':d.id,'base':base.id,**stats})
    db.commit(); return {**dataset_dict(d),'merge':stats}
