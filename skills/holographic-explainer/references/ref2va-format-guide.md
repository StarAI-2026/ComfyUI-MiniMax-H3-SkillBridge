# Ref2VA Format Complete Guide

This file is the self-contained format specification for the holographic-explainer skill. It does not depend on any external skill.

## Six-Section Structure

Each segment prompt must output six fields in this exact order:

| Order | Field Name | Purpose |
|-------|-----------|---------|
| 1 | subject_definitions | Define reference content and their labels |
| 2 | summary | Summarize task type and reference relationships |
| 3 | retention_analysis | Describe how reference content is preserved |
| 4 | detailed_description | Shot-by-shot description of visuals, actions, sound, dialogue |
| 5 | overall_soundscape | Summarize ambient and physical sounds |
| 6 | non_diegetic_music | Describe background music |

---

## 1. subject_definitions

Define each piece of referenced content that must be tracked.

### Label Types

| Label | Meaning |
|-------|---------|
| <Subject N> | Reusable visible content abstracted from reference images (people, environments, clothing, props, etc.) |
| <Picture N> | A reference image used as a concrete frame anchor |

### Rules

- <Subject 1> = the character presenter, extracted from Picture 1
- <Subject 2> = the environment/room, extracted from Picture 2
- <Picture 1> = the character reference image, declaring its reference role
- <Picture 2> = the environment reference image, declaring its reference role
- Once defined, labels stay consistent across all fields and all segments
- Subject 1, Subject 2, Picture 1, Picture 2 definitions must be identical across all segments

### Template

```text
subject_definitions:
<Subject 1> is [character description: ethnicity, age category, hair style and color, glasses and accessories, top clothing color and style, jewelry, makeup style]. She/He is the presenter named [presenter name].
<Subject 2> is [environment description: desk type and color, computer device, lamp type and shade color, chair material and color, shelves, flowers/plants, wall decor, overall color palette, ambience].
<Picture 1> is the presenter reference image, defining the character identity, facial structure, hairstyle, glasses, wardrobe, and accessories for all shots in this segment.
<Picture 2> is the environment reference image, defining the room layout, color palette, furniture, decor, and lighting mood for all shots in this segment.
```

---

## 2. summary

One English paragraph starting with a square-bracketed task-type prefix.

```text
[reference generation] The target video shows <Subject 1> ([presenter name]) [doing what, where] with [holographic interaction description]. <Picture 1> provides the character reference. <Picture 2> provides the environment reference. [One-sentence summary of segment content and duration].
```

---

## 3. retention_analysis

One line per reference label, all using `fully_preserved`.

```text
<Subject 1> (appears in [list all shots]): fully_preserved - [list specific preserved attributes].
<Subject 2> (appears in [list all shots]): fully_preserved - [list specific preserved attributes].
<Picture 1> (character reference): fully_preserved - [confirm consistent application].
<Picture 2> (environment reference): fully_preserved - [confirm consistent application].
```

---

## 4. detailed_description

The main body. Shot-by-shot description.

### Opening
- 1-2 English style sentences before [Shot 1]
- For segment 2 and later: add "continuing seamlessly from the previous segment"

### Shot Format
- `[Shot 1]` has no timestamp
- Later shots: `[Shot N] At MM:SS.mmm, the shot cuts to...`
- Timestamps must be strictly increasing and within 0 to max_segment_duration

### Camera Motion
Write as natural English action, including type + amplitude + speed:

| Dimension | Expression | Description |
|-----------|-----------|-------------|
| Type | Zoom In / Zoom Out | Focal length change |
| Type | Push In / Pull Out | Camera moves forward/backward |
| Type | Pan Left / Pan Right | Horizontal pivot |
| Type | Truck Left / Truck Right | Horizontal translation |
| Type | Tilt Up / Tilt Down | Vertical pivot |
| Type | Arc Shot | Arc movement around subject |
| Type | Tracking Shot | Follow subject |
| Type | Static Shot | Stationary |
| Amplitude | with small amplitude | Small range |
| Amplitude | with large amplitude | Large range |
| Speed | at slow speed | Slow pace |
| Speed | at fast speed | Fast pace |

Example: `The camera pushes in with small amplitude at slow speed toward...`

### Speaker and Dialogue
- Speaker ID: `(S1)` for the presenter, stable across all segments
- On-camera: `The presenter (S1) says: <d>[Chinese] narration text</d>`
- Voiceover: `The presenter (S1) says in an off-screen voiceover: <d>[Chinese] narration text</d> while her/his lips remain completely closed.`
- Dialogue across cuts: use `<scenetrans>` at connection points
- Truncated speech: use `<cutoff>`

### In-Scene Text
- Visible text in the scene uses English double quotation marks: `"16GB VRAM"`
- Text must appear as holographic text, signs, or labels integrated into the scene
- Do NOT place text as subtitle bars at the bottom of the frame

### Holographic Interaction Description
Each holographic element must describe four steps:
1. Summon (materializes, fades in, pops up, slides in...)
2. Interact (taps, pinches, flips, swipes...)
3. Respond (flips to reveal, expands, pulses, changes color...)
4. Exit (dissolves into particles, fades away, shrinks...)

### Word Count Target
- Generation tasks: 350-500 English words
- Dialogue-dense content: prioritize fitting the complete spoken timeline over reaching word count

---

## 5. overall_soundscape

1-4 English sentences summarizing ambient and physical sounds. Do not repeat dialogue or music.

```text
overall_soundscape: [Ambient sound description, including holographic UI sounds, room ambience, physical action sounds].
```

---

## 6. non_diegetic_music

1-3 English sentences describing background music. Use `N/A` when no music.

```text
non_diegetic_music: [Instrumentation, tempo, rhythm, dynamic changes description].
```

---

## Cross-Segment Continuity Checklist

- [ ] Subject 1 description identical in every segment
- [ ] Subject 2 description identical in every segment
- [ ] Presenter name identical in every segment
- [ ] Outfit, glasses, hairstyle, accessories identical in every segment
- [ ] Room layout, furniture, color palette identical in every segment
- [ ] Hologram design system colors identical in every segment
- [ ] Speaker ID (S1) stable across segments
- [ ] Segment 2+ opens with continuity note
- [ ] Background music style consistent across segments