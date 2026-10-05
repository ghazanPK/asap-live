# Requirements and provenance — Real-Time Live! variant

## Paper-supported facts

Only the Real-Time Live! abstract and public metadata were available locally. They state that ASAP understands movie-script text and automatically generates virtual-human co-speech gesture, facial expression, and body movement; dialogue drives a text-to-gesture model, parentheticals provide emotional cues, and action paragraphs yield subject/target/action entities combined into animation sequences. The later journal article was read only for shared-architecture context.

## Public implementation requirements

This project parses FDX or structured text, maps text to a user-authored motion library, creates speech/gaze/gesture, parenthetical-emotion, and actor/movement/object-interaction events, and renders continuous auto-playing SVG animation with an inspectable JSON schedule.

## Explicit assumptions and substitutions

The parser, TF-IDF mapping, entity patterns, emotion dictionary, durations, prop anchors, SVG renderer, and timeline format are public-implementation assumptions. They are not claimed as details of the one-page live paper. This does not reproduce the original text-to-gesture model, its 2D-video/3D-mocap training data, Unity renderer, facial rig, TTS, or assets.

## Interactive implementation

The local demo compiles the actual parser/resolver output into a Three.js stage with bundled fictional CC0 avatars. It supports text/FDX upload, editable character/prop/action catalogs, timeline scrubbing, dialogue playback, PNG storyboard capture and timeline/storyboard export. Recompilation resets the stage. The lexical example requires no weights; semantic mode uses independently configurable local gesture/action encoders. The small official BEAT sample and fitted retrieval artifacts stay in ignored local outputs; pinned renderer modules are downloaded into ignored vendor storage. The journal's GestureCLR pose-matching lineage is documented as a research dependency; the browser uses locally prepared BEAT body-motion clips for dialogue while keeping authored action poses; it does not claim to reproduce institute motion capture or GestureCLR weights. Early ASAP variants expose a subset of this component implementation and do not claim the later journal evaluation. Optional Kokoro and faster-whisper adapters replace browser speech/typed input; mouth motion is an approximate envelope, not aligned visemes.

## Bundled fictional avatar substitution

Two newly generated fictional CC0 humanoids replace the original avatar assets in the browser demo. They provide a 53-bone rig and named ARKit/viseme targets. Motion retargeting adapts source joints to their bind pose; speaking envelopes approximate mouth motion rather than phoneme alignment. The optional recorded BEAT companion inspects public motion, face and audio files prepared locally, independently of the paper's learned algorithm. No dataset recordings or trained weights are bundled.

## Local recorded co-speech integration

The browser application retrieves prepared BEAT body-motion clips with `automatic` mode: a current public-demo adapter; the one-page live paper does not identify this dependency. The first `python scripts/start_demo.py` run fetches a small official BVH/TextGrid sample, constructs a nine-clip bank, and fits the local retrieval artifact under ignored `outputs/beat-library/`. Install `scripts/requirements-demo.txt` first. Preparation code and method dependencies are vendored in this repository; no sibling clone, original institute library, full dataset, or pretrained weights are bundled. The screenplay parser, action resolver, live scene playback, and capture remain this application's core. The separate recorded-motion companion remains available for local motion/face/audio inspection.
