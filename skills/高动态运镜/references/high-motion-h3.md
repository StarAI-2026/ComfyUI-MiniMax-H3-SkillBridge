# High-motion H3 grammar

## Contents

1. High-motion definition
2. Flexible action architecture
3. Camera-command grammar
4. Motion density and causality
5. High-motion vocabulary
6. Rejection checklist
7. Official sources

## 1. High-motion definition

A high-motion prompt must change the image strongly over time. Require all of the following:

- The subject travels across at least two axes, such as forward plus down, sideways plus up, or forward plus rotational banking.
- The subject's apparent scale or camera-to-subject distance changes substantially.
- Foreground structures, cables, rails, debris, or particles whip across the frame to create fast parallax.
- The subject interacts with a physical feature: passes through a frame, clears a gap, scrapes a rail, dives around traffic, strikes a surface, redirects thrust, overtakes a vehicle, or narrowly misses an obstacle.
- Acceleration or deceleration is visible through body compression, thrust shape, wake distortion, sparks, dust, rain peel-off, shockwaves, or fabric/hair lag.
- The camera does more than passively center the subject. It chases, dives, rises, sweeps laterally, changes side, changes distance, or rolls with a large perspective shift.

Do not confuse high motion with a long list of unrelated moves. Motion should be fast, spatially large, and causally connected.

## 2. Flexible action architecture

Compose a shot around one dominant spatial path and one compatible camera pursuit. Use roughly three connected beats for a five-second test, but change the beat types to suit the concept.

Valid architectures include:

- high-speed weave → near miss → slingshot exit;
- vertical dive → corkscrew redirection → explosive climb;
- rail grind → gap transfer → wall ride;
- chase/overtake → side swap → close lens pass;
- ground skim → launch → air trick → landing drift;
- aerial pursuit → obstacle dodge → target intercept;
- falling pursuit → surface ricochet → lateral escape.

The supplied hoverboard sample demonstrates the fifth architecture. It contributes strong vocabulary and causal motion evidence, but its timestamps, takeoff, 180-degree orbit, and landing drift are not default requirements.

## 3. Camera-command grammar

MiniMax's official I2V API documents 15 bracketed commands for Hailuo 2.3, Hailuo 2.3 Fast, Hailuo 02, and I2V-01-Director:

`[Truck left]`, `[Truck right]`, `[Pan left]`, `[Pan right]`, `[Push in]`, `[Pull out]`, `[Pedestal up]`, `[Pedestal down]`, `[Tilt up]`, `[Tilt down]`, `[Zoom in]`, `[Zoom out]`, `[Shake]`, `[Tracking shot]`, `[Static shot]`.

Use commands inside `detailed_description`, embedded in natural English. Examples:

```text
[Tracking shot,Push in] The camera dives after her at fast speed with large amplitude...
At 00:01.300, [Tracking shot,Truck right] the camera whips outside her hard bank as foreground beams slice across frame...
From 00:03.800 to 00:05.000, [Tracking shot,Pedestal up] the camera rises with her while the city rapidly shrinks below...
```

- Put simultaneous commands inside one bracket, separated by commas.
- Use no more than three simultaneous commands in one bracket.
- Place sequential command groups at different timeline beats.
- Prefer explicit commands for accuracy; use natural English for arc shots, orbiting, crane-like sweeps, camera rolls, and fly-bys because these lack official bracket commands.
- Do not use `[Static shot]` in high-motion mode.
- Avoid combining opposite commands simultaneously, such as Push in plus Pull out.
- Match the camera to the action. A descent may use tracking plus tilt/pedestal down; a lateral weave may use tracking plus truck/pan; a climb may use tracking plus tilt/pedestal up; a close pass may use push in followed by pull out.

## 4. Motion density and causality

For every beat, specify this chain:

`subject force/action → body or equipment response → environmental reaction → camera response`.

Example:

```text
The left thruster flares, forcing a hard right bank; her coat and hair snap left, rain shears into a curved wake, and the chase camera dives inside the turn.
```

Use speed contrast. Begin fast, spike speed at an obstacle, redirect sharply, accelerate out, or compress on contact. Avoid a whole clip of uniform-speed parallel tracking.

## 5. High-motion vocabulary

Prefer concrete verbs and effects:

- Acceleration: explodes forward, rockets, catapults, slingshots, surges, bursts, snaps forward.
- Direction change: banks hard, dives, pitches upward, yaws, corkscrews, redirects thrust, rebounds, ricochets.
- Interaction: threads, clears, scrapes, clips, vaults, skims, wall-rides, overtakes, punches through mist.
- Camera pursuit: dives after, whips laterally, sweeps beneath, races alongside, surges forward, falls behind, arcs rapidly, flips to the opposite side.
- Parallax: foreground beams streak past, cables lash across frame, towers expand outward, road markings smear beneath, the ground spins below.
- Physical response: sparks fan backward, fabric snaps, hair lags then whips, dust walls erupt, rain peels off, vapor cones tighten, shock rings expand.

Avoid low-energy phrases as the main motion: slowly pushes in, gently pans, subtle drift, small adjustment, remains centered, holds the pose, settles calmly.

## 6. Rejection checklist

Reject and rewrite a prompt when any condition is true:

- The subject is not already meaningfully moving at 00:00.000.
- The subject stays near the same screen position and scale for most of the clip.
- The only visible motion is hair, cloth, particles, blinking, or a camera push-in.
- No foreground object crosses the frame.
- No obstacle, contact point, gap, gate, surface, vehicle, or spatial target affects the action.
- All camera movement is slow, small-amplitude, static, or merely parallel.
- More than three simultaneous official commands appear inside one bracket.
- The action list lacks physical transitions connecting one beat to the next.
- Every batch case repeats the same launch, orbit, landing, or drift progression without the user requesting that template.
- A final idle gesture consumes the payoff instead of completing a high-speed spatial event.

When sample matching is explicitly requested, additionally apply the exact checks in `sample-motion-blueprint.md`.

## 7. Official sources

- MiniMax Image-to-Video API camera-command documentation: https://platform.minimax.io/docs/api-reference/video-generation-i2v
- MiniMax Hailuo 2.3 release: https://www.minimax.io/news/minimax-hailuo-23
- MiniMax Hailuo start/end-frame dynamics examples: https://www.minimax.io/news/minimax-hailuo-02-start-end-frames-feature-is-now-live
