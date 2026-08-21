/* ═══════════════════════════════════════════════════════════════════════════
   THE PROCESSION — Rooms I, II, IV, V
   Blueprint §11.2: four rooms, one continuous camera, no cuts.

   Room III is deliberately absent from this file. §11.5 makes it a LAW that
   the blacklight room is DOM and not WebGL, because that surface is MADE OF
   TYPE and rendering type into a texture is F-04 — the single largest source
   of the "AI-generated" read. It lives in Overlay.tsx, in real DOM, at device
   resolution. The canvas drops to 30% opacity and lets the paper own the frame.
   ═══════════════════════════════════════════════════════════════════════════ */

import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { useEffect, useMemo, useRef, useState } from 'react';
import * as THREE from 'three';
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js';
import { damp, ease, frames, platePaint, scroll, span, type Tier } from './lib';

/* ── §11.7 · the light-theme inversion ─────────────────────────────────────
   In THE LIGHT TABLE the scene is NOT simply brightened. It becomes a
   different room: the black water becomes milk glass on a backlit table, the
   raking key becomes a soft top-down diffuse, the fill goes from a cold 12%
   hemispheric to a 45% bounce off the table surface, and the records read as
   INK rather than as light — multiplicative, not additive.

   A brightened dark scene looks like a dark scene with the lights left on. The
   whole point of the light table is that it is lit from underneath. */
export interface Palette {
  ground: string;      // scene background and the far water
  fog: string;
  fogBase: number;
  keyColour: string;
  keyIntensity: number;
  keyPosition: [number, number, number];
  fillSky: string;
  fillGround: string;
  fillIntensity: number;
  documents: string;
  pointCold: string;
  additive: boolean;
  reflectionStrength: number;
  envIntensity: number;
}

const VAULT: Palette = {
  ground: '#05060a',
  fog: '#05060a',
  fogBase: 0.028,
  keyColour: '#ffe9d0',
  keyIntensity: 2.8,
  keyPosition: [-4, 3.4, 2.4],
  fillSky: '#22303f',
  fillGround: '#05060a',
  fillIntensity: 0.32,
  documents: '#14161b',
  pointCold: '#7d868f',
  additive: true,
  reflectionStrength: 0.86,
  envIntensity: 0.30,
};

const LIGHT_TABLE: Palette = {
  ground: '#efeae1',
  fog: '#f4eee6',
  fogBase: 0.010,
  // Soft, top-down, 5600K. Not a raking key: on a light table the source is
  // beneath the glass and the top light is only there to keep the object solid.
  keyColour: '#fff6ea',
  keyIntensity: 1.5,
  keyPosition: [-1.2, 6.0, 2.0],
  fillSky: '#ffffff',
  fillGround: '#e6ddcd',
  fillIntensity: 0.95,
  documents: '#cfc7b8',
  pointCold: '#4a4f56',
  additive: false,
  // Milk glass rather than a mirror — but still legible. The reflection reads
  // IP54 and 10 A where the plate reads IP66 and 16 A, and a visitor who cannot
  // make out those four values has been shown a nice gradient instead of an
  // argument.
  reflectionStrength: 0.62,
  envIntensity: 0.55,
};

