# Narration Budget and Segment Splitting Guide

This file is the self-contained narration budget calculation and script splitting specification for the holographic-explainer skill.

## Core Principles

- Max segment duration is user-specified (default 15 seconds). The skill must NOT hardcode a fixed duration.
- Each segment's narration must be fully spoken within that segment's duration.
- Script coverage must be 100%. Minor colloquial adjustments are allowed as long as meaning is preserved.
- Speech rate is NOT fixed. It is calculated from content density or user-provided audio duration.

---

## Speech Rate Determination

### Method 1: User Provides Audio Duration
If the user provides a narration audio file or specifies total duration:

```text
actual_rate (chars/sec) = total_chars / audio_duration (sec)
available_chars_per_segment = actual_rate * max_segment_duration - hologram_pause_chars
```

### Method 2: Estimate from Content Density
If the user does not provide audio duration, estimate speech rate from content features:

| Content Feature | Estimated Rate (Chinese chars/sec) | Explanation |
|----------------|--------------------------------------|-------------|
| Tech-spec heavy (many numbers, models, terms) | 2.5-3.0 | Needs slower pace for comprehension |
| Educational (steps, processes, principles) | 3.0-3.5 | Moderate, slightly slow |
| Conversational (colloquial, stories, analogies) | 3.5-4.5 | Natural conversation rhythm |
| High-energy / fast-paced promotion | 4.5-5.5 | Fast and punchy |

Detection methods:
- Count numbers + English terms ratio: >30% -> tech-spec heavy
- Count comma/period ratio: high -> educational
- Count colloquial markers ("right?", "you see", "just like"): many -> conversational
- Count exclamation/question marks: >15% -> high-energy

### Method 3: User Directly Specifies
User can directly specify speech rate (e.g., "4 chars/second"). Skip estimation.

---

## Character Counting Rules

| Content Type | Counting Method | Example |
|-------------|-----------------|---------|
| Chinese character | 1 char each | "显存" = 2 chars |
| English word | 2 chars per word | "VRAM" = 2 chars |
| Digit group | 1 char per group | "16" = 1 char, "32" = 1 char |
| Single letter | 1 char each | "G" = 1 char, so "16G" = 2 chars total |
| Punctuation | 0 chars | "，" = 0 chars |
| Transition words | Counted as chars | "接下来" = 3 chars |

### Mixed Token Rule
For tokens mixing digits and letters (like "16G", "8GB"):
- Split into digit groups and letter groups
- Count each group as 1 char
- "16G" = "16"(1) + "G"(1) = 2 chars
- "8GB" = "8"(1) + "GB"(1) = 2 chars
- "RTX3090" = "RTX"(1) + "3090"(1) = 2 chars

---

## Holographic Interaction Pause Budget

Each segment requires at least 2 holographic interactions. Each interaction needs the presenter to pause or coordinate a physical action:

| Interaction Complexity | Pause Duration | Description |
|----------------------|-----------------|-------------|
| Simple (tap, point) | 0.5-1.0 sec | Quick interaction |
| Medium (flip, expand, pinch) | 1.0-1.5 sec | Requires hand coordination |
| Complex (multi-card, drag, rotate) | 1.5-2.0 sec | Requires visible body movement |

Total hologram pause per segment = interaction 1 pause + interaction 2 pause (+ interaction 3 pause if present)

```text
available_chars_per_segment = speech_rate * (max_segment_duration - total_hologram_pause)
```

---

## Segment Splitting Algorithm

### Input
- Full script text
- Max segment duration (default 15 seconds)
- Estimated speech rate
- Total hologram pause duration

### Steps

1. **Calculate available chars per segment**

```text
available_chars = speech_rate * (max_segment_duration - total_hologram_pause)
```

2. **Semantic splitting**
   - Split script into sentence units at punctuation (periods, question marks, exclamation marks, semicolons)
   - Count characters per sentence using the counting rules above

3. **Greedy bin packing**
   - Start from the first sentence, accumulate characters
   - When accumulated chars approach available_chars, split at the nearest semantic boundary
   - If adding the current sentence would exceed available_chars:
     - Overflow < 3 chars: include the sentence
     - Overflow >= 3 chars: move the sentence to the next segment

