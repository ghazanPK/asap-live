# Requirements and provenance — Real-Time Live! variant

## Paper-supported facts

Only the Real-Time Live! abstract and public metadata were available locally. They state that ASAP understands movie-script text and automatically generates virtual-human co-speech gesture, facial expression, and body movement; dialogue drives a text-to-gesture model, parentheticals provide emotional cues, and action paragraphs yield subject/target/action entities combined into animation sequences. The later journal article was read only for shared-architecture context.

## Public implementation requirements

This project parses FDX or structured text, maps text to a user-authored motion library, creates speech/gaze/gesture, parenthetical-emotion, and actor/movement/object-interaction events, and renders continuous auto-playing SVG animation with an inspectable JSON schedule.

## Explicit assumptions and substitutions

The parser, TF-IDF mapping, entity patterns, emotion dictionary, durations, prop anchors, SVG renderer, and timeline format are public-implementation assumptions. They are not claimed as details of the one-page live paper. This does not reproduce the original text-to-gesture model, its 2D-video/3D-mocap training data, Unity renderer, facial rig, TTS, or assets.

## Interactive implementation

The local demo compiles the actual parser/resolver output into an original procedural Three.js stage. It supports text/FDX upload, editable character/prop/action catalogs, timeline scrubbing, dialogue playback, PNG storyboard capture and timeline/storyboard export. Recompilation resets the stage. The lexical example requires no weights; semantic mode uses independently configurable local gesture/action encoders. Model files, motion libraries and vendor downloads remain outside Git. The journal's GestureCLR pose-matching lineage is documented as a research dependency; this compact renderer uses authored poses rather than claiming recovered motion capture. Early ASAP variants expose a subset of this component implementation and do not claim the later journal evaluation. Optional Kokoro and faster-whisper adapters replace browser speech/typed input; mouth motion is an approximate envelope, not aligned visemes.
