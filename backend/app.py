from __future__ import annotations
import json, os, shutil, subprocess, uuid
from pathlib import Path
from typing import Any
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship

ROOT = Path(os.environ.get('VISUSYNC_DATA', '/home/node/visusync-ai/data')).resolve()
ROOT.mkdir(parents=True, exist_ok=True)
engine = create_engine(f"sqlite:///{ROOT/'visusync.db'}", connect_args={'check_same_thread': False})
class Base(DeclarativeBase): pass
class Project(Base):
    __tablename__='projects'
    id: Mapped[str]=mapped_column(String, primary_key=True, default=lambda:str(uuid.uuid4()))
    name: Mapped[str]=mapped_column(String(180)); status: Mapped[str]=mapped_column(String, default='created')
    original_file: Mapped[str|None]=mapped_column(String, nullable=True); metadata_json: Mapped[str]=mapped_column(Text, default='{}')
    transcript_json: Mapped[str]=mapped_column(Text, default='[]'); suggestions_json: Mapped[str]=mapped_column(Text, default='[]')
    summary: Mapped[str]=mapped_column(Text, default=''); created: Mapped[str]=mapped_column(String, default=lambda:__import__('datetime').datetime.now().isoformat(timespec='seconds'))
    clips: Mapped[list['Clip']]=relationship(back_populates='project', cascade='all, delete-orphan')
class Clip(Base):
    __tablename__='clips'
    id: Mapped[str]=mapped_column(String, primary_key=True, default=lambda:str(uuid.uuid4())); project_id: Mapped[str]=mapped_column(ForeignKey('projects.id'))
    suggestion_id: Mapped[str]=mapped_column(String, default=''); start: Mapped[float]=mapped_column(Float); end: Mapped[float]=mapped_column(Float)
    type: Mapped[str]=mapped_column(String); description: Mapped[str]=mapped_column(Text); asset_path: Mapped[str|None]=mapped_column(String, nullable=True)
    project: Mapped[Project]=relationship(back_populates='clips')
Base.metadata.create_all(engine)
app=FastAPI(title='VisuSync AI API', version='0.1.0')
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_methods=['*'], allow_headers=['*'])
VIDEO_EXTS={'.mp4','.mov'}
def get_project(s:Session,pid:str)->Project:
    p=s.get(Project,pid)
    if not p: raise HTTPException(404,'Project not found')
    return p
def project_dict(p:Project, include_clips=False):
    d={'id':p.id,'name':p.name,'status':p.status,'metadata':json.loads(p.metadata_json),'transcript':json.loads(p.transcript_json),'suggestions':json.loads(p.suggestions_json),'summary':p.summary,'created':p.created,'has_video':bool(p.original_file)}
    if include_clips:d['clips']=[clip_dict(c) for c in p.clips]
    return d
def clip_dict(c):return {'id':c.id,'suggestion_id':c.suggestion_id,'start':c.start,'end':c.end,'type':c.type,'description':c.description,'asset_path':c.asset_path}
class ProjectIn(BaseModel): name:str=Field(min_length=1,max_length=180)
class ClipIn(BaseModel): suggestion_id:str=''; start:float=Field(ge=0); end:float=Field(gt=0); type:str; description:str=Field(min_length=1); asset_path:str|None=None
@app.get('/api/health')
def health(): return {'status':'ok','ffmpeg':shutil.which('ffmpeg') is not None,'ffprobe':shutil.which('ffprobe') is not None,'transcription_provider': 'openai-whisper' if os.getenv('OPENAI_API_KEY') else ('local-whisper' if shutil.which('whisper') else None),'llm_provider':'openai' if os.getenv('OPENAI_API_KEY') else None}
@app.get('/api/projects')
def list_projects():
    with Session(engine) as s:return [project_dict(p) for p in s.scalars(select(Project).order_by(Project.created.desc()))]
@app.post('/api/projects',status_code=201)
def create_project(body:ProjectIn):
    with Session(engine) as s:
        p=Project(name=body.name.strip());s.add(p);s.commit();s.refresh(p);return project_dict(p,True)
@app.get('/api/projects/{pid}')
def get_one(pid:str):
    with Session(engine) as s:return project_dict(get_project(s,pid),True)
