---
name: holographic-explainer
description: |
  Turn user-provided reference images and script into multi-segment H3 Ref2VA video prompts with character presenter, holographic interaction, and full narration coverage. Users provide a character reference image, an environment reference image, and a complete narration script. The Skill auto-splits the script into segments within user-specified max duration, calculates narration budget dynamically, designs at least 2 holographic interactions per segment, and outputs complete self-contained Ref2VA format prompts. No external skill dependencies. Style, aspect ratio, and segment duration are flexible.
trigger-words: [holographic explainer, character interactive demo, holographic presenter, 全息讲解, 角色交互演示, 全息互动讲解, 讲师视频提示词]
exported-by: StarAI
---

# Holographic Explainer (全息讲解)

Turn any user-provided script and reference images into polished multi-segment H3 video prompts featuring a character presenter, holographic UI interaction, and complete narration coverage. Each segment is an independently usable Ref2VA prompt. This Skill is fully self-contained and does not depend on any other skill.

## When to Use

- A character presenter explains a topic with holographic UI interaction
- A product tutorial, tech guide, or educational explainer needs polished short-video prompts
- A narration script needs to be split into timed segments with full coverage
- Hardware/software comparisons need holographic visualization

Do not use when:
- No character reference image is available
- The user needs non-narrated B-roll without a presenter
- The user needs only a written script without video prompts

## Required Input

The user must provide:
1. **Character reference image** (Picture 1): defines presenter identity, face, hair, glasses, wardrobe, accessories.
2. **Environment reference image** (Picture 2): defines room layout, color palette, furniture, lighting mood.
3. **Narration script**: the complete text to be spoken across all segments.

Optional input:
- **Presenter name**: the on-camera identity. Defaults to "Presenter".
- **Max segment duration**: default 15 seconds. User can specify any value.
- **Narration audio duration**: if provided, used to calculate actual speech rate.
- **Speech rate**: if user directly specifies (e.g., "4 chars/second"), skip estimation.
- **Style direction**: user expresses freely (e.g., mature, casual, professional, playful, sensual-but-professional). Affects acting only, not appearance.
- **Aspect ratio**: user sets in video generation software. Skill does not hardcode.
- **Narration language**: default Chinese.

## Reference Files

This Skill includes three self-contained reference files:

| File | Purpose |
|------|---------|
| `references/ref2va-format-guide.md` | Complete Ref2VA six-section format specification with shot rules, camera vocabulary, dialogue tags, and continuity checklist |
| `references/narration-budget-guide.md` | Speech rate estimation, word counting rules, segment splitting algorithm, and validation criteria |
| `references/hologram-library.md` | 12 hologram types, content matching rules, interaction vocabulary, and color derivation rules |

Read the relevant reference file at each step as instructed below.

---

## STEP 1: Parse Input

### 1.1 Extract Character Identity (from Picture 1)

Describe the character with these mandatory attributes:
- Ethnicity and age category
- Hair: style, length, color, distinctive features (ribbon, bow, etc.)
- Eyewear: frame type, color, chain or strap
- Top clothing: color, style, neckline
- Accessories: jewelry, necklace, ribbon
- Makeup style: natural, bold, luxury

### 1.2 Extract Environment (from Picture 2)

Describe the environment with these mandatory attributes:
- Desk: type, color, shape
- Computer/device: type, color
- Lighting: lamp type, shade color, LED strips, ambient mood
- Chair: material, color, base
- Shelves: type, contents
- Flowers/plants: type, color
- Wall decor: framed prints, signs
- Overall color palette and ambiance

### 1.3 Parse Script

- Preserve the original script verbatim
- Count total characters using the rules in `references/narration-budget-guide.md`
- Identify content features: technical density, conversational markers, emotional markers

### 1.4 Determine Style

- Read the user's style description if provided
- Do NOT impose a fixed style. The user expresses freely.
- Style affects acting and narration delivery only, NOT character appearance.

---

## STEP 2: Calculate Narration Budget

Read `references/narration-budget-guide.md` for the complete guide.

### 2.1 Determine Speech Rate

Priority order:
1. If user provides audio duration: `rate = total_chars / audio_duration`
2. If user directly specifies rate: use that value
3. Otherwise: estimate from content density (see narration-budget-guide.md)

### 2.2 Calculate Per-Segment Budget

```
hologram_pause_total = sum of all hologram interaction pauses in the segment
                   (minimum 2 interactions, each 0.5-2.0 seconds based on complexity)
available_chars = speech_rate * (max_segment_duration - hologram_pause_total)
```

### 2.3 Output Budget Table

