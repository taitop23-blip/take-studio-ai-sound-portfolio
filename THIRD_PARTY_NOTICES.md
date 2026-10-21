# Take Studio RC · Third-party components

This local evaluation package preserves third-party code, model metadata, and installed Python distribution notices. It does not grant rights beyond the upstream licenses. The user's recordings and generated validation audio are excluded from the distribution.

| Component | Source | Notice / terms |
|---|---|---|
| Higgs TTS 3 weights | https://huggingface.co/bosonai/higgs-tts-3-4b | Boson research and non-commercial license. Product/service embedding requires a separate commercial license. See the pinned `app/models/higgs-tts-3/LICENSE`. |
| Windows Transformers implementation | https://huggingface.co/multimodalart/higgs-audio-v3-tts-4b-transformers | Commit in `app/models/manifest.json`; preserves upstream model license. |
| Higgs audio tokenizer | https://huggingface.co/bosonai/higgs-audio-v2-tokenizer | `app/models/higgs-tokenizer/LICENSE` |
| VoxCPM2 weights and inference | https://huggingface.co/openbmb/VoxCPM2 and https://github.com/OpenBMB/VoxCPM | Apache-2.0. Pinned revision in `app/models/manifest.json`; license in `licenses/VoxCPM-Apache-2.0.txt`. |
| Four original synthetic voice presets | Generated locally with the pinned VoxCPM2 Voice Design model | `app/models/voice-presets/manifest.json` records prompts, text, seeds and SHA-256. No external person's recording is bundled. Preset audio is provided with the app under the model's Apache-2.0 terms. |
| Seed-VC | https://github.com/Plachtaa/seed-vc | GPL-3.0. Corresponding vendor source and LICENSE included under `app/vendor/seed-vc`. Local integration and output patch included. |
| Seed-VC pretrained dependencies | https://huggingface.co/Plachta/Seed-VC | Pinned revisions and hashes in `app/models/seed-vc/model_manifest.json`; downloaded repository notices retained alongside assets. Includes ASTRAL, HuBERT, Whisper-small, CAMPPlus and BigVGAN. |
| Qwen2-Audio 7B | https://huggingface.co/Qwen/Qwen2-Audio-7B-Instruct | Apache-2.0; model card retained. |
| Qwen2.5 7B | https://huggingface.co/Qwen/Qwen2.5-7B-Instruct | Apache-2.0; model LICENSE retained. |
| Whisper large-v3-turbo conversion | https://huggingface.co/dropbox-dash/faster-whisper-large-v3-turbo | MIT / OpenAI Whisper; model source revision in ready.json. |
| CPython | https://www.python.org/ | Python license in each runtime root. |
| PyTorch and installed packages | https://pytorch.org/ | Original notices in each runtime's `Lib/site-packages`; package/version inventory included. |
| FFmpeg via imageio-ffmpeg | https://github.com/imageio/imageio-ffmpeg | Binary and notices retained in the installed distribution. Check its bundled build/license terms for external redistribution. |
| .NET Windows Desktop runtime | https://github.com/dotnet/windowsdesktop | Self-contained runtime; runtime and third-party notices supplied. |
| Microsoft WebView2 | https://developer.microsoft.com/microsoft-edge/webview2/ | WebView2 SDK and Microsoft-signed Evergreen offline installer. Microsoft terms apply. |

The application icon and interface styling were authored for this app using the existing waveform brand. Civitai UI/UX Design Generator metadata was reviewed, but its LoRA weights were not available to this build. No generated design is attributed to that model.

## Reproducibility

Python application source is in `app`. Native shell, packaging scripts and tests are in `source`. Model revisions are pinned; optional online package upgrades are not performed at launch. A file inventory with SHA-256 accompanies the completed archive.

The RC is not presented as cleared for unrestricted commercial redistribution. In particular, bundled model weights, the GPL components, FFmpeg build terms and Microsoft's redistributable terms must be accounted for before a public release.
