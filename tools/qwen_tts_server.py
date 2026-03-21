"""
Qwen TTS Proxy Server
Lightweight proxy to Gradio 6.x demo instances (CustomVoice + VoiceDesign).
No torch/soundfile needed — just forwards requests to running qwen-tts-demo.

Gradio 6.x API:
  - /gradio_api/call/{endpoint}  (POST → event_id)
  - /gradio_api/call/{endpoint}/{event_id}  (GET SSE → data)

Usage:
  pip install fastapi uvicorn httpx
  python qwen_tts_server.py --port 8100 --custom-url http://localhost:8000 --design-url http://localhost:8001
"""

import json
import logging
import argparse
from pathlib import Path

from fastapi import FastAPI, HTTPException, Form
from fastapi.responses import Response, JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import httpx
import uvicorn

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("qwen-tts-proxy")

app = FastAPI(title="Qwen TTS Proxy")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

VOICES_DIR = Path(__file__).parent / "voices"
VOICES_DIR.mkdir(exist_ok=True)

CUSTOM_URL = "http://localhost:8000"
DESIGN_URL = "http://localhost:8001"

client = httpx.AsyncClient(timeout=httpx.Timeout(connect=10.0, read=600.0, write=10.0, pool=10.0))


async def gradio_call(base_url: str, endpoint: str, data: list) -> bytes:
    """Call Gradio 6.x API: POST to start, GET SSE stream for result, fetch audio file."""

    # Step 1: POST to start the call
    call_url = f"{base_url}/gradio_api/call/{endpoint}"
    log.info(f"Gradio POST: {call_url} data={[str(d)[:60] for d in data]}")
    resp = await client.post(call_url, json={"data": data})

    if resp.status_code != 200:
        log.error(f"Gradio call error {resp.status_code}: {resp.text[:500]}")
        raise HTTPException(resp.status_code, f"Gradio call error: {resp.text[:300]}")

    event_id = resp.json().get("event_id")
    if not event_id:
        raise HTTPException(500, f"No event_id in response: {resp.text[:200]}")

    log.info(f"Gradio event_id: {event_id}")

    # Step 2: GET SSE stream for result
    stream_url = f"{base_url}/gradio_api/call/{endpoint}/{event_id}"
    log.info(f"Gradio GET SSE: {stream_url}")

    audio_info = None
    async with client.stream("GET", stream_url) as stream:
        event_type = None
        async for line in stream.aiter_lines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("event:"):
                event_type = line[6:].strip()
            elif line.startswith("data:"):
                data_str = line[5:].strip()
                if event_type == "complete":
                    try:
                        parsed = json.loads(data_str)
                        data_out = parsed if isinstance(parsed, list) else parsed.get("data", parsed)
                        if isinstance(data_out, list) and len(data_out) > 0:
                            audio_info = data_out[0]
                    except json.JSONDecodeError:
                        log.warning(f"Failed to parse SSE data: {data_str[:200]}")
                elif event_type == "error":
                    raise HTTPException(500, f"Gradio error: {data_str[:300]}")

    if audio_info is None:
        raise HTTPException(500, "No audio data in Gradio SSE response")

    # Step 3: Extract file URL and fetch audio bytes
    if isinstance(audio_info, dict):
        file_url = audio_info.get("url") or audio_info.get("path", "")
    elif isinstance(audio_info, str):
        file_url = audio_info
    else:
        raise HTTPException(500, f"Unexpected audio format: {type(audio_info)}: {audio_info}")

    if not file_url:
        raise HTTPException(500, f"No audio URL in response: {audio_info}")

    # Make URL absolute
    if file_url.startswith("/"):
        file_url = f"{base_url}{file_url}"
    elif not file_url.startswith("http"):
        file_url = f"{base_url}/gradio_api/file={file_url}"

    log.info(f"Fetching audio: {file_url}")
    audio_resp = await client.get(file_url)
    if audio_resp.status_code != 200:
        raise HTTPException(500, f"Failed to fetch audio file: {audio_resp.status_code}")

    log.info(f"Audio fetched: {len(audio_resp.content)} bytes")
    return audio_resp.content


