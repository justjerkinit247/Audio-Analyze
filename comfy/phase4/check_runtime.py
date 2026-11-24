"""Read-only CPU integration check using the portable ComfyUI interpreter."""
import asyncio
import json
from pathlib import Path
import sys


async def check(comfy_path, packages, api):
    sys.path.insert(0,str(comfy_path))
    sys.argv[1:] = ["--cpu"]
    import comfy.options
    comfy.options.enable_args_parsing()
    import nodes
    import execution
    from comfy_execution.graph import DynamicPrompt
    for name in ("nodes_custom_sampler","nodes_lt","nodes_lt_audio","nodes_video"):
        assert await nodes.load_custom_node(str(comfy_path/"comfy_extras"/(name+".py")))
    for name in ("ComfyUI_AudioAnalyze_Orchestration","ComfyUI_AudioAnalyze_RenderBridge"):
        assert await nodes.load_custom_node(str(packages/name))
    registered = nodes.NODE_CLASS_MAPPINGS
    graph_module = sys.modules[registered["AAOContinuous"].__module__]
    parent = json.loads(api.read_text(encoding="utf-8-sig"))
    for n in parent.values():
        if n["class_type"]=="AAOInputs":
            config = registered["AAOInputs"]().execute(**n["inputs"])[0]
    recipe = graph_module.graph({"fps":24,"attempts":2},Path("fixture"),2)
    for title,g in (("operator",parent),("scene",recipe)):
        valid, reason, outputs, errors = await execution.validate_prompt("offline",g,None)
        if not valid or errors:
            raise RuntimeError((title,reason,errors))
        print(f"{title} validated: {len(g)} nodes, targets {outputs}")
    loop = sys.modules[registered["AAOASMOMotionLoop"].__module__]
    render = loop.capture_recipe(DynamicPrompt(recipe),"gate",config)
    retry = loop.retry_graph(dict(recipe=render,attempt=2,context={},seed_image=None),2)
    print(f"native positive route and {len(retry['expand'])} retry expansion nodes verified")
    import torch
    from comfy_extras.nodes_audio import load
    from unittest.mock import patch
    sound, rate = load(config["audio"])
    windows = graph_module.request_clock(graph_module.LTX,4,2,24,rate)
    finish = registered["AAOFinishScene"]()
    finish_module = sys.modules[type(finish).__module__]
    for w in windows:
        meta = dict(fps=24,rate=rate,window=w)
        scene = dict(phase4=meta,source_audio_path=config["audio"])
        context = dict(plan=dict(phase4=meta),clip_index=1,fps=24)
        batch = torch.arange(w["generated"])[:,None,None,None].expand(-1,2,2,3)
        with patch.object(finish_module,"checked_scene",return_value=scene):
            frames,audio,_,_ = finish.execute(batch,context)
            context["asmo_review"] = {"decision":"accept"}
            again,_,_,_ = finish.execute(frames,context)
        assert torch.equal(frames,again) and len(frames)==w["count"]
        assert frames[-1,0,0,0].item()==w["leading"]+w["count"]-1
        assert torch.equal(audio["waveform"][0],sound[:,w["audio_start"]:w["audio_end"]])
    print("Both native FinishScene passes preserve all 96 requested frames and match original decoded audio sample-for-sample")


if __name__ == "__main__":
    comfy_path, packages_path, api_path = map(Path,sys.argv[1:4])
    asyncio.run(check(comfy_path.resolve(),packages_path.resolve(),api_path.resolve()))