| Parameter | Value |
|-----------|-------|
| Total script chars | XXX |
| Speech rate | X.X chars/sec |
| Max segment duration | XX sec |
| Hologram pauses per segment | X.X sec |
| Available chars per segment | XX |

---

## STEP 3: Split Script into Segments

Read `references/narration-budget-guide.md` for the complete splitting algorithm.

### 3.1 Semantic Splitting

1. Split script into sentence units at punctuation (periods, question marks, exclamation marks, semicolons).
2. Count characters per sentence using the word-counting rules.
3. Greedily pack sentences into segments up to `available_chars`.

### 3.2 Long Sentence Handling

- If a single sentence exceeds `available_chars`, split at commas.
- The second half goes to the next segment.
- A transition word may be added at the start of the next segment (counts toward budget).

### 3.3 Strict Text Preservation

CRITICAL: The narration text must be EXACTLY as the user provided. Do NOT:
- Add or remove any words, particles, or filler words
- Adjust word order
- Add transition words between segments
- Paraphrase or rephrase any part of the script
- Abbreviate or expand any text

The only allowed operation is splitting the original text at sentence boundaries or comma boundaries for segmentation. Each character of the original script must appear in exactly one segment, in the original order.

### 3.4 Output Segment Table

```
| Seg | Chars | Narration Duration | Hologram Pause | Total Duration | Narration Text |
|-----|-------|-------------------|----------------|----------------|----------------|
| 1   | XX    | XX.Xs             | X.Xs           | XX.Xs          | "..."          |
| 2   | XX    | XX.Xs             | X.Xs           | XX.Xs          | "..."          |
```

### 3.5 Validate

- Each segment total duration <= max_segment_duration
- All segments concatenated = EXACT match with original script (zero modifications)
- No sentence is cut mid-way (except comma splits for long sentences)

---

## STEP 4: Design Holographic Interactions

Read `references/hologram-library.md` for the complete type library and vocabulary.

### 4.1 Minimum Requirement

- Each segment must have at least 2 holographic interaction elements.
- Adjacent segments should use different type combinations.

### 4.2 Content Matching

For each segment, select hologram types that match the narration content:
- Numbers/specs -> data panel, card deck
- Steps/process -> flow diagram, progress bar
- Comparison/choice -> comparison board, card deck
- Warning/question -> warning icon, flip card
- Result/completion -> confirmation badge, chart curve
- History/version -> timeline ribbon
- Product/model -> 3D model rotation, data panel
- Trend/performance -> chart curve
- Architecture/relation -> map/topology
- Features/keywords -> tag cloud

### 4.3 Choreograph Each Hologram

For every holographic element, specify all four steps:
1. **Summon**: how it appears (materializes, fades in, pops up, slides in...)
2. **Interact**: what the presenter does (taps, pinches, flips, swipes...)
3. **Respond**: how it reacts (flips to reveal, expands, pulses, changes color...)
4. **Exit**: how it leaves (dissolves into particles, fades away, shrinks...)

### 4.4 Derive Color Palette

- Extract dominant colors from the environment reference image (Picture 2).
- Map to hologram colors using the color rules in `references/hologram-library.md`.
- Keep hologram colors consistent across ALL segments.

### 4.5 Output Hologram Design Table

```
| Seg | Hologram ID | Type | Content | Summon | Interact | Respond | Exit | Duration |
|-----|-------------|------|---------|--------|----------|---------|------|----------|
| 1   | H1          | ...  | ...     | ...    | ...      | ...     | ...  | X.Xs     |
| 1   | H2          | ...  | ...     | ...    | ...      | ...     | ...  | X.Xs     |
| 2   | H3          | ...  | ...     | ...    | ...      | ...     | ...  | X.Xs     |
| 2   | H4          | ...  | ...     | ...    | ...      | ...     | ...  | X.Xs     |
```

---

## STEP 5: Generate Ref2VA Prompts

Read `references/ref2va-format-guide.md` for the complete format specification.

For each segment, output a complete Ref2VA prompt with all six sections:

### 5.1 subject_definitions

Define Subject 1 (character), Subject 2 (environment), Picture 1, Picture 2.
- Keep definitions identical across all segments.
- Extract character description from Step 1.1.
- Extract environment description from Step 1.2.

### 5.2 summary

One English paragraph with `[reference generation]` prefix.
- State what the presenter does, where, with which holograms.
- Reference all labels: <Subject 1>, <Subject 2>, <Picture 1>, <Picture 2>.
- State segment duration.

### 5.3 retention_analysis

One line per reference label, all `fully_preserved`.
- List which specific attributes are preserved.

### 5.4 detailed_description

The main body. Follow these rules:

**Opening**: 1-2 English style sentences before [Shot 1]. For segment 2+, add "continuing seamlessly from the previous segment".