function readTheme(): 'light' | 'dark' {
  const explicit = document.documentElement.getAttribute('data-theme');
  if (explicit === 'light' || explicit === 'dark') return explicit;
  return matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

/** The scene reads theme tokens at init AND on change (§6.6). */
function usePalette(): Palette {
  const [theme, setTheme] = useState<'light' | 'dark'>(() => readTheme());
  useEffect(() => {
    const update = () => setTheme(readTheme());
    const observer = new MutationObserver(update);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    const media = matchMedia('(prefers-color-scheme: dark)');
    media.addEventListener('change', update);
    // theme.js dispatches this when the toggle is used.
    document.documentElement.addEventListener('datum:theme', update);
    return () => {
      observer.disconnect();
      media.removeEventListener('change', update);
      document.documentElement.removeEventListener('datum:theme', update);
    };
  }, []);
  return theme === 'dark' ? VAULT : LIGHT_TABLE;
}

/* ── The camera path (§10.7) ───────────────────────────────────────────────
   Scroll sets a TARGET; the camera chases it with inertia. It is never
   assigned from scroll directly — that was F-03, and it is why the prototype
   transmitted every scroll stutter 1:1 into the image.

   One path through all five rooms, travelling -Z. No cuts: a cut would make
   this five scenes with a wipe between them, which is a slideshow. */
type Waypoint = { at: number; pos: [number, number, number]; look: [number, number, number]; fov: number };

const PATH: Waypoint[] = [
  // The plate sits just ABOVE the waterline and the camera looks DOWN onto it.
  //
  // This is not a taste decision, it is the geometry. An earlier framing put
  // the plate at eye height with a level 46-degree camera, and the reflection
  // was simply not in shot: the mirrored plate lands ~29 degrees below the view
  // axis and a 46-degree FOV only reaches 23. The scene rendered perfectly and
  // showed nothing, which is the most expensive kind of correct.
  //
  // Object low, close to the surface, camera slightly above: the composition
  // every still-water photograph has used for a century, for this reason.
  { at: 0.00, pos: [0, 2.50, 5.60], look: [0, -0.42, 0], fov: 52 },
  { at: 0.14, pos: [0, 1.90, 2.20], look: [0, 0.30, -3], fov: 50 },
  // II · COMPRESSION. FOV 48 → 32 and the fog climbs: the passage narrows
  // optically as well as physically, which is what makes it uncomfortable
  // rather than merely dark.
  { at: 0.30, pos: [0, 1.05, -17], look: [0, 1.00, -26], fov: 32 },
  { at: 0.56, pos: [0, 1.30, -30], look: [0, 0.90, -40], fov: 38 },
  // IV · THE ARCHIVE. Pull up and back to see the lattice fall.
  { at: 0.84, pos: [0, 6.20, -46], look: [0, 0.20, -64], fov: 46 },
  // V · THE QUEUE. Lights come up; the product resolves.
  { at: 1.00, pos: [0, 1.70, -54], look: [0, 0.45, -66], fov: 40 },
];

function sample(t: number) {
  let a = PATH[0];
  let b = PATH[PATH.length - 1];
  for (let i = 0; i < PATH.length - 1; i++) {
    if (t >= PATH[i].at && t <= PATH[i + 1].at) {
      a = PATH[i];
      b = PATH[i + 1];
      break;
    }
  }
  const k = ease(span(t, a.at, b.at));
  const mix = (x: number, y: number) => x + (y - x) * k;
  return {
    pos: [mix(a.pos[0], b.pos[0]), mix(a.pos[1], b.pos[1]), mix(a.pos[2], b.pos[2])] as const,
    look: [mix(a.look[0], b.look[0]), mix(a.look[1], b.look[1]), mix(a.look[2], b.look[2])] as const,
    fov: mix(a.fov, b.fov),
  };
}

/* ── Room I · the reflection that lies ─────────────────────────────────────
   The mirror is not showing the plate. A second scene, holding a DIFFERENT
   plate, is rendered from the mirrored camera into a render target, and the
   water samples that. So the reflection is genuinely showing something else —
   not a distorted copy, a different object. That is the whole beat of Act I
   and it cannot be faked with a filter.

   Scroll drives uDecohere: ripple amplitude 0.002 → 0.09 plus a lateral shear.
   The reflection comes apart while the real plate stays perfectly still. */

const WATER_VERT = /* glsl */ `
  uniform mat4 uTextureMatrix;
  varying vec4 vReflect;
  varying vec4 vClip;
  void main() {
    vec4 world = modelMatrix * vec4(position, 1.0);
    // The reflected sample coordinate, projected. NOT the fragment's own screen
    // position: sampling a mirrored render by screen UV only happens to work
    // when the virtual camera shares the main camera's projection, and building
    // that camera by hand (mirror the position, flip up, lookAt the mirrored
    // target) does not produce it. The plate's reflection landed 150px away
    // from where the plate met the water — a detached smear rather than a
    // mirror. This is the texture matrix three's own Reflector uses.
    // modelMatrix included: the texture matrix maps WORLD space, and this
    // plane is rotated -90 degrees about X. Feeding it the local position
    // sampled the render target somewhere off the plane entirely, and the
    // reflection disappeared while every matrix in it was individually correct.
    vReflect = uTextureMatrix * world;
    vClip = projectionMatrix * viewMatrix * world;
    gl_Position = vClip;
  }
`;

const WATER_FRAG = /* glsl */ `
  uniform sampler2D uMirror;
  uniform float uTime;
  uniform float uDecohere;
  uniform float uFade;
  uniform vec3 uGround;
  uniform float uStrength;
  varying vec4 vReflect;
  varying vec4 vClip;

  void main() {
    vec2 uv = vReflect.xy / max(0.0001, vReflect.w);

    // Two crossed sines, not noise: still water under a raking light shows
    // interference, and a noise field reads as fog on a surface.
    float r =
      sin(uv.y * 42.0 + uTime * 0.9) * 0.5 +
      sin(uv.x * 26.0 - uTime * 0.6) * 0.5;

    // Amplitude 0.002 -> 0.09, exactly as specified in §11.3, plus the lateral
    // shear that makes the false plate slide out of register with the real one.
    float amp = mix(0.002, 0.09, uDecohere);
    uv.x += r * amp;
    uv.x += (uv.y - 0.5) * uDecohere * 0.055;
    uv.y += r * amp * 0.35;

    vec3 mirrored = texture2D(uMirror, clamp(uv, 0.001, 0.999)).rgb;

    // The reflection is strong immediately under the waterline and gone before
    // it reaches the hero line. Faded on the SCREEN axis rather than the plane's
    // own UV, which turned out to be inverted and put the busiest part of the
    // image directly behind the one sentence on the page that matters.
    //
    // §6.8 forbids gradients as decoration and permits them for depth in WebGL.
    // This is the second: water reflects most where it meets the object and
    // least where it runs out toward the viewer, and a mirror that carries all
    // the way to the bottom of frame reads as chrome rather than as water.
    float sy = (vClip.y / vClip.w) * 0.5 + 0.5;
    float strength = smoothstep(0.30, 0.52, sy) * uFade;

    vec3 colour = mix(uGround, mirrored, strength * uStrength);
    gl_FragColor = vec4(colour, 1.0);
  }
`;

function usePlate(spec: { ingress: string; voltage: string; current: string }) {
  return useMemo(() => {
    const texture = new THREE.CanvasTexture(platePaint(spec));
    texture.colorSpace = THREE.SRGBColorSpace;
    texture.anisotropy = 8;
    return texture;
  }, [spec.ingress, spec.voltage, spec.current]);
}

function Plate({ map, ...rest }: { map: THREE.Texture } & Record<string, unknown>) {
  return (
    <mesh {...rest} castShadow={false}>
      {/* Real bevels, not a quad. A plate with a sharp silhouette edge reads as
          a decal; the bevel is what catches the key and says "object". */}
      <boxGeometry args={[2.56, 1.6, 0.05]} />
      <meshStandardMaterial
        map={map}
        metalness={0.55}
        roughness={0.42}
        envMapIntensity={1.0}
      />
    </mesh>
  );
}

function RoomI({ tier, palette }: { tier: Tier; palette: Palette }) {
  const { gl, scene } = useThree();
  const water = useRef<THREE.ShaderMaterial>(null);
  const real = usePlate({ ingress: 'IP66', voltage: '400 V', current: '16 A' });
  const lie = usePlate({ ingress: 'IP54', voltage: '400 V', current: '10 A' });

  // The render target and the second scene. On the `lite` tier there is no
  // reflection at all: it is the single most expensive thing in Room I, and a
  // still mirror on integrated graphics is worse than an honest dark surface.
  const rig = useMemo(() => {
    const target = new THREE.WebGLRenderTarget(1024, 640, {
      minFilter: THREE.LinearFilter,
      magFilter: THREE.LinearFilter,
      colorSpace: THREE.SRGBColorSpace,
    });
    const falseScene = new THREE.Scene();
    falseScene.background = new THREE.Color(palette.ground);

    const plate = new THREE.Mesh(
      new THREE.BoxGeometry(2.56, 1.6, 0.05),
      new THREE.MeshStandardMaterial({ map: lie, metalness: 0.55, roughness: 0.46 })
    );
    plate.position.set(0, 0.86, 0);
    falseScene.add(plate);

    const key = new THREE.DirectionalLight(palette.keyColour, palette.keyIntensity);
    key.position.set(...palette.keyPosition);
    falseScene.add(
      key,
      new THREE.HemisphereLight(palette.fillSky, palette.fillGround, palette.fillIntensity)
    );

    const mirror = new THREE.PerspectiveCamera(52, 1, 0.1, 140);
    return {
      target,
      falseScene,
      plate,
      mirror,
      normal: new THREE.Vector3(0, 1, 0),
      origin: new THREE.Vector3(0, 0, 0),
      view: new THREE.Vector3(),
      look: new THREE.Vector3(),
      lookTarget: new THREE.Vector3(),
      camWorld: new THREE.Vector3(),
      rotation: new THREE.Matrix4(),
      textureMatrix: new THREE.Matrix4(),
    };
  }, [lie, palette]);

  useEffect(() => () => rig.target.dispose(), [rig]);

  useFrame((state, delta) => {
    const t = scroll.progress;
    const room = span(t, 0, 0.16);
    const decohere = ease(room);

    if (water.current) {
      water.current.uniforms.uTime.value = state.clock.elapsedTime;
      water.current.uniforms.uDecohere.value = decohere;
      water.current.uniforms.uFade.value = 1 - ease(span(t, 0.12, 0.2));
    }

    if (tier !== 'full') return;

    // The false plate tracks the pointer at 0.84x the real one. It ALMOST
    // follows. That lag is what makes the wrongness surface before a visitor
    // can name it — and it is why the reflection is a second scene rather than
    // a mirrored copy: a copy cannot lag.
    const px = state.pointer.x;
    const py = state.pointer.y;
    rig.plate.rotation.y = damp(rig.plate.rotation.y, px * 0.20 * 0.84, 0.09, frames(delta));
    rig.plate.rotation.x = damp(rig.plate.rotation.x, -py * 0.12 * 0.84, 0.09, frames(delta));

    // A real planar reflection across y = 0, the way three's Reflector does it:
    // reflect the camera's POSITION and its LOOK DIRECTION about the plane,
    // reuse the main camera's projection unchanged, and build a texture matrix
    // that maps a water vertex to the right texel of the mirrored render.
    const cam = state.camera as THREE.PerspectiveCamera;
    rig.camWorld.setFromMatrixPosition(cam.matrixWorld);

    rig.view.subVectors(rig.origin, rig.camWorld).reflect(rig.normal).negate().add(rig.origin);
    rig.rotation.extractRotation(cam.matrixWorld);
    rig.look.set(0, 0, -1).applyMatrix4(rig.rotation).add(rig.camWorld);
    rig.lookTarget
      .subVectors(rig.origin, rig.look)
      .reflect(rig.normal)
      .negate()
      .add(rig.origin);

    rig.mirror.position.copy(rig.view);
    rig.mirror.up.set(0, 1, 0).applyMatrix4(rig.rotation).reflect(rig.normal);
    rig.mirror.lookAt(rig.lookTarget);
    rig.mirror.far = cam.far;
    rig.mirror.updateMatrixWorld();
    rig.mirror.projectionMatrix.copy(cam.projectionMatrix);

    // Clip space (-1..1) to texture space (0..1), then project through the
    // virtual camera and into the water's own model space.
    rig.textureMatrix.set(
      0.5, 0.0, 0.0, 0.5,
      0.0, 0.5, 0.0, 0.5,
      0.0, 0.0, 0.5, 0.5,
      0.0, 0.0, 0.0, 1.0
    );
    rig.textureMatrix.multiply(rig.mirror.projectionMatrix);
    rig.textureMatrix.multiply(rig.mirror.matrixWorldInverse);
    if (water.current) {
      water.current.uniforms.uTextureMatrix.value.copy(rig.textureMatrix);
    }

    // The false plate is in its own scene, so it needs the same environment or
    // it renders as a black rectangle in the water while the real one does not
    // — which would give the game away for the wrong reason.
    if (rig.falseScene.environment !== scene.environment) {
      rig.falseScene.environment = scene.environment;
      rig.falseScene.environmentIntensity = scene.environmentIntensity;
    }

    // Keep the target's aspect matched to the canvas, or the mirrored render is
    // stretched relative to the projection that samples it.
    const size = gl.getSize(new THREE.Vector2());
    const wantW = 1024;
    const wantH = Math.max(256, Math.round((wantW * size.y) / Math.max(1, size.x)));
    if (rig.target.height !== wantH) rig.target.setSize(wantW, wantH);

    const previous = scene.background;
    gl.setRenderTarget(rig.target);
    gl.render(rig.falseScene, rig.mirror);
    gl.setRenderTarget(null);
    scene.background = previous;
  }, -1);

  return (
    <group>
      {/* THE OBJECT. Still. It is the reflection that moves. */}
      <Plate map={real} position={[0, 0.86, 0]} />

      {/* THE WATER. Edge to edge, absolutely still. */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0, 0]}>
        <planeGeometry args={[60, 60]} />
        <shaderMaterial
          ref={water}
          vertexShader={WATER_VERT}
          fragmentShader={WATER_FRAG}
          uniforms={useMemo(
            () => ({
              uMirror: { value: rig.target.texture },
              uTime: { value: 0 },
              uDecohere: { value: 0 },
              uFade: { value: 1 },
              uGround: { value: new THREE.Color(palette.ground) },
              uStrength: { value: palette.reflectionStrength },
              uTextureMatrix: { value: new THREE.Matrix4() },
            }),
            [rig, palette]
          )}
        />
      </mesh>
    </group>
  );
}

