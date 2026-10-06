"""Check H3 conditioning and preservation of sound through film assembly."""
import json
import re
import shutil
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path
from unittest.mock import Mock, patch

import av
import numpy as np

from h3_video import build_h3_prompt, compose_native
from produce_video import ROOT, concatenate


class H3Tests(unittest.TestCase):
    def test_chinese_notes_are_translated_and_only_dialogue_stays_chinese(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'.cache') as temp:
            root = Path(temp)
            (root/'config').mkdir()
            shutil.copy2(ROOT/'config/planning.json',root/'config/planning.json')
            result = {'direction':'Close-up of Character 1, slowly turning her head under warm light.',
                      'appearances':{'Character 1':'adult Chinese woman in blue scrubs'}}
            response = Mock(status_code=200)
            response.json.return_value = {'choices':[{'message':{'content':json.dumps(result)}}]}
            story = {'style':'Live action','speakers':{'护士':{'appearance':'adult Chinese woman in blue scrubs'}}}
            shot = {'prompt':'Close-up of 护士','description':'护士打开握钥匙的手','camera':'缓慢推近',
                    'dialogue':[{'speaker':'护士','text':'我换成了盐水。'}]}
            config = json.loads((ROOT/'config/h3_studio_video.json').read_text())
            with patch('produce_video.ROOT',root), patch('add_dialogue.load_key',return_value='YOUR_API_KEY_HERE'), patch('requests.post',return_value=response) as request:
                graph = build_h3_prompt(config,story,shot,4,'translated',['cast.png'])
                build_h3_prompt(config,story,shot,4,'translated',['cast.png'])
                self.assertEqual(request.call_count,1)
            prompt = graph['5']['inputs']['prompt']
            self.assertIn('<d>[Chinese]我换成了盐水。</d>',prompt)
            outside = re.sub(r'<d>.*?</d>','',prompt)
            self.assertIsNone(re.search(r'[\u3400-\u9fff]',outside))
            self.assertNotIn('打开握钥匙',prompt)

    def test_reference_and_dialogue_conditioning(self):
        config = json.loads((ROOT / "config/h3_studio_video.json").read_text())
        story = {"style": "Live action", "speakers": {"甲": {"appearance": "adult woman"}}}
        shot = {"prompt": "Close up", "camera": "slow push in", "dialogue": [{"speaker": "甲", "text": "证据在这里。"}]}
        graph = build_h3_prompt(config, story, shot, 2, "test", ["test/cast.png"])
        text = graph["5"]["inputs"]["prompt"]
        self.assertIn("<Picture 1>", text)
        self.assertIn("<d>[Chinese]证据在这里。</d>", text)
        self.assertEqual(graph["5"]["inputs"]["ref_images.ref_image_1"], ["71", 0])
        self.assertEqual(graph["58"]["class_type"], "SaveVideo")
        self.assertNotIn("14", graph)

    def test_native_stereo_survives_trim_and_subtitles(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".cache") as temp:
            run = Path(temp)
            for name in ("clips", "final", "audio", "subtitles"):
                (run / name).mkdir()
            clips = []
            for index in (1, 2):
                path = run / "clips" / f"shot_{index:02d}.mp4"
                clips.append(path)
                with av.open(str(path), "w") as output:
                    video = output.add_stream("libx264", rate=24)
                    video.width, video.height, video.pix_fmt = 128, 128, "yuv420p"
                    sound = output.add_stream("aac", rate=32000)
                    sound.layout = "stereo"
                    for i in range(28):
                        frame = av.VideoFrame.from_ndarray(np.full((128,128,3), index*50, dtype=np.uint8), format="rgb24")
                        frame.pts, frame.time_base = i, Fraction(1,24)
                        for packet in video.encode(frame):
                            output.mux(packet)
                    samples = (0.1*np.sin(np.arange(40000)*2*np.pi*300/32000)).astype(np.float32)
                    frame = av.AudioFrame.from_ndarray(np.stack([samples,samples*.5]), format="fltp", layout="stereo")
                    frame.sample_rate, frame.pts, frame.time_base = 32000, 0, Fraction(1,32000)
                    for packet in sound.encode(frame):
                        output.mux(packet)
                    for stream in (video,sound):
                        for packet in stream.encode(None):
                            output.mux(packet)
            concatenate(clips,run/"final/film.mp4",24,24)
            story={"shots":[{"dialogue":[]},{"dialogue":[]}]}
            config={"fps":24,"width":128,"height":128,"output_frames_per_clip":24}
            tts={"subtitle_font":"C:/Windows/Fonts/msyh.ttc","subtitle_font_size":20}
            specs=compose_native(run,story,config,tts)
            self.assertEqual(specs["frames"],48)
            self.assertGreater(specs["audio_rms"],.01)
            with av.open(str(run/"final/film_with_dialogue.mp4")) as source:
                self.assertEqual(source.streams.audio[0].channels,2)
                self.assertEqual(source.streams.audio[0].rate,32000)
                self.assertAlmostEqual(source.duration/av.time_base,2,delta=.05)


if __name__=="__main__":
    unittest.main()
