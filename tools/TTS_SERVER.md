# Qwen TTS Server

Unified server for Qwen3 TTS models. Loads CustomVoice + VoiceDesign directly, no demo needed.

## Quick Start

```
start_tts_server.cmd
```

Or manually:
```bash
python qwen_tts_server.py --port 8100 --device cuda:0 --dtype bfloat16 --preload custom design
```

`--preload` is optional. Without it models load lazily on first request.

## API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/tts/custom` | POST | CustomVoice — 9 predefined speakers + style instruction |
| `/tts/design` | POST | VoiceDesign — generate voice from text description |
| `/tts/design/save` | POST | Generate + save voice profile for reuse |
| `/tts/clone` | POST | Speak with a previously saved voice |
| `/tts/speakers` | GET | List available CustomVoice speakers |
| `/tts/voices` | GET | List saved voice profiles |
| `/tts/voices/{name}` | DELETE | Delete a saved voice |
| `/tts/voices/{name}/preview` | POST | Play reference audio of saved voice |

## Examples

**CustomVoice** (speaker + instruction):
```bash
curl -X POST http://localhost:8100/tts/custom \
  -F "text=Hello world" -F "speaker=Vivian" -F "language=English" \
  -F "instruct=Speak warmly" --output out.wav
```

**VoiceDesign** (describe the voice you want):
```bash
curl -X POST http://localhost:8100/tts/design \
  -F "text=Hello world" -F "language=Russian" \
  -F "design=Young woman, warm energetic voice, slight Russian accent" --output out.wav
```

**Save a designed voice**:
```bash
curl -X POST http://localhost:8100/tts/design/save \
  -F "text=Sample text" -F "language=Russian" \
  -F "design=Young woman, warm energetic voice" \
  -F "voice_name=WarmGirl"
```

**Use saved voice**:
```bash
curl -X POST http://localhost:8100/tts/clone \
  -F "text=New text to speak" -F "language=Russian" \
  -F "voice_name=WarmGirl" --output out.wav
```

## Models Used

- `Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice` — predefined speakers, style instructions
- `Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign` — voice generation from natural language description

Saved voices are stored in `tools/voices/{name}/` (reference.wav + meta.json).