/* ── Room II · compression ─────────────────────────────────────────────────
   A passage between two walls of UNLIT stacked documents. Deliberately
   uncomfortable: this is what an unverifiable catalog feels like from inside.
   The documents are instanced because there are 1,800 of them and eighteen
   hundred draw calls is a slideshow. */

function RoomII({ palette }: { palette: Palette }) {
  const walls = useRef<THREE.InstancedMesh>(null);
  const group = useRef<THREE.Group>(null);
  const COUNT = 1800;

  const transforms = useMemo(() => {
    const dummy = new THREE.Object3D();
    const list: THREE.Matrix4[] = [];
    let seed = 24;
    const rand = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);

    for (let i = 0; i < COUNT; i++) {
      const side = i % 2 === 0 ? -1 : 1;
      const z = -2 - (i / COUNT) * 30;
      const stack = Math.floor(rand() * 26);
      dummy.position.set(
        side * (1.55 + rand() * 0.5),
        0.02 + stack * 0.042 + rand() * 0.01,
        z + (rand() - 0.5) * 0.5
      );
      dummy.rotation.set(0, side * (rand() - 0.5) * 0.16, (rand() - 0.5) * 0.02);
      dummy.scale.set(0.62 + rand() * 0.2, 1, 0.86 + rand() * 0.18);
      dummy.updateMatrix();
      list.push(dummy.matrix.clone());
    }
    return list;
  }, []);

  useEffect(() => {
    if (!walls.current) return;
    transforms.forEach((m, i) => walls.current!.setMatrixAt(i, m));
    walls.current.instanceMatrix.needsUpdate = true;
  }, [transforms]);

  // The corridor is BUILT the whole time and only becomes visible as the camera
  // enters it. Standing at the waterline in Act I, the stacks were plainly
  // visible behind the plate — a room you can see before you reach it is a set,
  // not a passage.
  useFrame(() => {
    if (group.current) group.current.visible = scroll.progress > 0.075;
  });

  return (
    <group ref={group} visible={false}>
    <instancedMesh ref={walls} args={[undefined, undefined, COUNT]} frustumCulled={false}>
      <boxGeometry args={[0.62, 0.04, 0.86]} />
      {/* Unlit and matte. These are the documents nobody checked; they are not
          supposed to look inviting. */}
      <meshStandardMaterial color={palette.documents} roughness={0.94} metalness={0.02} />
    </instancedMesh>
    </group>
  );
}

