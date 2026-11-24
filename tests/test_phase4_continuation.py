import json
import sys
import tempfile
import unittest
import wave
from unittest.mock import patch
from fractions import Fraction
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"comfy"))
from phase4.timeline import LTX, PROFILES, boundaries, request_clock, trim
from phase4.storage import accepted, assemble, save_scene
from phase4.continuation import graph
from phase4 import continuation


class ClockTests(unittest.TestCase):
    def test_boundaries(self):
        fps = Fraction(24000,1001)
        durations = [Fraction(i,37) for i in range(10,40)]
        for overlap in (0,1,4):
            windows = boundaries(durations,fps,44100,PROFILES[LTX],overlap)
            self.assertEqual(windows[-1]["end"],round(sum(durations)*fps))
            for i,w in enumerate(windows):
                self.assertEqual(w["generated"]%8,1)
                self.assertEqual(w["generated"],w["leading"]+w["count"]+w["trailing"])
                self.assertEqual(w["leading"],overlap if i else 0)
                self.assertEqual(w["audio_start"],windows[i-1]["audio_end"] if i else 0)
                self.assertEqual(w["audio_end"],round(w["end"]*44100/fps))

    def test_graph(self):
        g = graph({"fps":24,"attempts":2},Path("run"),2)
        self.assertEqual(g["24"]["inputs"]["frames_number"],g["7"]["inputs"]["length"])
        self.assertEqual(g["24"]["inputs"]["frame_rate"],g["5"]["inputs"]["frame_rate"])
        self.assertEqual(g["gate"]["inputs"]["max_attempts"],2)
        self.assertEqual(g["save"]["inputs"]["images"],["19",0])
        self.assertEqual(g["19"]["inputs"]["images"],["gate",0])
        def visit(k,ancestors):
            self.assertNotIn(k,ancestors)
            for value in g[k]["inputs"].values():
                if isinstance(value,list):
                    visit(value[0],ancestors|{k})
        visit("save",set())

    def test_unknown(self):
        for model,fps in (("unknown",24),(LTX,25)):
            with self.assertRaises(ValueError):
                request_clock(model,4,2,fps,44100)

    def test_resume_at_second_scene_and_surface_failure(self):
        windows = request_clock(LTX,4,2,24,48000)
        c = dict(fps=24,attempts=2,windows=windows)
        posted = []
        def server(base,path,data=None):
            if path=="/queue":
                return dict(queue_pending=[],queue_running=[])
            if path=="/prompt":
                posted.append(data["prompt"]["save"]["inputs"]["index"])
                return dict(prompt_id="fixture")
            return {"fixture":{"status":{"status_str":"error"}}}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(continuation,"accepted",return_value=[{"window":windows[0]}]), \
                 patch.object(continuation,"rpc",side_effect=server), patch.object(continuation.time,"sleep"):
                continuation.coordinate(root,c,"key","offline")
            self.assertEqual(posted,[2])
            self.assertEqual(json.loads((root/"status.json").read_text())["state"],"failed")


class MediaTests(unittest.TestCase):
    def test_resume_and_export(self):
        try:
            import av
            import imageio_ffmpeg
            import numpy as np
            import torch
            from PIL import Image
        except ImportError as exc:
            self.skipTest(str(exc))
        fps,rate = 24,44100
        windows = request_clock(LTX,4,2,fps,rate)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audio = root/"source.wav"
            with wave.open(str(audio),"wb") as out:
                out.setparams((1,2,rate,0,"NONE",""))
                out.writeframes(np.arange(rate*4,dtype="<i2").tobytes())
            config = dict(fps=fps,rate=rate,windows=windows,inputs={"audio":str(audio)})
            for i,w in enumerate(windows):
                directory = root/f"scene_{i+1:03}"
                batch = torch.arange(w["generated"],dtype=torch.float32)[:,None,None,None].expand(-1,32,32,3)/255
                with self.assertRaises(ValueError):
                    trim(batch[:-1],w)
                frames = trim(batch,w)
                with self.assertRaises(ValueError):
                    save_scene(directory,frames,fps,"key",w,{"decision":"retry"},{})
                save_scene(directory,frames,fps,"key",w,{"decision":"accept"},{})
                rows = accepted(root,"key",windows)
                self.assertEqual(len(rows),i+1)
                self.assertEqual(np.asarray(Image.open(directory/"anchor.png"))[0,0,0],w["leading"]+w["count"]-1)
                with av.open(str(directory/"scene.mkv")) as f:
                    pixels = [int(x.to_ndarray(format="rgb24")[0,0,0]) for x in f.decode(video=0)]
                self.assertEqual(pixels,list(range(w["leading"],w["leading"]+w["count"])))
            result = assemble(root,rows,config)
            self.assertEqual((result["frames"],result["samples"]),(96,176400))
            with self.assertRaises(ValueError):
                accepted(root,"different",windows)
            (root/"scene_001"/"anchor.png").write_bytes(b"bad")
            with self.assertRaises(ValueError):
                accepted(root,"key",windows)


if __name__ == "__main__":
    unittest.main(verbosity=2)
