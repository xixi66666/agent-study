"""Integration checks for version preservation, cache invalidation and scoped jobs."""

import asyncio
import copy
import hashlib
import json
import shutil
import tempfile
import threading
import unittest
from fractions import Fraction
from pathlib import Path
from unittest.mock import AsyncMock, patch

import av
import numpy as np
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

import server


class StudioTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=server.ROOT/".cache")
        self.root = Path(self.temporary.name)
        (self.root/"config").mkdir()
        (self.root/"prompts/stories").mkdir(parents=True)
        for name in ("cat_comic_video.json","fun_camera_video.json","h3_studio_video.json","mimo_tts.json"):
            shutil.copy2(server.ROOT/"config"/name,self.root/"config"/name)
        shutil.copy2(server.ROOT/"prompts/stories/cat_biscuit_mystery.json",self.root/"prompts/stories/cat_biscuit_mystery.json")
        self.submitted=[]
        self.cancelled=[]
        self.uploaded=[]
        self.hold=False
        self.fake=web.Application()
        async def prompt(request):
            payload=await request.json()
            self.submitted.append(payload)
            return web.json_response({"prompt_id":payload["prompt_id"]})
        async def history(request):
            prompt_id=request.match_info["id"]
            if self.hold:
                return web.json_response({})
            return web.json_response({prompt_id:{"status":{"status_str":"success"},"outputs":{"58":{"images":[{"filename":"new.mp4","subfolder":"test"}]}}}})
        async def cancel(request):
            self.cancelled.append(request.match_info["id"])
            return web.json_response({"cancelled":True})
        async def upload(request):
            data = await request.post()
            self.uploaded.append(data['image'].filename)
            return web.json_response({"name":"reference.png","subfolder":"test"})
        self.fake.router.add_post('/prompt',prompt)
        self.fake.router.add_get('/history/{id}',history)
        self.fake.router.add_post('/api/jobs/{id}/cancel',cancel)
        self.fake.router.add_post('/upload/image',upload)
        self.comfy=TestServer(self.fake)
        await self.comfy.start_server()
        cfg=server.read_json(self.root/"config/cat_comic_video.json")
        cfg.update(comfyui_url=str(self.comfy.make_url('/')).rstrip('/'),width=128,height=256,frames=5,output_frames_per_clip=4)
        self.cfg=cfg
        self.tts=server.read_json(self.root/"config/mimo_tts.json")
        self.tts["subtitle_band_height"]=80
        self.tts["dialogue_start_offset_seconds"]=.01
        server.write_json(self.root/"config/mimo_tts.json",self.tts)
        story=server.read_json(self.root/"prompts/stories/cat_biscuit_mystery.json")
        story["shots"]=story["shots"][:2]
        story["speakers"]={}
        for shot in story["shots"]:
            shot.pop("start_image",None)
            shot["dialogue"]=[]
        self.story=story
        run=self.root/"runs/source"
        for name in ("clips","references","prompts","logs"):
            (run/name).mkdir(parents=True)
        self.make_video(self.root/"ComfyUI/output/test/new.mp4",85)
        shots=[]
        for index in (1,2):
            clip=run/"clips"/f"shot_{index:02d}.mp4"
            self.make_video(clip,20*index)
            specs=server.inspect_clip(clip,run/"references"/f"shot_{index:02d}_last.png")
            shots.append({"status":"success","specs":specs,"title":story["shots"][index-1]["title"]})
        server.write_json(run/"storyboard.json",story)
        server.write_json(run/"config.json",cfg)
        server.write_json(run/"manifest.json",{"run_id":"source","title":story["title"],"status":"complete","shots":shots})
        self.original=(run/"manifest.json").read_bytes()
        self.app=server.create_app(self.root)
        self.client=TestClient(TestServer(self.app))
        await self.client.start_server()
        self.studio=self.app["studio"]
        self.project=self.studio.list_projects()[0]["id"]
        project=self.studio.project(self.project)
        project["tts"]=self.tts
        server.write_json(self.studio.project_path(self.project),project)

    def make_video(self,path,color,fps=24):
        path.parent.mkdir(parents=True,exist_ok=True)
        with av.open(str(path),'w') as output:
            stream=output.add_stream('libx264',rate=fps)
            stream.width,stream.height=128,256
            stream.pix_fmt='yuv420p'
            for index in range(5):
                frame=av.VideoFrame.from_ndarray(np.full((256,128,3),color+index,dtype=np.uint8),format='rgb24')
                frame.pts=index
                frame.time_base=Fraction(1,fps)
                for packet in stream.encode(frame):
                    output.mux(packet)
            for packet in stream.encode():
                output.mux(packet)

    async def asyncTearDown(self):
        await self.client.close()
        await self.comfy.close()
        self.temporary.cleanup()

    async def request(self,path,method='GET',payload=None,**kwargs):
        response=await self.client.request(method,path,json=payload,headers={'X-AIMedia-Client':'studio',**kwargs.pop('headers',{})},**kwargs)
        return response,await response.json()

    async def wait_job(self,job):
        await asyncio.wait_for(self.studio.tasks[job['id']],10)
        return self.studio.jobs[job['id']]

    async def test_save_versions_conflicts_and_no_credentials(self):
        payload=copy.deepcopy(self.studio.project(self.project))
        payload['story']['title']='修改后的故事'
        response,saved=await self.request('/api/projects/'+self.project,'PUT',payload)
        self.assertEqual(response.status,200)
        self.assertEqual(saved['revision'],2)
        response,history=await self.request('/api/projects/'+self.project+'/revisions/1')
        self.assertEqual(history['story']['title'],self.story['title'])
        response,_=await self.request('/api/projects/'+self.project,'PUT',payload)
        self.assertEqual(response.status,409)
        saved['tts']['api_key']='YOUR_API_KEY_HERE'
        response,_=await self.request('/api/projects/'+self.project,'PUT',saved)
        self.assertEqual(response.status,400)

    def camera_project(self):
        project=copy.deepcopy(self.studio.project(self.project))
        profile=server.read_json(self.root/'config/fun_camera_video.json')
        project['video']={**profile,**self.cfg,'generation_mode':'fun_camera','diffusion_model':profile['diffusion_model'],'vae':profile['vae'],'clip_vision':profile['clip_vision'],'fps':16}
        project['story']['shots'][0]['start_image']='runs/source/references/shot_01_last.png'
        return project

    def install_camera_placeholders(self,config):
        for field,folder in (('diffusion_model','diffusion_models'),('vae','vae'),('clip_vision','clip_vision'),('text_encoder','text_encoders')):
            target=self.root/'ComfyUI/models'/folder/config[field]
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(b'test fixture')

    async def test_camera_generation_conditions_sampler_and_outputs_new_fps(self):
        project=self.camera_project()
        project['story']['shots'][0].update(camera_motion='Zoom In',camera_speed=.7,seed=1234)
        self.install_camera_placeholders(project['video'])
        server.write_json(self.studio.project_path(self.project),project)
        self.make_video(self.root/'ComfyUI/output/test/new.mp4',90,fps=16)
        job=await self.studio.start_job(self.project,'shot',1)
        result=await self.wait_job(job)
        self.assertEqual(result['status'],'complete',result.get('error'))
        graph=self.submitted[0]['prompt']
        self.assertEqual(graph['60']['inputs']['camera_pose'],'Zoom In')
        self.assertEqual(graph['60']['inputs']['speed'],.7)
        self.assertEqual(graph['55']['class_type'],'WanCameraImageToVideo')
        for field,output in (('positive',0),('negative',1),('latent_image',2)):
            self.assertEqual(graph['3']['inputs'][field],['55',output])
        self.assertEqual(graph['55']['inputs']['camera_conditions'],['60',0])
        self.assertEqual(graph['55']['inputs']['clip_vision_output'],['62',0])
        self.assertEqual(graph['62']['inputs']['image'],['56',0])
        info=self.studio.run_info(job['run_id'])
        self.assertEqual(info['shots'][0]['specs']['fps'],16)
        self.assertIsNone(info['shots'][1]['clip'])
        self.assertEqual((self.root/'runs/source/manifest.json').read_bytes(),self.original)

    async def test_camera_preflight_and_invalid_settings_do_not_submit(self):
        project=self.camera_project()
        for section,field,value in (('video','generation_mode','unknown'),('video','vae','wan2.2_vae.safetensors'),('shot','camera_motion','Orbit'),('shot','camera_speed',float('nan')),('shot','camera_speed',11)):
            invalid=copy.deepcopy(project)
            target=invalid['video'] if section=='video' else invalid['story']['shots'][0]
            target[field]=value
            with self.assertRaises(web.HTTPBadRequest):
                self.studio.validate(invalid)
        server.write_json(self.studio.project_path(self.project),project)
        with self.assertRaises(web.HTTPConflict):
            await self.studio.start_job(self.project,'shot',1)
        self.install_camera_placeholders(project['video'])
        project['story']['shots'][0].pop('start_image')
        server.write_json(self.studio.project_path(self.project),project)
        with self.assertRaises(web.HTTPBadRequest):
            await self.studio.start_job(self.project,'shot',1)
        self.assertEqual(self.submitted,[])
        self.assertEqual(len(list((self.root/'runs').iterdir())),1)

    async def test_camera_motion_and_speed_invalidate_only_affected_independent_clips(self):
        project=self.camera_project()
        project['video']['use_previous_frame']=False
        explicit=copy.deepcopy(project['story'])
        explicit['shots'][0].update(camera_motion='Static',camera_speed=1)
        self.assertEqual(self.studio.visual_signature(project['video'],project['story'],0),self.studio.visual_signature(project['video'],explicit,0))
        source=self.root/'runs/source'
        server.write_json(source/'config.json',project['video'])
        server.write_json(source/'storyboard.json',project['story'])
        for field,value in (('camera_motion','Pan Left'),('camera_speed',.5)):
            modified=copy.deepcopy(project)
            modified['story']['shots'][0][field]=value
            run=self.studio.prepare_run(modified,'generate',1)
            info=self.studio.run_info(run.name)
            self.assertIsNone(info['shots'][0]['clip'])
            self.assertIsNotNone(info['shots'][1]['clip'])
        legacy=copy.deepcopy(self.cfg)
        explicit={**legacy,'generation_mode':'wan22'}
        self.assertEqual(self.studio.visual_signature(legacy,self.story,0),self.studio.visual_signature(explicit,self.story,0))

    async def test_original_clips_reused_and_composition_has_expected_duration(self):
        job=await self.studio.start_job(self.project,'compose')
        result=await self.wait_job(job)
        self.assertEqual(result['status'],'complete',result.get('error'))
        self.assertEqual(self.submitted,[])
        run=self.studio.run_path(job['run_id'])
        specs=server.inspect_clip(run/'final/film.mp4')
        self.assertEqual(specs['frames'],8)
        self.assertEqual(specs['fps'],24)
        self.assertEqual((self.root/'runs/source/manifest.json').read_bytes(),self.original)

    async def test_single_shot_changes_prompt_and_preserves_other_shot(self):
        project=self.studio.project(self.project)
        project['story']['shots'][0]['seed']=42
        project['story']['shots'][0]['description']='新的场景描述'
        server.write_json(self.studio.project_path(self.project),project)
        job=await self.studio.start_job(self.project,'shot',1)
        result=await self.wait_job(job)
        self.assertEqual(result['status'],'complete',result.get('error'))
        self.assertEqual(len(self.submitted),1)
        graph=self.submitted[0]['prompt']
        self.assertEqual(graph['3']['inputs']['seed'],42)
        self.assertIn('新的场景描述',graph['6']['inputs']['text'])
        run=self.studio.run_path(job['run_id'])
        self.assertEqual((run/'clips/shot_02.mp4').read_bytes(),(self.root/'runs/source/clips/shot_02.mp4').read_bytes())
        self.assertEqual((self.root/'runs/source/manifest.json').read_bytes(),self.original)

    async def test_changes_invalidate_following_dependent_shots(self):
        project=self.studio.project(self.project)
        project['story']['shots'][0]['prompt']+=' New action.'
        run=self.studio.prepare_run(project,'generate',1)
        manifest=server.read_json(run/'manifest.json')
        self.assertTrue(all(not entry for entry in manifest['shots']))

    async def test_stop_is_scoped_and_resuming_uses_new_prompt_after_cancel(self):
        self.hold=True
        job=await self.studio.start_job(self.project,'shot',1)
        for _ in range(100):
            if self.submitted:break
            await asyncio.sleep(.02)
        self.assertEqual(len(self.submitted),1)
        original_id=self.submitted[0]['prompt_id']
        await self.studio.cancel(job)
        result=await self.wait_job(job)
        self.assertEqual(result['status'],'stopped')
        self.assertEqual(self.cancelled,[original_id])
        self.hold=False
        response,resumed=await self.request('/api/jobs/'+job['id']+'/resume','POST',{})
        self.assertEqual(response.status,200)
        self.assertEqual((await self.wait_job(resumed))['status'],'complete')
        self.assertEqual(len(self.submitted),2)
        self.assertNotEqual(original_id,self.submitted[1]['prompt_id'])

    async def test_cross_origin_and_media_traversal_are_rejected(self):
        response,_=await self.request('/api/projects/'+self.project,'PUT',self.studio.project(self.project),headers={'Origin':'https://example.com'})
        self.assertEqual(response.status,403)
        response=await self.client.get('/media/runs/%2e%2e/config/mimo_tts.json')
        self.assertEqual(response.status,403)
        response=await self.client.get('/media/runs/source/clips/shot_01.mp4',headers={'Range':'bytes=0-99'})
        self.assertEqual(response.status,206)
        self.assertEqual(len(await response.read()),100)

    async def test_status_reports_only_key_presence(self):
        with patch.object(server,'load_key',return_value='YOUR_API_KEY_HERE'):
            response,status=await self.request('/api/status?project='+self.project)
            self.assertEqual(response.status,200)
            self.assertTrue(status['mimo_configured'])
            self.assertNotIn('YOUR_API_KEY_HERE',json.dumps(status))

    async def test_h3_frame_rules_and_native_dialogue_cache(self):
        project = self.studio.project(self.project)
        project['video'] = server.read_json(self.root/'config/h3_studio_video.json')
        project['video']['text_encoder_device'] = 'cpu'
        project['story']['speakers'] = {'甲': {'voice':'苏打','style':'冷静','appearance':'adult man'}}
        project['story']['shots'][0]['dialogue'] = [{'speaker':'甲','text':'证据在这里。'}]
        self.studio.validate(project)
        first = self.studio.visual_signature(project['video'], project['story'], 0)
        project['video']['text_encoder_device'] = 'default'
        self.studio.validate(project)
        self.assertEqual(first, self.studio.visual_signature(project['video'], project['story'], 0))
        project['story']['shots'][0]['dialogue'][0]['text'] = '证据被换过。'
        self.assertNotEqual(first, self.studio.visual_signature(project['video'], project['story'], 0))
        for frames, fps in ((121,24),(124,30)):
            invalid = copy.deepcopy(project)
            invalid['video'].update(frames=frames,fps=fps)
            with self.assertRaises(web.HTTPBadRequest):
                self.studio.validate(invalid)

    async def test_stopping_during_h3_translation_never_submits_a_prompt(self):
        config = server.read_json(self.root/'config/h3_studio_video.json')
        config['comfyui_url'] = self.cfg['comfyui_url']
        project = self.studio.create_project(self.story,config,self.tts)
        started, release = threading.Event(), threading.Event()
        def delayed_build(*args):
            started.set()
            release.wait(3)
            return {}
        with patch.object(self.studio,'h3_status',return_value={'ready':True}), patch.object(server,'build_prompt',side_effect=delayed_build):
            job = await self.studio.start_job(project['id'],'shot',1)
            for _ in range(100):
                if started.is_set(): break
                await asyncio.sleep(.01)
            self.assertTrue(started.is_set())
            await self.studio.cancel(job)
            release.set()
            self.assertEqual((await self.wait_job(job))['status'],'stopped')
            self.assertEqual(self.submitted,[])

    async def test_h3_explicit_cast_reference_precedes_previous_frame(self):
        story = copy.deepcopy(self.story)
        story['shots'].append(copy.deepcopy(story['shots'][1]))
        story['shots'][2]['reference_shots'] = [1]
        config = server.read_json(self.root/'config/h3_studio_video.json')
        config.update(comfyui_url=self.cfg['comfyui_url'],use_previous_frame=True)
        job = {'id':'reference-test','project_id':self.project,'run_id':'source','action':'shot','selected':3,'logs':[]}
        self.studio.stops[job['id']] = threading.Event()
        with patch.object(server,'build_prompt',side_effect=ValueError('Capture reference only')):
            with self.assertRaises(ValueError):
                await self.studio.generate(job,self.root/'runs/source',story,config,{'shots':[{}, {}, {}]})
        self.assertEqual(self.uploaded,['shot_01_last.png'])

    async def test_validation_run_does_not_break_run_inventory(self):
        (self.root/'runs/h3_check').mkdir()
        server.write_json(self.root/'runs/h3_check/manifest.json', {'status':'complete'})
        response, runs = await self.request('/api/runs')
        self.assertEqual(response.status, 200)
        self.assertNotIn('h3_check', [run['id'] for run in runs])

    async def test_planning_saves_story_and_preserves_user_revision(self):
        planned = copy.deepcopy(self.story)
        planned['title'] = '规划结果'
        with patch.object(server,'load_key',return_value='YOUR_API_KEY_HERE'), patch('plan_story.plan',new_callable=AsyncMock,return_value=planned) as planner:
            payload = {'brief':'封闭空间内四个人发现证据被调换','seconds':10,'revision':0}
            response, _ = await self.request('/api/projects/'+self.project+'/plan','POST',payload)
            self.assertEqual(response.status,409)
            payload['revision'] = 1
            response, job = await self.request('/api/projects/'+self.project+'/plan','POST',payload)
            self.assertEqual(response.status,202)
            result = await self.wait_job(job)
            self.assertEqual(result['status'],'complete')
            self.assertFalse((self.studio.run_path(job['run_id'])/'clips/shot_01.mp4').exists())
            self.assertEqual(self.studio.project(self.project)['story']['title'],'规划结果')
            self.assertEqual(self.studio.project(self.project)['revision'],2)
            self.assertEqual(planner.await_count,1)
        saved = self.studio.project(self.project)
        release = asyncio.Event()
        async def delayed_plan(*args, **kwargs):
            await release.wait()
            return planned
        with patch.object(server,'load_key',return_value='YOUR_API_KEY_HERE'), patch('plan_story.plan',side_effect=delayed_plan):
            payload['revision'] = 2
            response, job = await self.request('/api/projects/'+self.project+'/plan','POST',payload)
            saved['revision'] = 3
            saved['story']['title'] = '用户修改'
            server.write_json(self.studio.project_path(self.project),saved)
            release.set()
            self.assertEqual((await self.wait_job(job))['status'],'failed')
            self.assertEqual(self.studio.project(self.project)['story']['title'],'用户修改')

    async def test_workspace_summaries_follow_production_and_draft_changes(self):
        response, data = await self.request('/api/projects')
        self.assertEqual(response.status, 200)
        original = next(item for item in data['projects'] if item['id'] == self.project)
        self.assertEqual(original['stage'], 'visual_ready')
        self.assertEqual(original['completed_shots'], 2)
        response, blank = await self.request('/api/projects', 'POST', {'blank': True, 'title': 'Workspace draft'})
        self.assertEqual(response.status, 201)
        _, data = await self.request('/api/projects')
        self.assertEqual(len(data['projects']), 2)
        self.assertEqual(next(item for item in data['projects'] if item['id'] == blank['id'])['stage'], 'draft')
        _, job = await self.request('/api/projects/'+self.project+'/jobs', 'POST', {'action': 'compose'})
        self.assertEqual((await self.wait_job(job))['status'], 'complete')
        _, data = await self.request('/api/projects')
        completed = next(item for item in data['projects'] if item['id'] == self.project)
        self.assertEqual(completed['stage'], 'complete')
        self.assertEqual(completed['versions'], 2)
        self.assertTrue(completed['final'].endswith('/final/film.mp4'))
        _, runs = await self.request('/api/runs')
        self.assertTrue(next(item for item in runs if item['id'] == job['run_id'])['final'])
        project = self.studio.project(self.project)
        project['story']['title'] = 'Updated draft'
        response, _ = await self.request('/api/projects/'+self.project, 'PUT', project)
        self.assertEqual(response.status, 200)
        _, data = await self.request('/api/projects')
        updated = next(item for item in data['projects'] if item['id'] == self.project)
        self.assertEqual(updated['stage'], 'changed')
        self.assertTrue(updated['final'])


if __name__=='__main__':
    unittest.main(verbosity=2)