/* ── Rooms IV and V · 41,206, and the queue ────────────────────────────────
   ~150k points, NOT 1M: additive overdraw at a million is fillrate-bound on
   integrated graphics, and 150k reads identically at these camera distances.
   §11.6 says so and it is worth repeating where the number is written.

   The fall is ANALYTIC, in the vertex shader — y = y0 - ½gt² with a per-point
   delay and rest height. No GPGPU, no compute pass, no simulation state, so it
   is deterministic, scroll-scrubbable, and free to rewind. A simulation would
   make scrubbing backwards impossible, which on a scroll-driven page is not a
   detail. */

const FALL_VERT = /* glsl */ `
  attribute float aDelay;
  attribute float aRest;
  attribute float aBad;
  attribute vec3 aQueue;

  uniform float uFall;    // 0..1 across Room IV
  uniform float uQueue;   // 0..1 across Room V
  uniform float uSize;

  varying float vBad;
  varying float vHeat;

  void main() {
    float t = max(0.0, uFall * 2.6 - aDelay);
    float y = position.y - 0.5 * 9.81 * t * t;
    float settled = step(y, aRest);
    y = max(y, aRest);

    vec3 fallen = vec3(position.x, y, position.z);

    // Room V morphs the SAME buffer toward a second position: disputed records
    // snap into ranked rows at z = 0, verified records recede to z = -17 and
    // out of focus.
    vec3 p = mix(fallen, aQueue, uQueue);

    vec4 mv = modelViewMatrix * vec4(p, 1.0);
    gl_Position = projectionMatrix * mv;
    // Clamped: the naive 1/z size gave near points a 40px radius and the fall
    // read as falling bokeh rather than as records.
    gl_PointSize = clamp(uSize * (1.0 / max(0.2, -mv.z)) * 90.0, 1.0, 6.0);

    vBad = aBad;
    // Bad points run hot while falling and cool on settling.
    vHeat = aBad * (1.0 - settled) * step(0.001, t);
  }
`;

