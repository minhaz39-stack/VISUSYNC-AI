from __future__ import annotations
import os, subprocess
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
os.environ["VISUSYNC_DATA"] = "/home/node/visusync-ai/testdata"
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from backend.app import app, suggest_for_segments
@pytest.fixture(scope='module')
def client():
    with TestClient(app) as c: yield c
def test_project_and_analysis_configuration(client):
    p=client.post('/api/projects',json={'name':'Test clip'});assert p.status_code==201
    assert p.json()['status']=='created'
    assert suggest_for_segments([{'start':0,'end':2,'text':'The climate study described clean energy.'}])

def test_upload_metadata_audio_and_real_render(client,tmp_path):
    p=client.post('/api/projects',json={'name':'Render test'}).json()
    video=tmp_path/'sample.mp4'
    subprocess.run(['ffmpeg','-y','-f','lavfi','-i','color=c=blue:s=320x240:d=1','-f','lavfi','-i','sine=frequency=1000:duration=1','-shortest','-c:v','libx264','-c:a','aac',str(video)],check=True,capture_output=True)
    with video.open('rb') as f:r=client.post(f"/api/projects/{p['id']}/upload",files={'file':('sample.mp4',f,'video/mp4')})
    assert r.status_code==200 and r.json()['metadata']['audio_extracted']
    clip=client.post(f"/api/projects/{p['id']}/clips",json={'start':0,'end':0.8,'type':'caption','description':'Real render test'});assert clip.status_code==201
    out=client.post(f"/api/projects/{p['id']}/render");assert out.status_code==200
    download=client.get(f"/api/projects/{p['id']}/download");assert download.status_code==200 and download.content[:4]==b'ftyp'
