<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch, watchEffect } from 'vue'
import {
  ArrowDownUp, Layers, LocateFixed, Map, Maximize, Minimize, Minus, Pause, Play, Plus, RotateCcw,
} from '@lucide/vue'
import {
  fitOverview, fitRouteView, floorFootprint, floorRoute, hasCoordinates, previewFrame,
  previewTimeline, roomEntrance, routeFloors,
} from '../route-map'

const props = defineProps({
  route: { type: Object, required: true },
  labels: { type: Object, required: true },
  language: { type: String, required: true },
})

const floorId = ref(null)
const show3D = ref(true)
const zoom = ref(1)
const offset = ref([0, 0])
const framing = ref('route')
const diagram = ref(null)
const viewport = ref(null)
const sceneCanvas = ref(null)
const sceneReady = ref(false)
const size = ref({ width: 640, height: 420 })
const elapsed = ref(0)
const playing = ref(false)
const assetFailed = ref(false)
const canFullscreen = ref(false)
const fullscreen = ref(false)
const fullscreenError = ref(false)
let observer
let raf
let drag
let scene
let displayedPlan
let displayedDestination
let disposed = false

const floors = computed(() => routeFloors(props.route))
const floor = computed(() => floors.value.find(({ id }) => id === floorId.value))
const drawing = computed(() => floorRoute(props.route, floorId.value))
const plan = computed(() => floor.value?.plan)
const is3D = computed(() => Boolean(plan.value && show3D.value && sceneReady.value))
const flatRooms = computed(() => plan.value?.rooms.map((room) => ({
  ...room, entrance: roomEntrance(room, plan.value.corridors),
})))
const asset = computed(() => assetFailed.value ? null : floor.value?.asset)
const mapWidth = computed(() => plan.value?.width ?? 1000)
const mapHeight = computed(() => plan.value?.height ?? 1000)
const hasFloorMap = computed(() => Boolean(plan.value || asset.value))
const floorBounds = computed(() => plan.value ? floorFootprint(plan.value) : {
  x: 0, y: 0, width: mapWidth.value, height: mapHeight.value,
})
const framingWholeFloor = computed(() => hasFloorMap.value && (
  framing.value === 'overview' || !drawing.value.points.length
))
const timeline = computed(() => previewTimeline(props.route))
const duration = computed(() => timeline.value.at(-1)?.ends ?? 0)
const frame = computed(() => previewFrame(timeline.value, elapsed.value))
const finished = computed(() => duration.value > 0 && elapsed.value >= duration.value)

const colors = {
  origin: '#2466d8', arrival: '#cf4239', transfer: '#5843a5',
}
const landmarkLabels = computed(() => props.labels.landmarks)
const walker = computed(() => frame.value ?? { point: props.route.origin, walking: false })
const showWalker = computed(() => !finished.value && walker.value.point.floor_id === floorId.value
  && hasCoordinates(walker.value.point))
const markers = computed(() => {
  const onFloor = (point) => point.floor_id === floorId.value && hasCoordinates(point)
  const { origin, arrival, destination } = props.route
  const points = drawing.value.transfers.map(({ point, step, leaving }) => ({
    point, kind: 'transfer', text: leaving ? props.labels.transferTo(step.kind, step.end.floor) : props.labels.landmark(step.kind),
  }))
  if (onFloor(origin) && (!onFloor(arrival) || origin.x !== arrival.x || origin.y !== arrival.y)) {
    points.push({ point: origin, kind: 'origin', text: props.labels.kioskAt(origin.floor) })
  }
  if (onFloor(arrival)) {
    points.push({ point: arrival, kind: 'arrival', text: destination.code })
  }
  return points
})

function mapPoint(point) {
  return [point.x * mapWidth.value, point.y * mapHeight.value]
}

const frameBounds = computed(() => {
  if (framingWholeFloor.value) return fitOverview(size.value, floorBounds.value, Boolean(plan.value))
  const points = drawing.value.points.map(mapPoint)
  return fitRouteView(size.value, points.length ? points : [[0, 0]], hasFloorMap.value)
})

const camera = computed(() => {
  const { width, height } = size.value
  const { centerX, centerY, scaleX: baseScaleX, scaleY: baseScaleY } = frameBounds.value
  const scaleX = baseScaleX * zoom.value
  const scaleY = baseScaleY * zoom.value
  return {
    scaleX,
    scaleY,
    x: width / 2 - centerX * scaleX + offset.value[0],
    y: height / 2 - centerY * scaleY + offset.value[1],
  }
})