const FALL_FRAG = /* glsl */ `
  varying float vBad;
  varying float vHeat;
  uniform float uOpacity;
  uniform vec3 uCold;
  uniform vec3 uSignal;

  void main() {
    vec2 d = gl_PointCoord - 0.5;
    float r = dot(d, d);
    if (r > 0.25) discard;
    float a = smoothstep(0.25, 0.02, r);

    // Hot while FALLING, cooler once ranked. A field that stays at full signal
    // through Room V puts several thousand chromatic elements behind the queue
    // panel, and §6.8 caps signal at four per viewport — the panel is the thing
    // being read, and it has to win.
    vec3 colour = mix(uCold, uSignal, max(vBad * 0.42, vHeat));
    gl_FragColor = vec4(colour, a * uOpacity);
  }
`;

function Archive({ tier, palette }: { tier: Tier; palette: Palette }) {
  const material = useRef<THREE.ShaderMaterial>(null);
  const COUNT = tier === 'full' ? 150_000 : 34_000;

  const geometry = useMemo(() => {
    const g = new THREE.BufferGeometry();
    const position = new Float32Array(COUNT * 3);
    const queue = new Float32Array(COUNT * 3);
    const delay = new Float32Array(COUNT);
    const rest = new Float32Array(COUNT);
    const bad = new Float32Array(COUNT);

    // 41,206 of 1.2M is 3.43%. The proportion of hot points is that ratio, not
    // a number chosen because it looked right — the count on screen is the
    // claim, so the claim has to be what is drawn.
    const BAD_RATIO = 41206 / 1200000;

    let seed = 7;
    const rand = () => ((seed = (seed * 48271) % 2147483647) / 2147483647);

    const side = Math.ceil(Math.sqrt(COUNT));
    for (let i = 0; i < COUNT; i++) {
      const gx = (i % side) / side - 0.5;
      const gz = Math.floor(i / side) / side - 0.5;
      const isBad = rand() < BAD_RATIO;

      position[i * 3] = gx * 44;
      position[i * 3 + 1] = 16 + rand() * 26;
      position[i * 3 + 2] = -64 + gz * 44;

      delay[i] = rand() * 1.5;
      rest[i] = -0.4 + rand() * 0.12;
      bad[i] = isBad ? 1 : 0;

      if (isBad) {
        // Ranked rows at z = 0 relative to the room: a queue, not a cloud.
        const row = Math.floor(rand() * 26);
        queue[i * 3] = -9 + rand() * 18;
        queue[i * 3 + 1] = 0.25 + row * 0.16;
        queue[i * 3 + 2] = -62;
      } else {
        // Verified records recede and drop out of focus.
        queue[i * 3] = position[i * 3] * 1.35;
        queue[i * 3 + 1] = rest[i];
        queue[i * 3 + 2] = -62 - 17;
      }
    }

    g.setAttribute('position', new THREE.BufferAttribute(position, 3));
    g.setAttribute('aQueue', new THREE.BufferAttribute(queue, 3));
    g.setAttribute('aDelay', new THREE.BufferAttribute(delay, 1));
    g.setAttribute('aRest', new THREE.BufferAttribute(rest, 1));
    g.setAttribute('aBad', new THREE.BufferAttribute(bad, 1));
    g.boundingSphere = new THREE.Sphere(new THREE.Vector3(0, 0, -64), 90);
    return g;
  }, [COUNT]);

  useEffect(() => () => geometry.dispose(), [geometry]);

  useFrame(() => {
    if (!material.current) return;
    const t = scroll.progress;
    material.current.uniforms.uFall.value = ease(span(t, 0.56, 0.86));
    material.current.uniforms.uQueue.value = ease(span(t, 0.86, 1.0));
    // The archive recedes as the product resolves. It is the ground the queue
    // sits on by Act V, not the subject.
    const queue = ease(span(t, 0.86, 1.0));
    material.current.uniforms.uOpacity.value = ease(span(t, 0.5, 0.6)) * (1 - 0.62 * queue);
  });

  return (
    <points geometry={geometry} frustumCulled={false}>
      <shaderMaterial
        ref={material}
        vertexShader={FALL_VERT}
        fragmentShader={FALL_FRAG}
        transparent
        depthWrite={false}
        blending={palette.additive ? THREE.AdditiveBlending : THREE.MultiplyBlending}
        uniforms={useMemo(
          () => ({
            uFall: { value: 0 },
            uQueue: { value: 0 },
            uOpacity: { value: 0 },
            uSize: { value: 1.5 },
            uCold: { value: new THREE.Color(palette.pointCold) },
            uSignal: { value: new THREE.Color('#c42b38') },
          }),
          [palette]
        )}
      />
    </points>
  );
}

