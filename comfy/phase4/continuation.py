"""A short user submission starts a local coordinator. Each child is a normal Comfy job."""
from pathlib import Path
import hashlib
import json
import re
import threading
import time
import urllib.request
import uuid

from .storage import accepted, assemble, atomic_json, digest, load, save_scene
from .timeline import LTX, request_clock

HERE = Path(__file__).parent
LOCK = threading.Lock()
ACTIVE = set()


def run_root(directory):
    import folder_paths
    parent = Path(folder_paths.get_output_directory()).resolve()/"ASMO_1_4"
    path = Path(directory).resolve()
    if path.parent != parent or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}",path.name):
        raise ValueError("Invalid continuation run directory")
    return path


def graph(config, root, index):
    recipe = load(HERE/"native_recipe.json")
    fps = config["fps"]
    recipe["plan"] = dict(class_type="AAOContinuationPlan",inputs=dict(directory=str(root),index=index))
    recipe["18"] = dict(class_type="AAOSceneRenderInputs",inputs=dict(plan=["plan",0],clip_index=1,
                        fps=fps,prompt_mode="asmo_motion",motion_override="",max_chars=5000))
    recipe["gate"] = dict(class_type="AAOASMOMotionLoop", inputs=dict(images=["3",0],
                          render_context=["18",7],seed_image=["18",0],max_attempts=config["attempts"]))
    recipe["19"] = dict(class_type="AAOFinishScene",inputs=dict(images=["gate",0],render_context=["gate",1]))
    recipe["save"] = dict(class_type="AAOContinuationSave",inputs=dict(images=["19",0],context=["gate",1],
                          timing=["19",3],directory=str(root),index=index))
    for ident in ("4","20","21"):
        if recipe[ident]["inputs"]["ckpt_name"] != LTX:
            raise ValueError("Incompatible native model or audio/video VAE")
    for ident,port,expected in (("7","length",["18",3]),("24","frames_number",["18",3]),
                                ("24","frame_rate",["18",4]),("5","frame_rate",["18",4]),
                                ("23","latent",["7",0]),("23","image",["6",0]),
                                ("6","image",["18",0]),("25","audio_latent",["24",0]),
                                ("25","video_latent",["23",0])):
        if recipe[ident]["inputs"].get(port) != expected:
            raise ValueError(f"Incompatible native latent or seed connection at {ident}.{port}")
    return recipe


def rpc(base, path, data=None):
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(base+path, data=body, headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def coordinate(root, config, key, base):
    status = root/"status.json"
    try:
        rows = accepted(root,key,config["windows"])
        if len(rows)==len(config["windows"]) and status.exists():
            old = load(status)
            if old.get("state")=="complete" and (root/"continuous.mp4").is_file():
                if old["export"].get("sha256")==digest(root/"continuous.mp4"):
                    return
        for window in config["windows"][len(rows):]:
            index = window["index"]
            prompt = graph(config, root, index)
            queue = rpc(base,"/queue")
            jobs = queue["queue_running"] + queue["queue_pending"]
            ids = [j[1] for j in jobs if j[2].get("save",{}).get("inputs",{}).get("directory")==str(root)]
            if ids:
                raise RuntimeError("An earlier scene job is still active. Resume after it ends.")
            atomic_json(status,dict(state="submitting",scene=index))
            job = rpc(base,"/prompt",dict(prompt=prompt,client_id=uuid.uuid4().hex))["prompt_id"]
            atomic_json(status,dict(state="rendering",scene=index,prompt_id=job))
            while True:
                time.sleep(3)
                item = rpc(base,"/history/"+job).get(job)
                if item is not None:
                    if item["status"]["status_str"] != "success":
                        raise RuntimeError(f"Scene {index} failed. See ComfyUI history {job}")
                    break
                queue = rpc(base,"/queue")
                if not any(j[1]==job for j in queue["queue_running"]+queue["queue_pending"]):
                    if not rpc(base,"/history/"+job).get(job):
                        raise RuntimeError(f"Scene {index} was cancelled or its history was cleared")
            rows = accepted(root,key,config["windows"])
            if len(rows) != index:
                raise RuntimeError("Child finished without its accepted checkpoint")
        atomic_json(status,dict(state="assembling"))
        result = assemble(root,rows,config)
        result["sha256"] = digest(root/"continuous.mp4")
        atomic_json(status,dict(state="complete",export=result))
    except Exception as exc:
        atomic_json(status,dict(state="failed",error=str(exc)))
    finally:
        with LOCK:
            ACTIVE.discard(root)


class Continuous:
    CATEGORY = "Audio Analyze/Local Video"
    FUNCTION = "execute"
    RETURN_TYPES = ("STRING",)
    OUTPUT_NODE = True

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    @classmethod
    def INPUT_TYPES(cls):
        return {"required":{"inputs":("AAO_CONFIG",),"model":([LTX],),
                "duration":("FLOAT",{"default":4.0,"min":2.0,"max":400.0}),
                "fps":("INT",{"default":24,"min":1,"max":120}),
                "scenes":("INT",{"default":2,"min":1,"max":20}),
                "attempts":("INT",{"default":2,"min":1,"max":4}),
                "run_name":("STRING",{"default":"phase4-preview"})}}

    def execute(self, inputs, model, duration, fps, scenes, attempts, run_name):
        import av
        import folder_paths
        from server import PromptServer
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}",run_name) or len(inputs["seeds"]) != 1:
            raise ValueError("Supply one identity seed and an alphanumeric run name")
        root = Path(folder_paths.get_output_directory()).resolve()/"ASMO_1_4"/run_name
        root.mkdir(parents=True,exist_ok=True)
        with av.open(inputs["audio"]) as container:
            rate = container.streams.audio[0].codec_context.sample_rate
        windows = request_clock(model,duration,scenes,fps,rate)
        files = [inputs["audio"],*inputs["seeds"]]+([inputs["lyrics"]] if inputs["lyrics"] else [])
        config = dict(version="1.4", strategy="last_frame_auto",model=model,inputs=inputs,
                      input_hashes={p:digest(p) for p in files},fps=fps,rate=rate,attempts=attempts,
                      windows=windows,adapter_hashes={p.name:digest(p) for p in
                      [*HERE.glob("*.py"),HERE/"native_recipe.json",HERE.parent/"asmo_loop.py",
                       HERE.parent/"nodes.py",HERE.parent/"pipeline_worker.py"]})
        source = Path(inputs["repo"])/"src"/"audio_analyze"
        config["repository_modules"] = {str(p.relative_to(source)):digest(p) for p in source.rglob("*.py")}
        key = hashlib.sha256(json.dumps(config,sort_keys=True).encode()).hexdigest()
        with LOCK:
            if root in ACTIVE:
                raise RuntimeError("This run is already active")
            manifest = root/"manifest.json"
            if manifest.exists() and load(manifest)["key"] != key:
                raise ValueError("Resume configuration changed. Choose another run name.")
            atomic_json(manifest,dict(key=key,config=config))
            ACTIVE.add(root)
        base = f"http://127.0.0.1:{PromptServer.instance.port}"
        threading.Thread(target=coordinate,args=(root,config,key,base),daemon=True).start()
        message = str(root/"status.json")
        return {"ui":{"text":[message]},"result":(message,)}