# --- Health & discovery ---

@app.get("/", response_class=HTMLResponse)
async def root():
    """Health check page."""
    custom_ok = False
    design_ok = False
    try:
        r = await client.get(f"{CUSTOM_URL}/gradio_api/info", timeout=3)
        custom_ok = r.status_code == 200
    except:
        pass
    try:
        r = await client.get(f"{DESIGN_URL}/gradio_api/info", timeout=3)
        design_ok = r.status_code == 200
    except:
        pass

    c_status = "🟢 online" if custom_ok else "🔴 offline"
    d_status = "🟢 online" if design_ok else "🔴 offline"

    return f"""<!DOCTYPE html><html><head><title>Qwen TTS Proxy</title>
    <style>body{{font-family:system-ui;background:#1a1b26;color:#c0caf5;padding:40px}}
    h1{{color:#7aa2f7}}table{{border-collapse:collapse;margin:20px 0}}
    td,th{{padding:8px 16px;border:1px solid #3b4261;text-align:left}}</style></head>
    <body><h1>Qwen TTS Proxy</h1>
    <table><tr><th>Backend</th><th>URL</th><th>Status</th></tr>
    <tr><td>CustomVoice</td><td>{CUSTOM_URL}</td><td>{c_status}</td></tr>
    <tr><td>VoiceDesign</td><td>{DESIGN_URL}</td><td>{d_status}</td></tr></table>
    <h3>Endpoints</h3><ul>
    <li><code>POST /tts/custom</code> — speaker + instruction</li>
    <li><code>POST /tts/design</code> — voice from description</li>
    <li><code>POST /tts/design/save</code> — generate + save voice</li>
    <li><code>POST /tts/clone</code> — reuse saved voice</li>
    <li><code>GET /tts/speakers</code> — list speakers</li>
    <li><code>GET /tts/voices</code> — list saved voices</li>
    </ul></body></html>"""


@app.get("/health")
async def health():
    custom_ok = design_ok = False
    try:
        r = await client.get(f"{CUSTOM_URL}/gradio_api/info", timeout=3)
        custom_ok = r.status_code == 200
    except:
        pass
    try:
        r = await client.get(f"{DESIGN_URL}/gradio_api/info", timeout=3)
        design_ok = r.status_code == 200
    except:
        pass
    return {
        "status": "ok",
        "backends": {
            "custom": {"url": CUSTOM_URL, "available": custom_ok},
            "design": {"url": DESIGN_URL, "available": design_ok},
        }
    }


@app.get("/tts/speakers")
def get_speakers():
    return {
        "speakers": [
            "Vivian", "Serena", "Ryan", "Aiden", "Eric",
            "Dylan", "Ono Anna", "Sohee", "Uncle Fu"
        ]
    }


# --- CustomVoice ---

@app.post("/tts/custom")
async def tts_custom(
    text: str = Form(...),
    speaker: str = Form("Vivian"),
    language: str = Form("Auto"),
    instruct: str = Form(""),
):
    """CustomVoice: run_instruct(text, lang, speaker, instruct) -> audio"""
    try:
        audio = await gradio_call(
            CUSTOM_URL, "run_instruct",
            data=[text, language, speaker, instruct or ""]
        )
        return Response(content=audio, media_type="audio/wav")
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"CustomVoice error: {e}")
        raise HTTPException(500, str(e))


# --- VoiceDesign ---

@app.post("/tts/design")
async def tts_design(
    text: str = Form(...),
    design: str = Form("A natural, clear voice with warm tone."),
    language: str = Form("Auto"),
):
    """VoiceDesign: run_voice_design(text, lang, design) -> audio"""
    try:
        audio = await gradio_call(
            DESIGN_URL, "run_voice_design",
            data=[text, language, design]
        )
        return Response(content=audio, media_type="audio/wav")
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"VoiceDesign error: {e}")
        raise HTTPException(500, str(e))