function screen(x, y) {
  return [camera.value.x + x * camera.value.scaleX, camera.value.y + y * camera.value.scaleY]
}

const position = (point) => screen(...mapPoint(point))
const at = (x, y) => `translate(${x} ${y})`

const walkerPose = computed(() => {
  if (!showWalker.value) return null
  const { point, step } = walker.value
  const [x, y] = mapPoint(point)
  let facing = 0
  if (step && walker.value.walking) {
    const [startX, startY] = position(step.start)
    const [endX, endY] = position(step.end)
    facing = Math.atan2(endX - startX, endY - startY)
  }
  const animate = playing.value && walker.value.walking
    && !window.matchMedia('(prefers-reduced-motion: reduce)').matches
  return { x, y, facing, stride: animate ? Math.sin(elapsed.value / 100) * 0.58 : 0 }
})

const routePath = computed(() => drawing.value.segments
  .map(({ start, end }) => `M ${mapPoint(start).join(' ')} L ${mapPoint(end).join(' ')}`).join(' '))

const arrows = computed(() => drawing.value.segments.flatMap(({ start, end }) => {
  const [sx, sy] = position(start)
  const [ex, ey] = position(end)
  const dx = ex - sx
  const dy = ey - sy
  const length = Math.hypot(dx, dy)
  if (length < 42) return []
  return [0.5, ...(length > 150 ? [0.26, 0.74] : [])].map((t) => (
    `${at(sx + dx * t, sy + dy * t)} rotate(${Math.atan2(dy, dx) * 180 / Math.PI})`
  ))
}))

const landmarks = computed(() => (plan.value?.landmarks ?? []).filter((landmark) => (
  !markers.value.some(({ point }) => {
    const [x, y] = mapPoint(point)
    return Math.hypot(x - landmark.x, y - landmark.y) < 12
  })
)))

function zoneName(zone, target) {
  const name = props.language === 'en' ? zone.name_en : zone.name
  const available = target ? size.value.width - 48 : zone.width * camera.value.scaleX - 10
  const limit = Math.max(12, Math.min(36, Math.floor(available / 6.7)))
  return name.length > limit ? `${name.slice(0, limit - 1).trimEnd()}…` : name
}

function overlaps(a, b) {
  return a.x < b.x + b.width + 6 && a.x + a.width + 6 > b.x
    && a.y < b.y + b.height + 6 && a.y + a.height + 6 > b.y
}

const markedPoints = computed(() => {
  const occupied = markers.value.map(({ point }) => {
    const [x, y] = position(point)
    return { x: x - 11, y: y - 10, width: 22, height: 20 }
  })
  return markers.value.map((marker) => {
    const [x, y] = position(marker.point)
    const width = marker.text.length * 6.7 + 16
    const height = 24
    const right = { x: x + 19, y: y - 12, width, height }
    const candidates = [
      right,
      { ...right, x: x - 19 - width },
      { ...right, x: x - width / 2, y: y + 17 },
      { ...right, x: x - width / 2, y: y - 55 },
    ]
    const label = candidates.find((candidate) => (
      candidate.x >= 4 && candidate.x + width <= size.value.width - 4
      && candidate.y >= 4 && candidate.y + height <= size.value.height - 4
      && !occupied.some((other) => overlaps(candidate, other))
    )) ?? right
    occupied.push(label)
    return { ...marker, label }
  })
})

const zoneBadges = computed(() => {
  const destination = props.route.destination.code.split('-').slice(0, 2).join('-')
  const occupied = markedPoints.value.flatMap((marker) => {
    const [x, y] = position(marker.point)
    return [marker.label, { x: x - 13, y: y - 30, width: 26, height: 44 }]
  })
  for (const landmark of landmarks.value) {
    const [x, y] = screen(landmark.x, landmark.y)
    occupied.push({ x: x - 12, y: y - 9, width: 24, height: 18 })
  }
  const visible = []
  const zones = [...(plan.value?.zones ?? [])].sort((a, b) => Number(b.code === destination) - Number(a.code === destination))
  for (const zone of zones) {
    const target = zone.code === destination
    const text = zoneName(zone, target)
    const width = text.length * 6.7 + 16
    const height = 24
    const anchors = [zone.y + 4]
    if (target) anchors.push(zone.y + zone.height - 8)
    const label = anchors.map((anchor) => {
      const [centerX, y] = screen(zone.x + zone.width / 2, anchor)
      return { x: centerX - width / 2, y: y - height / 2, width, height }
    }).find((candidate) => candidate.x >= 8 && candidate.x + width <= size.value.width - 12
      && candidate.y >= 38 && candidate.y + height <= size.value.height - 10
      && !occupied.some((other) => overlaps(candidate, other)))
    if (!label) continue
    occupied.push(label)
    visible.push({ code: zone.code, text, label, target })
  }
  return visible
})