@app.post('/api/projects/{pid}/upload')
def upload(pid:str,file:UploadFile=File(...)):
    suffix=Path(file.filename or '').suffix.lower()
    if suffix not in VIDEO_EXTS:raise HTTPException(400,'Only MP4 and MOV files are supported.')
    with Session(engine) as s:
        p=get_project(s,pid); folder=ROOT/pid;folder.mkdir(parents=True,exist_ok=True); target=folder/f'original{suffix}'
        size=0
        with target.open('wb') as out:
            while chunk:=file.file.read(1024*1024):
                size+=len(chunk)
                if size>2*1024*1024*1024:target.unlink(missing_ok=True);raise HTTPException(413,'File exceeds 2 GB limit.')
                out.write(chunk)
        probe=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration:format_tags=title:stream=codec_type,codec_name,width,height,r_frame_rate','-of','json',str(target)],capture_output=True,text=True)
        if probe.returncode:target.unlink(missing_ok=True);raise HTTPException(400,'FFprobe could not read this video.')
        data=json.loads(probe.stdout); streams=data.get('streams',[]);fmt=data.get('format',{})
        if not any(x.get('codec_type')=='video' for x in streams):target.unlink(missing_ok=True);raise HTTPException(400,'File contains no video stream.')
        duration=float(fmt.get('duration',0));thumb=folder/'thumbnail.jpg'
        subprocess.run(['ffmpeg','-y','-ss',str(min(1,max(0,duration*.1)) if duration else 0),'-i',str(target),'-frames:v','1','-vf','scale=640:-2',str(thumb)],capture_output=True)
        audio=folder/'audio.wav'; audio_result=subprocess.run(['ffmpeg','-y','-i',str(target),'-vn','-ac','1','-ar','16000','-c:a','pcm_s16le',str(audio)],capture_output=True)
        if audio_result.returncode:audio.unlink(missing_ok=True)
        p.original_file=str(target);p.metadata_json=json.dumps({'duration':duration,'size_bytes':size,'streams':streams,'thumbnail':f'/api/projects/{pid}/thumbnail','audio_extracted':audio.exists()});p.status='uploaded';s.commit();return project_dict(p,True)
@app.get('/api/projects/{pid}/source')
def source_video(pid:str):
    with Session(engine) as s:
        p=get_project(s,pid)
        if not p.original_file or not Path(p.original_file).exists(): raise HTTPException(404,'Source video not found')
        return FileResponse(p.original_file,media_type='video/mp4')
@app.get('/api/projects/{pid}/thumbnail')
def thumbnail(pid:str):
    with Session(engine) as s:p=get_project(s,pid); path=ROOT/pid/'thumbnail.jpg'
    if not path.exists():raise HTTPException(404,'Thumbnail not ready')
    return FileResponse(path,media_type='image/jpeg')
def suggest_for_segments(segments:list[dict[str,Any]])->list[dict[str,Any]]:
    rules=[(('number','percent','increased','decreased','growth','data','rate','million'),('statistics card','Highlight the stated quantity or rate; include no figures beyond the narration.')),(('process','how','step','first','then','method','system'),('diagram','Show the process or sequence described in the narration.')),(('city','forest','ocean','mountain','travel','building','street','nature'),('B-roll','Use contextual footage illustrating the place or scene explicitly mentioned.')),(('research','study','discovered','scientist','technology','climate','solar','energy','history'),('image','Show a relevant illustrative image for the named topic.'))]
    out=[]
    for x in segments:
        text=x['text']; low=text.lower(); match=next(((typ,desc) for words,(typ,desc) in rules for w in [words] if any(k in low for k in w)),None)
        if not match:continue
        typ,desc=match;topic=' '.join(text.split()[:12]).rstrip('.,')
        out.append({'id':str(uuid.uuid4()),'timestamp_start':float(x['start']),'timestamp_end':float(x['end']),'narration':text,'visual_type':typ,'description':f"{desc} Subject: {topic}.",'reason':'Matches a concrete subject or concept stated in this transcript segment.','asset_query':topic,'asset_url':None,'confidence':0.72,'status':'pending'})
    return out
@app.post('/api/projects/{pid}/analyze')
def analyze(pid:str):
    with Session(engine) as s:
        p=get_project(s,pid)
        if not p.original_file:raise HTTPException(409,'Upload a video before analysis.')
        audio=ROOT/pid/'audio.wav'
        if not audio.exists():raise HTTPException(422,'Audio extraction failed; this video needs an audio stream.')
        key=os.getenv('OPENAI_API_KEY')
        if not key:raise HTTPException(503,'Transcription is not configured. Set OPENAI_API_KEY to enable Whisper API analysis, or install the local whisper CLI.')
        import urllib.request
        boundary='----VisuSync'+uuid.uuid4().hex
        def part(name, value, filename=None, ctype=None):
            disp=f'Content-Disposition: form-data; name="{name}"'+(f'; filename="{filename}"' if filename else '')
            return (f'--{boundary}\r\n{disp}\r\n'+(f'Content-Type: {ctype}\r\n' if ctype else '')+'\r\n').encode()+value+b'\r\n'
        body=part('model',b'whisper-1')+part('response_format',b'verbose_json')+part('file',audio.read_bytes(),'audio.wav','audio/wav')+f'--{boundary}--\r\n'.encode()
        req=urllib.request.Request('https://api.openai.com/v1/audio/transcriptions',data=body,headers={'Authorization':f'Bearer {key}','Content-Type':f'multipart/form-data; boundary={boundary}'},method='POST')
        try:
            with urllib.request.urlopen(req,timeout=300) as resp: transcript=json.loads(resp.read())
        except Exception as e:raise HTTPException(502,f'Transcription provider failed: {str(e)[:250]}')
        segs=[{'start':float(z.get('start',0)),'end':float(z.get('end',0)),'text':z.get('text','').strip()} for z in transcript.get('segments',[]) if z.get('text','').strip()]
        if not segs and transcript.get('text'):segs=[{'start':0,'end':float(json.loads(p.metadata_json).get('duration',0)),'text':transcript['text']}]
        if not segs:raise HTTPException(422,'Transcription returned no speech segments.')
        p.transcript_json=json.dumps(segs);p.suggestions_json=json.dumps(suggest_for_segments(segs));p.summary=transcript.get('text','')[:600];p.status='analyzed';s.commit();return project_dict(p,True)