**Shots**: 3-4 shots per segment.
- `[Shot 1]` has no timestamp.
- Later shots: `[Shot N] At MM:SS.mmm, the shot cuts to...`
- Timestamps strictly increasing, within 0 to max_segment_duration.

**Camera motion**: type + amplitude + speed as natural English action.

**Speaker**: `(S1)` for the presenter, stable across all segments.

**Dialogue**: Use the narration text from the segment table (Step 3.4).
- On-camera: `The presenter (S1) says: <d>[Chinese] narration text</d>`
- Voiceover: `The presenter (S1) says in an off-screen voiceover: <d>[Chinese] narration text</d> while her/his lips remain completely closed.`

**Holograms**: Insert hologram interactions at appropriate shots. Describe all four steps (summon, interact, respond, exit) using vocabulary from `references/hologram-library.md`.

**Visible text**: Use English double quotation marks for text visible in the scene (e.g., `"16GB VRAM"`).
- IMPORTANT: Text must appear as holographic text, signs, or labels integrated into the scene.
- Do NOT place text as subtitle bars at the bottom of the frame.

**Transitions**: Soft whip pans, hologram wipes, match cuts, or glowing data ribbons between shots.

**Target length**: 350-500 English words.

### 5.5 overall_soundscape

1-4 English sentences summarizing ambient and physical sounds. Include:
- Room ambience (lamp hum, ventilation)
- Holographic UI sounds (chimes, digital ticks)
- Physical action sounds (chair creak, fabric movement, finger taps)
- Do NOT repeat dialogue or music here.

### 5.6 non_diegetic_music

1-3 English sentences describing background music.
- Focus on instrumentation, tempo, rhythm, dynamics.
- Keep music style consistent across segments.
- Use `N/A` if no music.

---

## STEP 6: Validate

Output a validation report for all segments:

| Check Item | Method | Pass Criteria |
|------------|--------|---------------|
| Duration | Last shot timestamp <= max_segment_duration | PASS/FAIL |
| Char count | Count chars in `<d>` tags per segment | <= available_chars |
| Script coverage | Concatenate all segment narration, compare to original | EXACT match (zero modifications to original text) |
| Hologram count | Count hologram interactions per segment | >= 2 per segment |
| Hologram completeness | Check summon/interact/respond/exit for each | All 4 steps present |
| Character consistency | Compare Subject 1 across segments | Identical |
| Environment consistency | Compare Subject 2 across segments | Identical |
| Speaker ID | Check (S1) usage | Stable across segments |
| Timestamp order | Check shot timestamps | Strictly increasing, within range |
| Format completeness | Check 6 sections present | All 6 present |
| No subtitles | Check for subtitle-style text | Text only as in-scene elements |

If any check FAILS, note which segment and item, then revise before final output.

---

## Camera and Acting Guidelines

- Segment 1 typically opens with a medium close-up, then varies angles.
- Later segments use frontal framing, controlled zooms, and holographic transitions.
- The presenter alternates: speaking to camera, gesturing toward workspace, manipulating holograms.
- Motions match the user's style description. Do NOT impose a fixed acting style.
- Continuity across segments: same room, outfit, glasses, hairstyle, holographic design system.

## Audio Guidelines

- Narration voice matches the user's style description.
- Ambient music matches the environment mood, low volume, consistent across segments.
- Holographic UI sounds: chimes, digital ticks, interaction feedback.
- Room ambience: lamp hum, chair creak, fabric movement.
- No loud notifications, harsh whooshes, or comedic stingers.

## Text Rules

- Text in the scene must be integrated as holographic text, signs, labels, or data displays.
- Do NOT generate subtitle bars, lower-third captions, or bottom-of-frame text overlays.
- Keep hologram text short and readable: labels, numbers, short phrases.
- No dense paragraphs of text in holograms.

## Reject or Rewrite If

- Output is one generic prompt instead of N separate segment prompts.
- It ignores the character reference, environment reference, or holographic interaction requirements.
- It changes the character's identity, age, ethnicity, glasses, or outfit palette.
- It changes the environment into a generic office or studio.
- Narration beats are too long to fit their timecode.
- Fewer than 2 holographic interactions in any segment.
- Any hologram missing one of the four steps (summon/interact/respond/exit).
- Script is modified in any way (added, removed, reordered, or rephrased text).
- Text appears as subtitle bars instead of in-scene elements.
- The output depends on or references any external skill.

## Iteration

- When updating this Skill, increment the version in `meta.yaml`.
- Keep all three reference files in sync with SKILL.md changes.
- Do not duplicate reference file content in SKILL.md; reference them by path.