function recenter() {
  zoom.value = 1
  offset.value = [0, 0]
}

function chooseFraming(value) {
  framing.value = value
  recenter()
}

function syncFullscreen() {
  fullscreen.value = document.fullscreenElement === diagram.value
}

async function toggleFullscreen() {
  fullscreenError.value = false
  try {
    if (fullscreen.value) await document.exitFullscreen()
    else await diagram.value.requestFullscreen()
  } catch {
    fullscreenError.value = true
  }
}

watch(() => props.route, (route) => {
  stop()
  elapsed.value = 0
  floorId.value = route.origin.floor_id
  assetFailed.value = false
  chooseFraming('route')
}, { immediate: true })

watch(floorId, () => {
  recenter()
  assetFailed.value = false
})

function chooseFloor(id) {
  stop()
  floorId.value = id
}

function changeZoom(factor) {
  const next = Math.min(3, Math.max(0.45, zoom.value * factor))
  const ratio = next / zoom.value
  offset.value = offset.value.map((value) => value * ratio)
  zoom.value = next
}

function startDrag(event) {
  if (!event.isPrimary || event.button !== 0) return
  drag = { id: event.pointerId, x: event.clientX, y: event.clientY, offset: offset.value }
  event.currentTarget.setPointerCapture(event.pointerId)
}

function moveDrag(event) {
  if (drag?.id !== event.pointerId) return
  offset.value = [drag.offset[0] + event.clientX - drag.x, drag.offset[1] + event.clientY - drag.y]
}

function endDrag(event) {
  if (drag?.id === event.pointerId) drag = null
}

function stop() {
  playing.value = false
  if (raf !== undefined) cancelAnimationFrame(raf)
  raf = undefined
}

function seek(time) {
  elapsed.value = Math.min(duration.value, Math.max(0, time))
  const id = frame.value?.point.floor_id
  if (id != null) floorId.value = id
}

function togglePlayback() {
  if (playing.value) {
    stop()
    return
  }
  if (!duration.value) return
  seek(finished.value ? 0 : elapsed.value)
  playing.value = true
  let previous
  function tick(now) {
    if (previous !== undefined) seek(elapsed.value + Math.min(now - previous, 100))
    previous = now
    if (finished.value) stop()
    else raf = requestAnimationFrame(tick)
  }
  raf = requestAnimationFrame(tick)
}

onMounted(() => {
  canFullscreen.value = Boolean(document.fullscreenEnabled && diagram.value.requestFullscreen)
  document.addEventListener('fullscreenchange', syncFullscreen)
  observer = new ResizeObserver(([{ contentRect }]) => {
    if (contentRect.width > 0 && contentRect.height > 0) size.value = { width: contentRect.width, height: contentRect.height }
  })
  observer.observe(viewport.value)
  watch(() => Boolean(plan.value), async (hasPlan) => {
    if (!hasPlan || scene || disposed) return
    try {
      const { createFloorScene } = await import('../floor-scene')
      if (disposed || scene) return
      scene = createFloorScene(sceneCanvas.value)
      sceneReady.value = Boolean(scene)
    } catch {
      sceneReady.value = false
    }
  }, { immediate: true })
})

watchEffect(() => {
  if (!is3D.value) return
  const currentPlan = plan.value
  const destination = props.route.destination.code
  if (displayedPlan !== currentPlan || displayedDestination !== destination) {
    scene.setFloor(currentPlan, destination)
    displayedPlan = currentPlan
    displayedDestination = destination
  }
  scene.draw(size.value, camera.value, walkerPose.value)
})

onBeforeUnmount(() => {
  disposed = true
  document.removeEventListener('fullscreenchange', syncFullscreen)
  observer?.disconnect()
  stop()
  scene?.dispose()
})
</script>