/* ── The rig ───────────────────────────────────────────────────────────── */

/* ── The environment ───────────────────────────────────────────────────────
   A metal without an environment to reflect renders BLACK. `metalness: 0.62`
   and no envMap is why the anodized plate came out as a featureless dark slab
   on the light table: a metallic surface has almost no diffuse term, so with
   nothing around it there is nothing for it to be.

   `RoomEnvironment` is procedural and ships inside three, so this costs no
   network request and no HDR file — which matters, because §5.3's no-CDN law
   is about the critical path and an environment map is on it. The room is
   tinted to the palette so the plate picks up the light table's bounce in one
   theme and the vault's cold fill in the other. */
function Environment({ palette }: { palette: Palette }) {
  const { gl, scene } = useThree();
  useEffect(() => {
    const pmrem = new THREE.PMREMGenerator(gl);
    const room = new RoomEnvironment();
    const target = pmrem.fromScene(room, 0.04);
    scene.environment = target.texture;
    // RoomEnvironment is a BRIGHT studio box. At full intensity on the light
    // table it flattened the whole scene into a grey gradient — the plate, the
    // water and the fog all lit to the same value, which is the opposite of a
    // raking key. Enough to make the metal read, not enough to be the light.
    scene.environmentIntensity = palette.envIntensity;
    return () => {
      target.dispose();
      pmrem.dispose();
      room.dispose?.();
      scene.environment = null;
    };
  }, [gl, scene, palette]);
  return null;
}