# --- Save designed voice ---

@app.post("/tts/design/save")
async def tts_design_save(
    text: str = Form(...),
    design: str = Form(...),
    language: str = Form("Auto"),
    voice_name: str = Form(...),
):
    """Generate with VoiceDesign and save audio + metadata."""
    try:
        audio = await gradio_call(
            DESIGN_URL, "run_voice_design",
            data=[text, language, design]
        )

        voice_dir = VOICES_DIR / voice_name
        voice_dir.mkdir(exist_ok=True)
        (voice_dir / "reference.wav").write_bytes(audio)

        meta = {
            "name": voice_name,
            "design": design,
            "language": language,
            "sample_text": text,
        }
        (voice_dir / "meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        log.info(f"Saved voice '{voice_name}' to {voice_dir}")
        return JSONResponse({
            "status": "saved",
            "voice_name": voice_name,
            "path": str(voice_dir / "reference.wav"),
            "audio_size": len(audio),
        })
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"VoiceDesign save error: {e}")
        raise HTTPException(500, str(e))


# --- Clone: re-use saved voice ---

@app.post("/tts/clone")
async def tts_clone(
    text: str = Form(...),
    language: str = Form("Auto"),
    voice_name: str = Form(None),
):
    """Re-generate using saved voice's design description."""
    if not voice_name:
        raise HTTPException(400, "Provide voice_name")

    meta_path = VOICES_DIR / voice_name / "meta.json"
    if not meta_path.exists():
        raise HTTPException(404, f"Voice '{voice_name}' not found")

    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        design = meta.get("design", "A natural, clear voice.")

        audio = await gradio_call(
            DESIGN_URL, "run_voice_design",
            data=[text, language, design]
        )
        return Response(content=audio, media_type="audio/wav")
    except HTTPException:
        raise
    except Exception as e:
        log.error(f"VoiceClone error: {e}")
        raise HTTPException(500, str(e))


# --- Voice management ---

@app.get("/tts/voices")
def list_voices():
    voices = []
    if VOICES_DIR.exists():
        for d in sorted(VOICES_DIR.iterdir()):
            if d.is_dir() and not d.name.startswith("_"):
                meta_path = d / "meta.json"
                has_ref = (d / "reference.wav").exists()
                meta = {}
                if meta_path.exists():
                    try:
                        meta = json.loads(meta_path.read_text(encoding="utf-8"))
                    except:
                        pass
                voices.append({"name": d.name, "has_reference": has_ref, **meta})
    return {"voices": voices}


@app.delete("/tts/voices/{voice_name}")
def delete_voice(voice_name: str):
    voice_dir = VOICES_DIR / voice_name
    if not voice_dir.exists():
        raise HTTPException(404, f"Voice '{voice_name}' not found")
    import shutil
    shutil.rmtree(voice_dir)
    return {"status": "deleted", "voice_name": voice_name}


@app.post("/tts/voices/{voice_name}/preview")
async def preview_voice(voice_name: str):
    ref_path = VOICES_DIR / voice_name / "reference.wav"
    if not ref_path.exists():
        raise HTTPException(404, f"Voice '{voice_name}' has no reference audio")
    return Response(content=ref_path.read_bytes(), media_type="audio/wav")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Qwen TTS Proxy Server")
    parser.add_argument("--port", type=int, default=8100)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--custom-url", default="http://localhost:8000",
                        help="CustomVoice Gradio demo URL")
    parser.add_argument("--design-url", default="http://localhost:8001",
                        help="VoiceDesign Gradio demo URL")
    args = parser.parse_args()

    CUSTOM_URL = args.custom_url
    DESIGN_URL = args.design_url

    log.info(f"Proxy server on {args.host}:{args.port}")
    log.info(f"  CustomVoice: {CUSTOM_URL}")
    log.info(f"  VoiceDesign: {DESIGN_URL}")

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
