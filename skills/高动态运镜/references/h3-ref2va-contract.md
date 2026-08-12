# H3 Ref2VA contract

## Contents

1. Exact section order
2. Reference roles
3. Task-type selection
4. Retention markers
5. Timeline and shot rules
6. Sound rules
7. Flexible high-motion defaults
8. Preflight checklist

## 1. Exact section order

Write all prompt sections in English. Preserve another language only for dialogue, lyrics, and visible scene text. Use these six fields in this exact order and do not rename them:

```text
subject_definitions:
...

summary:
...

retention_analysis:
...

detailed_description:
...

overall_soundscape:
...

non_diegetic_music:
...
```

For a generation task, make `detailed_description` explicit enough to establish composition, visible identity, environment, lighting, action/state changes, camera movement, synchronized physical sound, and the points where references apply. The H3 reference guide normally recommends 350-500 English words, but temporal feasibility takes priority: do not invent extra actions merely to reach a word count.

## 2. Reference roles

- `<Subject N>`: reusable visible content such as a person, creature, object, outfit, prop, environment, effect, pose, or visual style.
- `<Picture N>`: a concrete first frame, last frame, keyframe, edited keyframe, composition anchor, or storyboard/planning anchor.
- `<Video N>`: a source video being edited or continued, or a whole-video temporal/camera structure reference.
- `<Audio N>`: an audio signal copied or referenced for voice, music, rhythm, ambience, dialogue, lyrics, or effects.

Keep each label's meaning identical across all six sections. If an image only defines a character or style, cite it inside the relevant `<Subject N>` definition and do not create a standalone `<Picture N>` line. If an image is the concrete opening frame, define it as `<Picture N>` and mention that the shot begins from it.

For dual-image mode, use `<Picture 1>` as the standalone opening-frame anchor and `<Picture 2>` as the standalone character-design reference. Use `[keyframe completion + reference generation]` and give all three defined labels exactly one retention line.

## 3. Task-type selection

Start `summary` with the applicable task types inside one pair of square brackets:

- `keyframe completion`: an image is a concrete first, last, or intermediate frame anchor.
- `reference generation`: a reference guides character, scene, style, action, camera, storyboard, or sound without being a concrete keyframe or an edited/continued source video.
- `video editing`: directly modify a source video.
- `video continuation`: extend or resume a source video.
- `audio reuse`: copy the same audio signal in full or in part.
- `audio reference`: follow audio traits without copying the signal.

Combine applicable values with ` + ` and do not repeat them. A first-frame image plus a separate design board normally requires `[keyframe completion + reference generation]`.

## 4. Retention markers

Use only these fixed markers for visible references:

- `fully_preserved`
- `partially_preserved`
- `attribute_transfer`
- `weak_reference`

Use only these for audio references:

- `fully_copy`
- `partially_copy`
- `reference`
- `weak_reference`

Give every defined label exactly one retention line. Do not count new actions, backgrounds, or plot events as losses of reference fidelity.

## 5. Timeline and shot rules

- `[Shot 1]` opens the timeline and has no `At` cut timestamp.
- Later shots use `[Shot N] At MM:SS.mmm, ...` with strictly increasing times inside the requested duration.
- Internal phases may use `At 00:01.500`, `From 00:01.500 to 00:03.800`, or equivalent natural English.
- For a first-frame anchor, explicitly say `the shot begins from <Picture 1>` or an equivalent unambiguous phrase.
- Write camera movement naturally. Name a motion type and add amplitude/speed only when meaningful: tracking shot, arc shot, push in, pull out, pan, truck, tilt, pedestal, roll, static shot, or controlled shake.
- Give actual speakers stable `(S1)`, `(S2)` identifiers. Put dialogue/lyrics in `<d>[Language] ...</d>`. Characters who never vocalize receive no speaker ID.
- Use `<scenetrans>` only for speech crossing a cut and `<cutoff>` only for speech truncated by the video ending.

## 6. Sound rules

- `detailed_description`: synchronized dialogue, vocals, and shot-specific sound events.
- `overall_soundscape`: continuous ambience, physical action sounds, and non-verbal human sounds. Do not repeat dialogue or music here.
- `non_diegetic_music`: audience-only score. State instrumentation, tempo, rhythm, and dynamic development. Use `N/A` when absent.

## 7. Flexible high-motion defaults

Choose timing from the requested duration and the selected motion path:

- About 5 seconds: 3 connected beats—immediate motion onset, compound traversal/redirection, and a decisive exit or impact payoff.
- 6-8 seconds: 3-4 connected beats with room for one additional spatial reversal, obstacle, or scale change.
- About 10 seconds: 4-5 connected beats, preferably with one speed contrast and one major environmental transition.

No action type is mandatory. Launches, aerial tricks, landings, and drifts are valid modules, not a required sequence. A shot may instead use weaving, overtaking, descending pursuit, rail transfer, wall riding, ricochet, gate threading, close passing, vertical climbing, or another coherent high-speed path.

The supplied hoverboard sample represents one `ground skim → launch → air trick → landing drift` preset. Use its exact 00:02.500/00:05.500 boundaries and 180-degree orbit only when the user explicitly asks for sample matching.

## 8. Preflight checklist

- Six fields exist once and remain in exact order.
- All labels are defined before use and retain one meaning.
- The summary task type matches actual reference roles.
- A standalone first-frame picture triggers `keyframe completion`.
- Every reference label has exactly one valid retention entry.
- Shot times fit the requested duration and increase strictly.
- Shot 1 has no cut timestamp; later shots do.
- Physical action, camera movement, and secondary motion are causally compatible.
- High-motion prompts include at least two sequential official camera-command groups, explicit fast/large motion language, two-axis subject displacement, foreground parallax, obstacle/contact interaction, substantial perspective/scale change, and visible physical reaction.
- Each batch case uses a coherent but meaningfully different action progression and camera path.
- `overall_soundscape` and `non_diegetic_music` do not duplicate dialogue or each other.
- The ending is achievable from the opening state within the duration.
- Apply sample-specific launch/orbit/landing/drift checks only when sample matching was explicitly requested.