function Rig({ tier, palette }: { tier: Tier; palette: Palette }) {
  const target = useMemo(() => new THREE.Vector3(), []);
  const look = useMemo(() => new THREE.Vector3(0, -0.42, 0), []);
  const fog = useMemo(() => new THREE.FogExp2(palette.fog, palette.fogBase), [palette]);
  const { scene, gl } = useThree();

  useEffect(() => {
    scene.fog = fog;
    scene.background = new THREE.Color(palette.ground);
    gl.setClearColor(palette.ground, 1);
    return () => void (scene.fog = null);
  }, [scene, gl, fog, palette]);

  useFrame((state, delta) => {
    const t = scroll.progress;
    const wanted = sample(t);
    const dt = frames(delta);
    const cam = state.camera as THREE.PerspectiveCamera;

    target.set(wanted.pos[0], wanted.pos[1], wanted.pos[2]);

    // A little pointer parallax, damped, and only in the first two rooms —
    // beyond that the camera has somewhere to be and a wandering frame reads
    // as drift rather than as presence.
    const parallax = 1 - ease(span(t, 0.18, 0.34));
    target.x += state.pointer.x * 0.28 * parallax;
    target.y += state.pointer.y * 0.14 * parallax;

    // DAMPED, never assigned (F-03 / §10.7). Scroll sets where the camera
    // should be; the camera decides how fast it gets there.
    cam.position.x = damp(cam.position.x, target.x, 0.10, dt);
    cam.position.y = damp(cam.position.y, target.y, 0.10, dt);
    cam.position.z = damp(cam.position.z, target.z, 0.12, dt);

    look.x = damp(look.x, wanted.look[0], 0.12, dt);
    look.y = damp(look.y, wanted.look[1], 0.12, dt);
    look.z = damp(look.z, wanted.look[2], 0.12, dt);
    cam.lookAt(look);

    const fovNow = damp(cam.fov, wanted.fov, 0.10, dt);
    if (Math.abs(fovNow - cam.fov) > 0.001) {
      cam.fov = fovNow;
      cam.updateProjectionMatrix();
    }

    // Fog density 0.028 -> 0.055 through the compression, then clearing as the
    // lights come up in Room V.
    // 0.028 -> 0.055 through the compression (§11.4), then clearing as the
    // lights come up in Room V. The light table starts at 0.010 bone and moves
    // by the same proportion, so the passage narrows in both rooms.
    const climb = palette.fogBase === 0.028 ? 0.027 : 0.010;
    fog.density =
      palette.fogBase +
      climb * ease(span(t, 0.14, 0.30)) -
      climb * 0.74 * ease(span(t, 0.84, 1.0));
  });

  return (
    <>
      {/* L-5 — every light has a source you could point at. One raking key,
          out of frame, upper-left. One cold hemispheric fill at 12%. Nothing
          else: no rim light without a lamp, no ambient prettiness. */}
      <directionalLight
        color={palette.keyColour}
        intensity={palette.keyIntensity}
        position={palette.keyPosition}
      />
      <hemisphereLight args={[palette.fillSky, palette.fillGround, palette.fillIntensity]} />
      <Environment palette={palette} />
      <RoomI tier={tier} palette={palette} />
      <RoomII palette={palette} />
      <Archive tier={tier} palette={palette} />
    </>
  );
}