@app.patch('/api/projects/{pid}/suggestions/{sid}')
def decide(pid:str,sid:str,body:dict):
    status=body.get('status')
    if status not in ('accepted','rejected','pending'):raise HTTPException(422,'Invalid suggestion status')
    with Session(engine) as s:
        p=get_project(s,pid);items=json.loads(p.suggestions_json);found=False
        for x in items:
            if x['id']==sid:x['status']=status;found=True
        if not found:raise HTTPException(404,'Suggestion not found')
        p.suggestions_json=json.dumps(items);s.commit();return {'suggestions':items}
@app.post('/api/projects/{pid}/clips',status_code=201)
def add_clip(pid:str,b:ClipIn):
    if b.end<=b.start:raise HTTPException(422,'Clip end must be after its start.')
    with Session(engine) as s:
        p=get_project(s,pid);c=Clip(project_id=pid,**b.model_dump());s.add(c);s.commit();s.refresh(c);return clip_dict(c)
@app.patch('/api/projects/{pid}/clips/{cid}')
def edit_clip(pid:str,cid:str,b:ClipIn):
    if b.end<=b.start:raise HTTPException(422,'Clip end must be after its start.')
    with Session(engine) as s:
        get_project(s,pid);c=s.get(Clip,cid)
        if not c or c.project_id!=pid:raise HTTPException(404,'Clip not found')
        for k,v in b.model_dump().items():setattr(c,k,v)
        s.commit();return clip_dict(c)
@app.delete('/api/projects/{pid}/clips/{cid}')
def delete_clip(pid:str,cid:str):
    with Session(engine) as s:
        get_project(s,pid);c=s.get(Clip,cid)
        if not c or c.project_id!=pid:raise HTTPException(404,'Clip not found')
        s.delete(c);s.commit();return {'deleted':True}
def esc(s:str)->str:return s.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;').replace("'",'&#39;').replace(':','\\:').replace('%','\\%').replace(',','\\,')
@app.post('/api/projects/{pid}/render')
def render(pid:str):
    with Session(engine) as s:
        p=get_project(s,pid)
        if not p.original_file:raise HTTPException(409,'Upload a video first.')
        clips=list(p.clips); source=Path(p.original_file); out=ROOT/pid/'export.mp4'
        if not clips:
            cmd=['ffmpeg','-y','-i',str(source),'-map','0:v:0','-map','0:a?','-c:v','libx264','-preset','veryfast','-crf','23','-c:a','aac','-movflags','+faststart',str(out)]
        else:
            filters=[]; overlays=[];inputs=['-i',str(source)];n=1
            for c in clips:
                if c.type.lower() in ('caption','captions','text'):
                    filters.append(f"drawtext=text='{esc(c.description)}':fontcolor=white:fontsize=30:borderw=2:bordercolor=black:x=(w-text_w)/2:y=h-text_h-48:enable='between(t,{c.start},{c.end})'")
                elif c.asset_path and Path(c.asset_path).is_file():
                    inputs += ['-i',c.asset_path];overlays.append(f'[{n}:v]scale=iw*min(0.36*W/iw\\,0.36*H/ih):-2[ov{n}];[v{n-1}][ov{n}]overlay=W-w-28:28:enable=\\'between(t,{c.start},{c.end})\\'[v{n}]');n+=1
            if not filters and not overlays:raise HTTPException(422,'Add caption clips or image clips with valid local asset files to render.')
            graph='[0:v]'+','.join(filters)+'[v0]' if filters else '[0:v]null[v0]'
            if overlays: graph=';'.join(['[0:v]null[v0]']+overlays)
            if filters:graph += ';[v'+str(n-1)+']'+','.join(filters)+'[vout]' if overlays else ';[v0]'+','.join(filters)+'[vout]'
            else:graph += ';[v'+str(n-1)+']null[vout]'
            cmd=['ffmpeg','-y',*inputs,'-filter_complex',graph,'-map','[vout]','-map','0:a?','-c:v','libx264','-preset','veryfast','-crf','23','-c:a','aac','-movflags','+faststart',str(out)]
        result=subprocess.run(cmd,capture_output=True,text=True,timeout=3600)
        if result.returncode:raise HTTPException(500,'FFmpeg render failed: '+result.stderr[-1200:])
        p.status='exported';s.commit();return {'status':'completed','download_url':f'/api/projects/{pid}/download','size_bytes':out.stat().st_size}
@app.get('/api/projects/{pid}/download')
def download(pid:str):
    with Session(engine) as s:get_project(s,pid);out=ROOT/pid/'export.mp4'
    if not out.exists():raise HTTPException(404,'No export has been rendered.')
    return FileResponse(out,media_type='video/mp4',filename='visusync-export.mp4')