<template>
  <div ref="diagram" class="route-diagram">
    <div class="map-toolbar">
      <div class="floor-tabs" role="group" :aria-label="labels.mapFloors">
        <button v-for="level in floors" :key="level.id" type="button"
          :aria-pressed="floorId === level.id" @click="chooseFloor(level.id)">
          {{ labels.floor(level.label) }}
        </button>
      </div>
      <div class="map-actions">
        <button v-if="drawing.points.length" class="map-mode" type="button"
          :aria-pressed="!framingWholeFloor" @click="chooseFraming('route')">
          <LocateFixed :size="16" /> {{ labels.recenter }}
        </button>
        <button v-if="hasFloorMap" class="map-mode" type="button"
          :aria-pressed="framingWholeFloor" @click="chooseFraming('overview')">
          <Map :size="16" /> {{ labels.overview }}
        </button>
        <button v-if="plan && sceneReady" class="map-mode" type="button" :aria-label="labels.map3D" :aria-pressed="is3D"
          @click="show3D = !show3D">
          <Layers :size="16" /> {{ is3D ? '3D' : '2D' }}
        </button>
        <button v-if="canFullscreen && (drawing.points.length || hasFloorMap)" class="map-mode" type="button"
          :aria-label="fullscreen ? labels.exitFullscreen : labels.fullscreen"
          :title="fullscreen ? labels.exitFullscreen : labels.fullscreen" @click="toggleFullscreen">
          <Minimize v-if="fullscreen" :size="16" />
          <Maximize v-else :size="16" />
          <span class="fullscreen-text">{{ fullscreen ? labels.exitFullscreen : labels.fullscreen }}</span>
        </button>
      </div>
    </div>

    <p v-if="fullscreenError" class="map-note" role="status">{{ labels.fullscreenError }}</p>
    <div ref="viewport" class="map-viewport">
      <canvas v-show="is3D" ref="sceneCanvas" class="map-scene" aria-hidden="true"
        @webglcontextlost="sceneReady = false" @webglcontextrestored="sceneReady = Boolean(scene)" />
      <template v-if="drawing.points.length || plan || asset">
        <svg class="indoor-map" :viewBox="`0 0 ${size.width} ${size.height}`" role="img"
          :aria-label="labels.mapLabel(floor?.label)"
          @pointerdown="startDrag" @pointermove="moveDrag"
          @lostpointercapture="endDrag" @pointercancel="endDrag" @pointerup="endDrag">
          <g :transform="`translate(${camera.x} ${camera.y}) scale(${camera.scaleX} ${camera.scaleY})`">
            <g v-if="!is3D">
              <rect v-if="plan" class="map-floor" v-bind="floorBounds" rx="8" />
              <image v-else-if="asset" :href="asset" :width="mapWidth" :height="mapHeight"
                preserveAspectRatio="none" @error="assetFailed = true" />
              <template v-if="plan">
                <rect v-for="zone in plan.zones" :key="zone.code" v-bind="{
                    x: zone.x, y: zone.y, width: zone.width, height: zone.height,
                  }" rx="10" class="map-zone"
                  :class="{ 'map-zone-target': route.destination.code.startsWith(zone.code + '-') || route.destination.code === zone.code }" />
                <line v-for="([x1, y1, x2, y2], index) in plan.corridors" :key="index"
                  v-bind="{ x1, y1, x2, y2 }" class="map-corridor"
                    :stroke-width="x1 === x2 ? 56 : 33" />
              </template>
            </g>
            <g v-if="plan && !is3D">
              <g v-for="room in flatRooms" :key="room.code">
                <rect :x="room.x" :y="room.y" :width="room.width" :height="room.height"
                  rx="2" class="map-room" :class="{ 'map-room-target': room.code === route.destination.code }" />
                <circle :cx="room.entrance.x" :cy="room.entrance.y" r="3" fill="#fff" />
              </g>
            </g>
            <g fill="none" stroke-linecap="round" stroke-linejoin="round">
              <path :d="routePath" stroke="white" stroke-width="11" vector-effect="non-scaling-stroke" />
              <path :d="routePath" stroke="#2466d8" stroke-width="7" vector-effect="non-scaling-stroke" />
            </g>
          </g>

          <g v-for="badge in zoneBadges" :key="badge.code"
            :transform="at(badge.label.x, badge.label.y)" :class="{ 'zone-badge-target': badge.target }">
            <rect :width="badge.label.width" :height="badge.label.height" rx="6" class="zone-badge" />
            <text x="8" y="16" class="zone-label">{{ badge.text }}</text>
          </g>
          <path v-for="arrow in arrows" :key="arrow" :transform="arrow" d="M -3 -2.5 L 0 0 L -3 2.5"
            fill="none" stroke="white" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" />
          <g v-for="landmark in landmarks" :key="landmark.code"
            :transform="at(...screen(landmark.x, landmark.y))">
            <title>{{ labels.landmark(landmark.kind) }}</title>
            <rect x="-12" y="-8" width="24" height="16" rx="5" class="map-landmark" />
            <text y="3.2" text-anchor="middle" class="landmark-label">{{ landmarkLabels[landmark.kind] }}</text>
          </g>

          <g v-for="(marker, index) in markedPoints" :key="index">
            <g :transform="at(...position(marker.point))" :fill="colors[marker.kind]" stroke="white" stroke-width="2.5">
              <path v-if="marker.kind === 'arrival'" d="M 0 1 C -2 -3 -11 -9 -11 -17 A 11 11 0 0 1 11 -17 C 11 -9 2 -3 0 1 Z" />
              <circle v-else-if="marker.kind === 'origin' && is3D && showWalker && elapsed === 0"
                r="9" fill="none" :stroke="colors.origin" stroke-width="1.6" />
              <circle v-else r="9" />
              <circle v-if="marker.kind === 'arrival'" cy="-17" r="3.1" fill="white" stroke="none" />
              <path v-else-if="marker.kind === 'transfer'" d="M -4 2 V -4 L -6 -2 M -4 -4 L -2 -2 M 4 -2 V 4 L 2 2 M 4 4 L 6 2"
                fill="none" stroke-width="1.2" stroke-linecap="round" />
              <circle v-else-if="!is3D || !showWalker || elapsed > 0" r="3" fill="white" stroke="none" />
            </g>
            <g :transform="at(marker.label.x, marker.label.y)">
              <rect :width="marker.label.width" :height="marker.label.height" rx="6" class="map-marker-label" />
              <text x="8" y="16" class="marker-label" :fill="colors[marker.kind]">{{ marker.text }}</text>
            </g>
          </g>

          <g v-if="showWalker && !is3D" :transform="at(...position(walker.point))" aria-hidden="true">
            <ellipse cy="0" rx="12" ry="5" fill="#153666" opacity=".24" />
            <g class="map-walker" :class="{ 'is-walking': playing && walker.walking }" transform="translate(0 -5)">
              <path class="walker-body" d="M0 -21 V-10" />
              <path class="walker-leg walker-left" d="M0 -10 L-5 -5 L-6 0" />
              <path class="walker-leg walker-right" d="M0 -10 L5 -5 L6 0" />
              <path class="walker-arm walker-left" d="M0 -19 L-6 -15 L-8 -16" />
              <path class="walker-arm walker-right" d="M0 -19 L6 -16 L8 -19" />
              <circle cy="-27" r="5.5" fill="#f8a43a" stroke="white" stroke-width="1.6" />
            </g>
          </g>
        </svg>

        <span class="map-badge">{{ plan ? labels.demoMap : asset ? labels.indoor : labels.lineOnly }}</span>
        <div class="map-controls" role="group" :aria-label="labels.mapControls">
          <button type="button" :aria-label="labels.zoomIn" :disabled="zoom >= 3" @click="changeZoom(1.25)">
            <Plus :size="19" />
          </button>
          <button type="button" :aria-label="labels.zoomOut" :disabled="zoom <= 0.45" @click="changeZoom(0.8)">
            <Minus :size="19" />
          </button>
        </div>
      </template>
      <p v-if="!drawing.points.length" class="map-empty">{{ labels.noCoordinates }}</p>
    </div>

    <div v-if="duration" class="map-playback">
      <button type="button" class="map-play" @click="togglePlayback">
        <Pause v-if="playing" :size="17" />
        <RotateCcw v-else-if="finished" :size="17" />
        <Play v-else :size="17" />
        {{ playing ? labels.pauseGuide : finished ? labels.replayGuide : elapsed ? labels.resumeGuide : labels.playGuide }}
      </button>
      <input type="range" min="0" :max="duration" :value="elapsed" :aria-label="labels.guideProgress"
        @input="stop(); seek(Number($event.target.value))" />
    </div>
    <p v-if="elapsed > 0" class="map-guide-instruction" aria-live="polite">
      {{ finished ? labels.end : frame?.step.instruction }}
    </p>

    <div v-if="drawing.points.length" class="diagram-key">
      <span><i class="origin-key"></i>{{ labels.start }}</span>
      <span><i class="path-key"></i>{{ labels.path }}</span>
      <span><i class="arrival-key"></i>{{ labels.end }}</span>
      <span v-if="floors.length > 1"><ArrowDownUp :size="13" />{{ labels.changeFloor }}</span>
    </div>
    <p class="map-note">{{ plan ? labels.mapNote : labels.guideNote }}</p>
  </div>
</template>