export default function Scene({ tier }: { tier: Tier }) {
  const palette = usePalette();
  const dpr: [number, number] = tier === 'full' ? [1, 2] : [1, 1.5];

  // The canvas layer is OUR div, not a className handed to <Canvas>. R3F puts
  // the class somewhere inside its own wrapper tree, and the wrapper inherits
  // its size from the parent — so with `#root` at auto height the whole thing
  // collapsed to 150px and rendered a letterbox. Owning the positioned element
  // means the layout cannot depend on where a library chooses to hang a class.
  return (
    <div className="gl-layer">
    <Canvas
      dpr={dpr}
      gl={{ antialias: tier === 'full', powerPreference: 'high-performance' }}
      camera={{ position: [0, 1.05, 6.6], fov: 48, near: 0.1, far: 140 }}
      // §10.4 — under reduced motion the scene renders ON DEMAND, one frame per
      // scroll change, instead of running a loop. Not "animation disabled": the
      // procession still moves when the reader moves, it simply never moves by
      // itself.
      frameloop={tier === 'lite' ? 'demand' : 'always'}
      onCreated={({ gl, scene }) => {
        gl.setClearColor(palette.ground, 1);
        scene.background = new THREE.Color(palette.ground);
      }}
    >
      <Rig tier={tier} palette={palette} />
    </Canvas>
    </div>
  );
}
