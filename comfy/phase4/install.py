"""Install narrowly scoped hooks into the workstation's existing RenderBridge."""
from pathlib import Path
from datetime import datetime
import argparse
import shutil
import os

HERE = Path(__file__).parent
HOOKS = {
    "ComfyUI_AudioAnalyze_Orchestration/worker.py": [
        ("beat_align=True,", "beat_align=not options.get('continuous_grid', False),")],
    "ComfyUI_AudioAnalyze_RenderBridge/__init__.py": [
        ('__all__ =', 'from .phase4.continuation import NODES\nNODE_CLASS_MAPPINGS.update(NODES)\n\n__all__ =')],
    "ComfyUI_AudioAnalyze_RenderBridge/nodes.py": [
        ('        waveform, sample_rate = load(str(audio_path))', '''        if "phase4" in plan:
            from .phase4.storage import audio_window
            meta = plan["phase4"]
            w = meta["window"]
            waveform, sample_rate = audio_window(audio_path,w["audio_start"],w["audio_end"],meta["rate"])
        else:
            waveform, sample_rate = load(str(audio_path))'''),
        ('        if first + samples > waveform.shape[-1]:', '''        offset = 0 if "phase4" in plan else first
        if offset + samples > waveform.shape[-1]:'''),
        ('waveform[:, first:first + samples]', 'waveform[:, offset:offset + samples]'),
        ("return core.select_scene(plan, clip_index)",
         "scene = core.select_scene(plan, clip_index)\n    if 'phase4' in plan:\n        scene['phase4'] = plan['phase4']\n    return scene"),
        ('    window = scene["scene"]', '''    if "phase4" in scene:
        meta = scene["phase4"]
        w = meta["window"]
        if fps != meta["fps"]:
            raise ValueError("Scene FPS differs from master timeline")
        return dict(start=w["start"]/fps, planned_seconds=w["count"]/fps, fps=fps,
                    render_frames=w["generated"], output_frames=w["count"], output_seconds=w["count"]/fps,
                    trimmed_seconds=w["trailing"]/fps, motion_sync_verified=False)
    window = scene["scene"]'''),
        ('        offset = 0 if "phase4" in plan else first', '''        if "phase4" in plan:
            from .phase4.timeline import trim
            meta = plan["phase4"]
            w = meta["window"]
            if sample_rate != meta["rate"]:
                raise ValueError("Soundtrack sample rate changed")
            first, samples = w["audio_start"], w["audio_end"] - w["audio_start"]
            if "asmo_review" in render_context:
                if len(images) != count or render_context["asmo_review"]["decision"] != "accept":
                    raise ValueError("Invalid accepted scene")
            else:
                images = trim(images, w)
        offset = 0 if "phase4" in plan else first''')],
    "ComfyUI_AudioAnalyze_RenderBridge/asmo_loop.py": [
        ("receipt=module.verify_prompt_audit(prepared, scene)", """audit_scene = scene
        if 'phase4' in plan:
            from .phase4.timeline import conditioning_scene
            audit_scene = conditioning_scene(scene, plan['phase4'], module.scene_cues(scene))
        receipt=module.verify_prompt_audit(prepared, audit_scene)"""),
        ("(1800 if experiment_retry_uncertain else 900)", "(14400 if 'phase4' in plan else (1800 if experiment_retry_uncertain else 900))"),
        ("model='ltxv-2b-0.9.6-distilled',**state", "model=plan.get('phase4', {}).get('model', 'ltxv-2b-0.9.6-distilled'),**state")],
    "ComfyUI_AudioAnalyze_RenderBridge/pipeline_worker.py": [
        ("            taps = learning.scene_cues(scene)", """            if phase:
                from phase4.timeline import conditioning_scene
                scene = conditioning_scene(scene, phase, learning.scene_cues(scene))
            taps = learning.scene_cues(scene)"""),
        ("        if action == 'asmo_record':", """        phase = plan.get('phase4')
        if phase:
            state_root = Path(phase['root']) / 'learning'
        if action == 'asmo_record':"""),
        ("        payload=client._chat_payload",'''        if phase:
            if phase['history']:
                user += "\\nContinue from the current seed and previous accepted movement. Historical observations may be uncertain: " + json.dumps(phase['history'][-2:])[:6000]
                images.append(encode_image_base64(phase['identity']))
                user += "\\nThe last image is the original identity reference. The starting pose comes from the current scene seed."
            user += "\\nMaster output frame interval: " + str((phase['window']['start'], phase['window']['end']))
        payload=client._chat_payload''')]
}


def install(custom):
    edits = {}
    for relative, pairs in HOOKS.items():
        path = custom/relative
        value = path.read_bytes().decode("utf-8")
        newline = "\r\n" if "\r\n" in value else "\n"
        value = value.replace("\r\n","\n")
        for old,new in pairs:
            if new in value:
                continue
            if value.count(old) != 1:
                raise ValueError(f"Unexpected installed version of {relative}: {old}")
            value = value.replace(old,new)
        compile(value,str(path),"exec")
        edits[path] = value.replace("\n",newline).encode()
    package = custom/"ComfyUI_AudioAnalyze_RenderBridge"/"phase4"
    package.mkdir(exist_ok=True)
    for name in ("timeline.py","storage.py","continuation.py","native_recipe.json"):
        edits[package/name] = (HERE/name).read_bytes()
    backup = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    for path,data in edits.items():
        if path.exists():
            if path.read_bytes() == data:
                continue
            shutil.copy2(path,path.with_name(path.name+"."+backup+".bak"))
        tmp = path.with_name(path.name+"."+backup+".tmp")
        tmp.write_bytes(data)
        os.replace(tmp,path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("custom_nodes",type=Path)
    install(parser.parse_args().custom_nodes)
