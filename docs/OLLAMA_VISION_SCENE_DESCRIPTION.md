# Ollama Vision Scene Description

The LTX pipeline now uses the selected seed image pixels as an input to the local Ollama `gemma3:4b` vision model before the final scene prompt is assembled.

## Responsibility boundary

Gemma's vision call acts as the eyes of the pipeline. It returns one concise natural-language paragraph describing only the observable opening frame:

- visible subject count and subject type;
- pose, orientation, and visible limbs;
- clothing and props;
- framing, camera angle, and composition;
- environment, lighting, and visual style.

The vision call does **not** return JSON as its model output. It does not invent motion, choreography, emotion, events, or backstory, and it does not write the final LTX prompt.

The surrounding run plan remains JSON so the scene description, model name, completion status, and fallback reason can be audited.

## Existing logic remains authoritative

The visual description is inserted into a `[SCENE_DESCRIPTION]` prompt block. It does not replace or override:

- audio analysis;
- beat-aligned scene timing;
- tap-accent synchronization;
- structured choreography profiles;
- subject-count locks;
- negative-prompt memory;
- final LTX prompt assembly.

The exact seed filename remains a secondary contextual hint. The seed pixels and the natural-language visual description are the primary visual evidence.

## Failure behavior

If the seed file is missing, unsupported, or Ollama fails, the pipeline records `status: fallback`, records the error, and uses a clearly labeled filename-derived fallback description. It does not claim that the pixels were analyzed.

## Ollama transport

The local client sends base64-encoded image bytes in the user message's `images` array to Ollama's `/api/chat` endpoint. The default model is `gemma3:4b` and the default server is `http://127.0.0.1:11434`.