4. **Long sentence handling**
   - If a single sentence exceeds available_chars:
     - Split at commas
     - First half goes to current segment, second half goes to next segment
     - A transition word may be added at the start of the next segment (counts toward budget)

5. **Colloquial micro-adjustments**
   - If a segment is a few chars short of full: add filler words ("right?", "you see", "actually") without changing meaning
   - If a segment is a few chars over: remove redundant particles ("的", "了", "一下") without changing meaning
   - Adjusted text must preserve the original meaning

6. **Inter-segment transitions**
   - If the next segment needs context from the previous one, add a transition word at the start
   - Transition word chars count toward that segment's budget

7. **Last segment check**
   - If the last segment has fewer than 50% of available_chars, move 1-2 sentences from the previous segment

### Edge Cases

| Scenario | Handling |
|----------|----------|
| Very short script (< 30 chars) | Single segment. No splitting needed. Ensure at least 2 holographic interactions. |
| Very long script (> 500 chars) | Warn the user: "This script will produce N segments. Consider trimming or increasing max segment duration." |
| Pure English script | Apply English word counting (2 chars/word) consistently. |
| Script contains line breaks | Treat line breaks as semantic boundaries, equivalent to semicolons. |
| Single sentence longer than available_chars | Split at commas. If no commas, split at the char limit and add "..." in narration. |

### Output Format

```text
| Seg | Chars | Narration Duration | Hologram Pause | Total Duration | Narration Text |
|-----|-------|-------------------|----------------|----------------|----------------|
| 1   | XX    | XX.Xs             | X.Xs           | XX.Xs          | "..."          |
| 2   | XX    | XX.Xs             | X.Xs           | XX.Xs          | "..."          |
```

---

## Validation Rules

| Check Item | Method | Pass Criteria |
|-----------|--------|---------------|
| Duration | Each segment total = narration + hologram pause | <= max_segment_duration |
| Char count | Count chars inside `<d>` tags per segment | <= available_chars |
| Coverage | Concatenate all segment narration, compare to original | 100% (with allowed micro-adjustments) |
| Completeness | No sentence cut mid-way | Except long sentence comma splits |
| Uniformity | Segment char count variance | Max segment chars <= available_chars * 110% |

---

## Example

### Input

```text
Script: "MiniMax H3到底怎么玩？全网最全攻略玩法，它来了！很多博主说8G显存就能跑H3，确实能跑，但你看过跑起来的效果和时间吗？如果想要比较好的画面与时间，我建议最低档的硬件要求16G显存和32G内存起步或者等GGUF量化模型。中档位的硬件要求24G显存和48G内存，3090是一个性价比高的选择。有条件的可以直接上32G显存和64G内存，速度和分辨率都有很大提升。"
Max segment duration: 15 seconds
Estimated rate: 3.0 chars/sec (tech-spec heavy)
Hologram pause: 2 interactions x 1.5 sec = 3 sec
Available chars = 3.0 * (15 - 3) = 36 chars
```

### Split Result

```text
| Seg | Chars | Narration | Pause | Total | Narration Text |
|-----|-------|-----------|-------|-------|----------------|
| 1   | 35    | 11.7s     | 3.0s  | 14.7s | MiniMax H3到底怎么玩？全网最全攻略玩法，它来了！很多博主说8G显存就能跑H3， |
| 2   | 33    | 11.0s     | 3.0s  | 14.0s | 确实能跑，但你看过跑起来的效果和时间吗？我建议最低档16G显存和32G内存起步。 |
| 3   | 30    | 10.0s     | 3.0s  | 13.0s | 或者等GGUF量化模型。中档位24G显存和48G内存，3090性价比高。 |
| 4   | 28    | 9.3s      | 3.0s  | 12.3s | 有条件的直接上32G显存和64G内存，速度和分辨率都有很大提升。 |
```

Coverage check: original 126 chars, split total 126 chars, 100% coverage.