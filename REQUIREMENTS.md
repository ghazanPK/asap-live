# Requirements and provenance — Real-Time Live! variant

## Paper-supported facts

Only the Real-Time Live! abstract and public metadata were available locally. They state that ASAP understands movie-script text and automatically generates virtual-human co-speech gesture, facial expression, and body movement; dialogue drives a text-to-gesture model, parentheticals provide emotional cues, and action paragraphs yield subject/target/action entities combined into animation sequences. The later journal article was read only for shared-architecture context.

## Public implementation requirements

This project parses FDX or structured text, maps text to a user-authored motion library, creates speech/gaze/gesture, parenthetical-emotion, and actor/movement/object-interaction events, and renders continuous auto-playing SVG animation with an inspectable JSON schedule.

## Explicit assumptions and substitutions

The parser, TF-IDF mapping, entity patterns, emotion dictionary, durations, prop anchors, SVG renderer, and timeline format are public-implementation assumptions. They are not claimed as details of the one-page live paper. This does not reproduce the original text-to-gesture model, its 2D-video/3D-mocap training data, Unity renderer, facial rig, TTS, or assets.