class Plan:
    CATEGORY = "Audio Analyze/Local Video"
    FUNCTION = "execute"
    RETURN_TYPES = ("AAO_PLAN",)

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    @classmethod
    def INPUT_TYPES(cls):
        return {"required":{"directory":("STRING",),"index":("INT",{"min":1})}}

    def execute(self,directory,index):
        from ..nodes import planner_core
        root = run_root(directory)
        manifest = load(root/"manifest.json")
        c = manifest["config"]
        rows = accepted(root,manifest["key"],c["windows"])
        if index != len(rows)+1:
            raise ValueError("Scene order changed")
        w = c["windows"][index-1]
        inputs = c["inputs"].copy()
        if any(digest(p)!=v for p,v in c["input_hashes"].items()):
            raise ValueError("Original inputs changed during run")
        if rows:
            inputs["seeds"] = [str(root/f"scene_{index-1:03}"/"anchor.png")]
        core = planner_core()
        started = time.time()
        import torch
        if torch.cuda.is_available():
            torch.cuda.reset_peak_memory_stats()
        plan = core.run_worker(inputs,provider="ollama",ollama_model="gemma3:4b",aspect_ratio="9:16",
                               scene_seconds=w["count"]/c["fps"],start_seconds=w["start"]/c["fps"],
                               continuous_grid=True)
        scene = core.select_scene(plan,1)
        for field,frame in (("start",w["start"]),("end",w["end"])):
            if abs(scene["scene"][field]-frame/c["fps"]) > 0.00051:
                raise ValueError("Semantic plan does not cover requested master interval")
        plan["phase4"] = dict(window=w,rate=c["rate"],fps=c["fps"],started=started,root=directory,
                              identity=c["inputs"]["seeds"][0],model=c["model"],
                              history=[dict(index=r["window"]["index"],prompt=r["review"]["positive_sent_to_ltx"],
                                            observation=r["review"].get("gemma_review")) for r in rows])
        return (plan,)


class Save:
    CATEGORY = Plan.CATEGORY
    FUNCTION = "execute"
    RETURN_TYPES = ()
    OUTPUT_NODE = True

    @classmethod
    def INPUT_TYPES(cls):
        return {"required":dict(images=("IMAGE",),context=("AAO_RENDER_CONTEXT",),timing=("STRING",),
                                directory=("STRING",),index=("INT",{"min":1}))}

    def execute(self,images,context,timing,directory,index):
        root = run_root(directory)
        meta = context["plan"]["phase4"]
        manifest = load(root/"manifest.json")
        if directory != meta["root"] or meta["window"] != manifest["config"]["windows"][index-1]:
            raise ValueError("Invalid accepted scene context")
        import torch
        peak = torch.cuda.max_memory_allocated() if torch.cuda.is_available() else None
        save_scene(root/f"scene_{index:03}",images,meta["fps"],manifest["key"],meta["window"],
                   context["asmo_review"],dict(seconds=time.time()-meta["started"],timing=json.loads(timing),
                   peak_torch_cuda_allocated_bytes=peak,model_reload_seconds=None,
                   source_plan=context["plan"]["plan_path"],identity=meta["identity"]))
        return ()


NODES = {"AAOContinuous":Continuous,"AAOContinuationPlan":Plan,"AAOContinuationSave":Save}
