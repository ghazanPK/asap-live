# ASAP: Auto-generating Storyboard and Previz

**Hanseob Kim, Ghazanfar Ali, Bin Han, Hwangyoun Kim, Jieun Kim, Jae-In Hwang**

**SIGGRAPH Asia Real-Time Live! · 2022** · Published

[Paper / publisher](https://doi.org/10.1145/3550453.3570124) · [Project page](https://ghazanfarali.com/research/asap-live/) · [Video presentation](https://www.youtube.com/watch?v=omdEg7Ro_bU) · [BibTeX](citation.bib) · [Requirements](REQUIREMENTS.md) · [Code & setup](#implementation-and-usage)

> A live demonstration of screenplay-driven virtual actors.

![Scientific method schematic for asap-live](paper-assets/method.svg)

*Graphical abstract diagram. Screenplay structure drives coordinated virtual-actor behavior and previsualization.*

## Why this research

A live workflow demonstrates how screenplay text can become visible actor behavior. This presentation shows the ASAP system coordinating dialogue, emotion and physical action during previsualization.

The SIGGRAPH Asia Real-Time Live! presentation shows ASAP turning screenplay text into virtual-actor scenes. Dialogue drives co-speech gesture, parentheticals supply emotional cues, and action paragraphs specify physical movements. The video is the live demonstration of this system.

## Method at a glance

**Movie script** → **Gesture + expression + action** → **Live virtual-actor scene**

| | Research system |
|---|---|
| Input | Movie-script dialogue, parentheticals, and action paragraphs |
| Method | Script understanding and composition of animation modules |
| Output | Virtual-actor scenes, gestures, facial expression, and body movements |

## Evidence and scope

Real-Time Live! demonstration; no journal benchmark is attributed to this item

**Attribution:** These findings describe the paper or manuscript, not results obtained with this repository's code.

**Study context:** Demonstration scenarios.

**Limitations:** This demonstration and its one-page publication are distinct from the ISMAR and journal papers.

## Explore the implementation

A standalone autoplay previsualization demo. It uses disclosed shared-architecture choices from the journal and does not recreate the original live performance or Unity assets.

This repository contains independently written research code. The institute's original source, datasets and trained models are not distributed. Public-data preparation, commands, assumptions and checks are documented below and in [REQUIREMENTS.md](REQUIREMENTS.md).

## Resources and citation

Read the paper through its [publisher record](https://doi.org/10.1145/3550453.3570124). PDFs are hosted by publishers or preprint archives rather than stored in this repository.

Watch the [existing YouTube presentation](https://www.youtube.com/watch?v=omdEg7Ro_bU).

Please cite the research paper when using its ideas; [download the BibTeX citation](citation.bib). The implementation has its own documented scope.

## Implementation and usage

<!-- implementation-guide -->

This standalone, asset-free demonstrator compiles a screenplay into an auto-playing browser scene. Dialogue triggers estimated speech timing, gaze, and a catalog gesture; parentheticals trigger emotion; action paragraphs create movement toward a configured prop anchor followed by an interaction.

**Citation.** Hanseob Kim, Ghazanfar Ali, Bin Han, Hwangyoun Kim, Jieun Kim, and Jae-In Hwang. “ASAP: Auto-generating Storyboard and Previz.” *SIGGRAPH Asia Real-Time Live!* (2022), pp. 1–1. [https://doi.org/10.1145/3550453.3570124](https://doi.org/10.1145/3550453.3570124). Status: published live demonstration.

Only the abstract and public metadata were available locally for this variant. See [REQUIREMENTS.md](REQUIREMENTS.md) for the evidence boundary. No institute code, datasets, models, weights, mocap, character assets, or Unity project are included.

### Interactive quickstart

From this repository root, install the package, prepare the local viewer, and launch the browser demo:

```powershell
python -m pip install -e .
python scripts/prepare_viewer.py
python scripts/demo.py --port 8010
```

Open http://127.0.0.1:8010. The authored example compiles on load; edit the screenplay or import an FDX file, then play or scrub the timeline.

### Verify the included example

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e .
python scripts/verify.py
start outputs/verify/live.html
```

The default backend is a deterministic TF-IDF cosine baseline. To use a cached sentence-transformer, install `python -m pip install -e ".[semantic]"` and add `"resolver": {"backend": "sentence-transformer", "model": "path-or-cached-model-name"}` to the library. `local_files_only=True` prevents downloads.

### Input schemas

Structured text uses one `LABEL: text` record per line. Supported labels are `SCENE`, `ACTION`, `CHARACTER`, `DIALOGUE`, and `PARENTHETICAL`. FDX input reads `Paragraph Type` plus nested `Text` elements. The library JSON contains `stage`, keyed `characters`, keyed `props` with interaction anchors, and `motions` whose entries include `id`, `kind`, and example `phrases`.

`timeline.json` is the canonical output. `live.html` embeds its JSON, CSS, SVG, and JavaScript, and opens without a server. It is a schematic playback demo, not the paper's Unity rendering or trained text-to-gesture system.

### Public data and model setup

The included screenplay and motion library are authored artificial fixtures, not paper data. Use screenplays you own or public-domain scripts and motion descriptions you can redistribute. Keep user downloads under ignored asset/data/model directories.

To swap in real inputs, keep the same labels in the screenplay (or use an `.fdx` file) and the same keys in `library.json`, then run `asap-live path/to/screenplay.fdx --library path/to/library.json --out outputs/my-run`. The verify script and CLI call the same parser, compiler, and renderer.

See [REQUIREMENTS.md](REQUIREMENTS.md) for paper facts, implementation assumptions, and scope limits.

## Run the interactive 3D demo

From this repository root, with Python 3.10+:

```bash
python scripts/prepare_viewer.py
python scripts/demo.py --port 8010
```

Open http://127.0.0.1:8010. Edit the screenplay or import FDX, compile the scene, play/scrub its actual event schedule, inspect resolved actions/gestures and capture rendered storyboard frames. Characters and the starter motion catalog are independently authored procedural examples. The browser renderer replaces the institute’s Unity/assets; it does not reproduce its motion library.

The default lexical resolver runs without model downloads. For the paper’s semantic retrieval component, install `pip install -e ".[semantic]"`, obtain local Sentence-BERT model directories and select semantic mode: `all-mpnet-base-v2` for gesture phrases and `multi-qa-mpnet-base-dot-v1` for actions. The scene catalog remains JSON: replace `characters`, `props` and `motions` to extend the demonstration. No dataset or model weights are included.

The journal demo exposes camera inspection, JSON schedule export and storyboard export. The ISMAR variant centers on scene playback and frame capture; the Live variant starts continuous playback after compilation. Neither earlier variant claims the journal’s full VR/360 outputs.

## Components and related implementations

The ASAP papers share screenplay parsing, action selection and coordinated speech/body/face behavior. The journal paper explicitly describes GestureCLR for 2D/3D gesture matching; see [Wild Pose Matching](https://github.com/ghazanPK/wild-pose-matching) and [Multilingual Gestures](https://github.com/ghazanPK/multilingual-gesture) for that component’s implementations. [Automatic Text-to-Gesture](https://github.com/ghazanPK/automatic-text-to-gesture) documents the earlier rule-mining approach. These research links identify component lineage; this standalone demo uses an explicit user-authored motion catalog and does not silently load a sibling repository.

Related system variants: [ASAP journal](https://github.com/ghazanPK/asap-journal), [ASAP ISMAR](https://github.com/ghazanPK/asap-ismar), [ASAP Live](https://github.com/ghazanPK/asap-live).

## Optional local speech

Browser speech works immediately when enabled. For Kokoro, install `pip install -e ".[speech]"`, prepare local `config.json`, `kokoro-v1_0.pth` and `voices/af_heart.pt` from https://huggingface.co/hexgrad/Kokoro-82M, and set `KOKORO_MODEL_DIR` to that folder before starting the server. Prepare the English phonemizer dependencies described at https://github.com/hexgrad/kokoro (including espeak-ng where required). Choose Local Kokoro in the demo. Weights remain outside Git.

The replaceable speech adapter also supports CPU-INT8 faster-whisper with `WHISPER_MODEL_DIR` pointing to a locally obtained converted small model directory containing `model.bin`; `/api/asr` accepts raw audio and returns transcription plus word timestamps. The screenplay application primarily takes text/FDX. Speech adapters are engineering substitutions, not the papers’ original services.

<!-- avatar-recorded-motion:start -->
## Bundled characters and recorded public motion

The browser demos include Rowan and Mira, two new fictional GLB characters built with MPFB and MakeHuman community assets under CC0 1.0. See [avatar licensing and provenance](static/avatars/LICENSE.md). Use the character selector in the stage. The shared renderer supports body bones, ARKit facial channels, and approximate speaking motion.

The [recorded BEAT motion companion](static/recorded-motion.html) opens at `/recorded-motion.html` while the demo server is running. It plays locally selected motion, face, and WAV files on the bundled characters; this is recorded public-data inspection, separate from the paper implementation. No BEAT recording, dataset archive, or trained model is bundled. Install the one preparation dependency and fetch a small official sample into ignored `outputs/beat-demo/`:

```sh
python -m pip install numpy
python scripts/beat_demo/fetch_modalities.py --speaker 1 --sequence 1_wayne_0_1_1 --include-bvh --max-bytes 25000000 --output-dir outputs/beat-demo/source
python scripts/beat_demo/prepare_bvh.py --bvh outputs/beat-demo/source/1_wayne_0_1_1.bvh --output outputs/beat-demo/sample/1_wayne_0_1_1-raw-motion.json --frames 120
python scripts/beat_demo/prepare_modalities.py --sequence 1_wayne_0_1_1 --source outputs/beat-demo/source --output outputs/beat-demo/sample --frames 120
```

Open the companion and select `outputs/beat-demo/sample/1_wayne_0_1_1-raw-motion.json`, `1_wayne_0_1_1-face.json`, and `1_wayne_0_1_1.wav`. The downloader caps each original file at 25 MB; the prepared clip contains up to 120 frames. The viewer uses local files and does not upload them. For other BEAT takes, substitute a matching official speaker and sequence ID.
<!-- avatar-recorded-motion:end -->
