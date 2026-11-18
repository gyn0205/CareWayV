<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch, watchEffect } from 'vue'
import {
  Layers, LocateFixed, Map, Maximize, Minimize, Minus, Pause, Play, Plus, RotateCcw,
} from '@lucide/vue'
import {
  fitOverview, fitRouteView, floorFootprint, floorRoute, hasCoordinates, headingDegrees, insidePolygon, isTransfer,
  previewFrame, previewTimeline, roomEntrance, routeFloors, stairTreads, sunroomShade, wrapLabel, zoneCode,
} from '../route-map'

const props = defineProps({
  // Bản đồ màn hình chờ: vị trí kiosk + mặt bằng mọi tầng (có trước khi khách hỏi).
  kioskMap: Object,
  // Tuyến hiện tại; null khi đang chờ hoặc đang hỏi lại.
  route: Object,
  // Các điểm đến ứng viên khi kiosk đang hỏi lại → tô viền đỏ nét đứt trên bản đồ.
  candidates: { type: Array, default: () => [] },
  labels: { type: Object, required: true },
  language: { type: String, required: true },
  // Khoá danh mục khu khi đang tìm đường / đang thu âm.
  disabled: Boolean,
})
const emit = defineEmits(['select', 'progress'])

const floorId = ref(null)
const show3D = ref(false)
const zoom = ref(1)
const offset = ref([0, 0])
const framing = ref('overview')
const diagram = ref(null)
const viewport = ref(null)
const sceneCanvas = ref(null)
const sceneReady = ref(false)
const sceneFailed = ref(false)
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

const NO_DRAWING = { points: [], segments: [], transfers: [] }

// Danh sách tầng: lấy từ bản đồ kiosk (đủ mọi tầng); thiếu thì lấy các tầng tuyến đi qua.
const floors = computed(() => {
  if (!props.kioskMap) return props.route ? routeFloors(props.route) : []
  const plans = [...(props.route?.floor_plans ?? []), ...props.kioskMap.floor_plans]
  return props.kioskMap.floors.map(({ floor_id: id, floor, map_asset_url: asset }) => ({
    id, label: floor, asset, plan: plans.find((plan) => plan.floor_id === id),
  }))
})
const origin = computed(() => props.route?.origin ?? props.kioskMap?.origin)
const homeFloorId = computed(() => origin.value?.floor_id)
const floor = computed(() => floors.value.find(({ id }) => id === floorId.value))
const drawing = computed(() => props.route ? floorRoute(props.route, floorId.value) : NO_DRAWING)
const plan = computed(() => floor.value?.plan)
const is3D = computed(() => Boolean(plan.value && show3D.value && sceneReady.value))
// Mã khu của điểm đến, tra theo phòng của mọi tầng, ví dụ phòng "3-167" → khu "3-10".
const allRooms = computed(() => floors.value.flatMap(({ plan: floorPlan }) => floorPlan?.rooms ?? []))
const targetZone = computed(() => props.route ? zoneCode(props.route.destination.code, allRooms.value) : null)
const candidateZones = computed(() => new Set(props.candidates.map(({ code }) => zoneCode(code, allRooms.value))))
const highlighting = computed(() => Boolean(targetZone.value || candidateZones.value.size))
// Mặt bằng mới có đường viền khu → chỉ vẽ phòng của khu đích cho gọn như bảng thật.
const detailedPlan = computed(() => Boolean(plan.value?.zones.some((zone) => zone.outline?.length)))
const flatRooms = computed(() => (plan.value?.rooms ?? [])
  .filter((room) => !detailedPlan.value || room.zone === targetZone.value)
  .map((room) => ({ ...room, entrance: roomEntrance(room, plan.value.corridors) })))
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
const timeline = computed(() => props.route ? previewTimeline(props.route) : [])
const duration = computed(() => timeline.value.at(-1)?.ends ?? 0)
const frame = computed(() => previewFrame(timeline.value, elapsed.value))
const finished = computed(() => duration.value > 0 && elapsed.value >= duration.value)
// Đang phát (hoặc tạm dừng giữa chừng) → tuyến phía trước mờ, đoạn đã đi đậm như prototype.
const inProgress = computed(() => playing.value || (elapsed.value > 0 && !finished.value))
// Tầng thuộc tuyến nhưng không có tọa độ → báo cho khách xem chỉ dẫn chữ.
const routeFloorIds = computed(() => new Set(props.route ? routeFloors(props.route).map(({ id }) => id) : []))

// Bước đang đi (để bảng bên phải tô sáng): -1 khi chưa phát, bước cuối khi đã tới nơi.
const activeStep = computed(() => {
  if (!props.route || !timeline.value.length) return -1
  if (finished.value) return props.route.steps.length - 1
  if (!inProgress.value) return -1
  return props.route.steps.indexOf(frame.value.step)
})
watch([activeStep, finished], ([step, done]) => emit('progress', step, done), { immediate: true })

const walker = computed(() => frame.value ?? { point: origin.value, walking: false })
const showWalker = computed(() => Boolean(walker.value.point) && !finished.value
  && walker.value.point.floor_id === floorId.value && hasCoordinates(walker.value.point))
const onFloor = (point) => point.floor_id === floorId.value && hasCoordinates(point)
const markers = computed(() => {
  const { arrival } = props.route ?? {}
  const points = drawing.value.transfers.map(({ point, step }) => ({
    point, kind: 'transfer', tag: `⇅ ${props.labels.floor(step.start.floor)} → ${props.labels.floor(step.end.floor)}`,
  }))
  const home = origin.value
  if (home && onFloor(home) && (!arrival || !onFloor(arrival) || home.x !== arrival.x || home.y !== arrival.y)) {
    // Chấm xanh "Bạn đang ở đây" như prototype.
    points.unshift({ point: home, kind: 'origin', tag: props.labels.youAreHere })
  }
  if (arrival && onFloor(arrival)) points.push({ point: arrival, kind: 'arrival' })
  return points
})

function mapPoint(point) {
  return [point.x * mapWidth.value, point.y * mapHeight.value]
}

const frameBounds = computed(() => {
  // Giữ tỉ lệ thật của mặt bằng (không kéo giãn) để hình khu giống bảng treo tường.
  if (framingWholeFloor.value) return fitOverview(size.value, floorBounds.value, !detailedPlan.value && Boolean(plan.value))
  const points = drawing.value.points.map(mapPoint)
  return fitRouteView(size.value, points.length ? points : [[0, 0]], hasFloorMap.value,
    detailedPlan.value ? [640, 440] : undefined)
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
const polygon = (points) => points.map((point) => point.join(',')).join(' ')
const pathOf = (segments) => segments
  .map(({ start, end }) => `M ${mapPoint(start).join(' ')} L ${mapPoint(end).join(' ')}`).join(' ')

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

// Hướng mũi tên của người dẫn đường 2D: chỉ hiện khi đang đi trên một đoạn tuyến.
const walkerHeading = computed(() => {
  const { step, walking } = walker.value
  if (!showWalker.value || !walking || !step) return null
  return headingDegrees(position(step.start), position(step.end))
})

const routePath = computed(() => pathOf(drawing.value.segments))
// Phần tuyến đã đi qua trên tầng đang xem (đoạn hiện tại vẽ tới vị trí người dẫn đường).
const progressPath = computed(() => {
  if (!inProgress.value) return ''
  return pathOf(timeline.value.flatMap(({ step, begins, ends }) => {
    if (begins >= elapsed.value || isTransfer(step)) return []
    const end = ends <= elapsed.value ? step.end : frame.value.point
    return onFloor(step.start) && onFloor(end) ? [{ start: step.start, end }] : []
  }))
})

const arrows = computed(() => inProgress.value ? [] : drawing.value.segments.flatMap(({ start, end }) => {
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

// Bảng sơ đồ tầng (vạch tối sát mép giếng sảnh).
const boards = computed(() => (plan.value?.blocks ?? []).filter(({ kind }) => kind === 'board'))

// Mốc trong lõi (thang máy, WC, thang bộ); ẩn mốc trùng với điểm đánh dấu tuyến.
// Kiosk đứng ngay cạnh bảng sơ đồ nên không vẽ thêm ô "i" khi mặt bằng đã có bảng.
const landmarks = computed(() => (plan.value?.landmarks ?? []).filter((landmark) => (
  !(landmark.kind === 'kiosk' && boards.value.length)
  && !markers.value.some(({ point }) => {
    const [x, y] = mapPoint(point)
    return Math.hypot(x - landmark.x, y - landmark.y) < 12
  })
)))

// Nhãn nổi cạnh chấm "Bạn đang ở đây" và điểm chuyển tầng (prototype); tràn mép phải thì đặt bên trái.
const TAG_CHAR = 7.4
// Đang mô phỏng thì ẩn nhãn "Bạn đang ở đây" để người dẫn đường không đè lên chữ.
const tags = computed(() => markers.value.filter(({ tag, kind }) => tag && !(kind === 'origin' && inProgress.value)).map((marker) => {
  const [x, y] = position(marker.point)
  const width = Math.round(marker.tag.length * TAG_CHAR + 22)
  const right = x + 20 + width <= size.value.width - 6
  return { kind: marker.kind, text: marker.tag, x: right ? x + 20 : x - 20 - width, y: y - 15, width, height: 30 }
}))

function overlaps(a, b) {
  return a.x < b.x + b.width + 6 && a.x + a.width + 6 > b.x
    && a.y < b.y + b.height + 6 && a.y + a.height + 6 > b.y
}

// Nhãn khu luôn song ngữ như bảng sơ đồ thật: dòng Việt đậm, dòng Anh nghiêng nhỏ hơn.
const VI_CHAR = 7.3
const EN_CHAR = 6.1
const VI_LINE = 15
const EN_LINE = 13

// Nhãn khu kiểu bảng thật: vòng tròn số + tên khu, tránh đè lên nhau.
const zoneBadges = computed(() => {
  // Chừa chỗ cho chấm đánh dấu, nhãn nổi và mốc trong lõi.
  const occupied = markers.value.map(({ point }) => {
    const [x, y] = position(point)
    return { x: x - 14, y: y - 14, width: 28, height: 28 }
  })
  occupied.push(...tags.value)
  for (const landmark of landmarks.value) {
    const [x, y] = screen(landmark.x, landmark.y)
    occupied.push({ x: x - 12, y: y - 10, width: 24, height: 20 })
  }
  const targetRoom = props.route && flatRooms.value.find((room) => room.code === props.route.destination.code)
  if (targetRoom) {
    const [x, y] = screen(targetRoom.x, targetRoom.y)
    occupied.push({ x, y, width: targetRoom.width * camera.value.scaleX, height: targetRoom.height * camera.value.scaleY })
  }
  const visible = []
  const important = (zone) => zone.code === targetZone.value || candidateZones.value.has(zone.code)
  // Khu đích/ứng viên trước, rồi khu nhỏ trước (ít chỗ đặt nhãn hơn khu lớn).
  const zones = [...(plan.value?.zones ?? [])].sort((a, b) => (
    Number(important(b)) - Number(important(a)) || a.width * a.height - b.width * b.height
  ))
  // Khu đích có vẽ phòng: ưu tiên đặt nhãn ngay dưới/trên dãy phòng để không che phòng.
  let roomsBlock
  if (detailedPlan.value && flatRooms.value.length) {
    const [left, top] = screen(Math.min(...flatRooms.value.map((room) => room.x)), Math.min(...flatRooms.value.map((room) => room.y)))
    const [right, bottom] = screen(
      Math.max(...flatRooms.value.map((room) => room.x + room.width)),
      Math.max(...flatRooms.value.map((room) => room.y + room.height)),
    )
    roomsBlock = { x: left, y: top, width: right - left, height: bottom - top }
  }
  for (const zone of zones) {
    const target = zone.code === targetZone.value
    const anchorX = zone.label_x ?? zone.x + zone.width / 2
    const anchorY = zone.label_y ?? zone.y + zone.height / 2
    // Bề ngang dành cho chữ: phần khu đối xứng quanh điểm đặt nhãn.
    const span = Math.min(zone.width, 2 * Math.min(anchorX - zone.x, zone.x + zone.width - anchorX))
    const available = target ? Math.max(span * camera.value.scaleX, 150) : span * camera.value.scaleX
    const vi = wrapLabel(zone.name, Math.floor((available - 14) / VI_CHAR))
    const en = zone.name_en ? wrapLabel(zone.name_en, Math.floor((available - 14) / EN_CHAR)) : []
    // Quầy lễ tân không có số trên bảng → vòng tròn chữ "i" (thông tin).
    const hasNumber = zone.number != null || zone.tone === 'desk'
    const shifts = [0, -0.28, 0.28, -0.4, 0.4, -0.46, 0.46]
    // Thử đủ 2 thứ tiếng → chỉ tiếng Việt → chỉ vòng số; khu đích né dãy phòng trước.
    const layouts = []
    if (vi.length) {
      if (en.length) layouts.push([vi, en])
      layouts.push([vi, []])
    }
    if (hasNumber) layouts.push([[], []])
    const avoidRooms = target && roomsBlock ? [true, false] : [false]
    let placed
    search: for (const strict of avoidRooms) {
      for (const [viLines, enLines] of layouts) {
        const width = Math.max(hasNumber ? 24 : 0, ...viLines.map((line) => line.length * VI_CHAR + 8),
          ...enLines.map((line) => line.length * EN_CHAR + 8))
        const textHeight = viLines.length * VI_LINE + enLines.length * EN_LINE
        const height = (hasNumber ? 24 : 0) + textHeight + (textHeight ? 3 : 0)
        for (const shift of shifts) {
          const planY = anchorY + zone.height * shift
          const [centerX, centerY] = screen(anchorX, planY)
          const box = { x: centerX - width / 2, y: centerY - height / 2, width, height }
          if (box.x < 6 || box.x + width > size.value.width - 6 || box.y < 6 || box.y + height > size.value.height - 6) continue
          // Nhãn phải nằm trong khu của nó (lượt đầu: cả mép trên/dưới nhãn; lượt dự phòng: tâm nhãn).
          if (zone.outline?.length) {
            const half = height / 2 / camera.value.scaleY
            const probes = strict || !target ? [planY - half, planY, planY + half] : [planY]
            if (!probes.every((y) => insidePolygon(zone.outline, anchorX, y))) continue
          }
          if (occupied.some((other) => overlaps(box, other))) continue
          if (strict && overlaps(box, roomsBlock)) continue
          placed = { box, vi: viLines, en: enLines }
          break search
        }
      }
    }
    if (!placed) continue
    occupied.push(placed.box)
    visible.push({
      code: zone.code, number: zone.number ?? 'i', tone: zone.tone, target,
      candidate: candidateZones.value.has(zone.code),
      x: placed.box.x + placed.box.width / 2, y: placed.box.y, vi: placed.vi, en: placed.en, hasNumber,
    })
  }
  return visible
})
// Toạ độ dòng chữ trong nhãn khu (dưới vòng số).
const lineY = (badge, index, alt = false) => (badge.hasNumber ? 24 : 0)
  + (alt ? badge.vi.length * VI_LINE + (index + 1) * EN_LINE : (index + 1) * VI_LINE) - 2

// Danh mục khu của tầng đang xem — giống cột danh sách của bảng sơ đồ.
const directory = computed(() => [...(plan.value?.zones ?? [])]
  .filter((zone) => zone.number != null || zone.tone === 'desk')
  .sort((a, b) => (a.number ?? Infinity) - (b.number ?? Infinity))
  .map((zone) => ({
    code: zone.code, number: zone.number ?? 'i', tone: zone.tone, target: zone.code === targetZone.value,
    candidate: candidateZones.value.has(zone.code),
    name: props.language === 'en' ? zone.name_en : zone.name,
  })))

// Số ứng viên trên từng tầng → huy hiệu đỏ trên nút tầng khác (prototype).
const candidatesOn = (level) => props.candidates.filter((candidate) => candidate.floor === level.label).length

const sunrooms = computed(() => (plan.value?.blocks ?? []).filter(({ kind }) => kind === 'sunroom'))
const coreBlocks = computed(() => (plan.value?.blocks ?? []).filter(({ kind }) => kind !== 'sunroom'))

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

const reducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches

// Có tuyến mới / ứng viên mới / đổi kiosk → về tầng phù hợp; tuyến mới thì tự phát mô phỏng.
watch([() => props.route, () => props.candidates, homeFloorId], ([route, candidates, home]) => {
  stop()
  elapsed.value = 0
  assetFailed.value = false
  chooseFraming('overview')
  const homeLevel = floors.value.find(({ id }) => id === home)?.label
  const elsewhere = candidates.length && !candidates.some(({ floor: level }) => level === homeLevel)
  floorId.value = (elsewhere && floors.value.find(({ label }) => label === candidates[0].floor)?.id) || home || null
  if (route && !reducedMotion()) nextTick(play)
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

function play() {
  if (playing.value || !duration.value || disposed) return
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

function togglePlayback() {
  if (playing.value) stop()
  else play()
}

// Nút "Xem lại đường đi" ở bảng bên phải.
function replay() {
  stop()
  elapsed.value = 0
  play()
}
defineExpose({ replay })

onMounted(() => {
  canFullscreen.value = Boolean(document.fullscreenEnabled && diagram.value.requestFullscreen)
  document.addEventListener('fullscreenchange', syncFullscreen)
  observer = new ResizeObserver(([{ contentRect }]) => {
    if (contentRect.width > 0 && contentRect.height > 0) size.value = { width: contentRect.width, height: contentRect.height }
  })
  observer.observe(viewport.value)
  // Chỉ tải three.js khi khách bật chế độ 3D.
  watch(() => Boolean(plan.value && show3D.value), async (wanted) => {
    if (!wanted || scene || disposed) return
    try {
      const { createFloorScene } = await import('../floor-scene')
      if (disposed || scene) return
      scene = createFloorScene(sceneCanvas.value)
      sceneReady.value = Boolean(scene)
    } catch {
      sceneReady.value = false
    }
    // Máy không có WebGL → ẩn nút 3D, giữ bản đồ 2D.
    if (!scene) {
      sceneFailed.value = true
      show3D.value = false
    }
  }, { immediate: true })
})

watchEffect(() => {
  if (!is3D.value) return
  const currentPlan = plan.value
  const destination = props.route?.destination.code ?? ''
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
    <!-- Cột trái như prototype: tiêu đề tầng, nút tầng, danh mục khu, chú giải -->
    <aside class="map-rail">
      <div v-if="floor" class="floor-title">
        {{ labels.floorUp }}<b>{{ floor.label }}</b><i>{{ labels.floorAlt(floor.label) }}</i>
      </div>
      <div class="floor-buttons" role="group" :aria-label="labels.mapFloors">
        <button v-for="level in floors" :key="level.id" type="button"
          :aria-pressed="floorId === level.id" @click="chooseFloor(level.id)">
          {{ labels.floor(level.label) }}
          <small v-if="level.id === homeFloorId">● {{ labels.yourFloor }}</small>
          <span v-if="candidatesOn(level) && level.id !== floorId" class="floor-badge">{{ candidatesOn(level) }}</span>
        </button>
      </div>

      <!-- Danh mục khu giống cột danh sách của bảng "Mặt bằng tầng" -->
      <section v-if="directory.length" class="zone-directory" :aria-label="labels.directory(floor?.label)">
        <h3>{{ labels.directory(floor?.label) }}</h3>
        <ol>
          <!-- Bấm vào khu → tìm đường ngay tới khu đó (khu đang là đích thì không cần bấm) -->
          <li v-for="item in directory" :key="item.code"
            :class="[item.tone && `tone-${item.tone}`, { 'is-target': item.target, 'is-cand': item.candidate }]">
            <button type="button" class="directory-item" :disabled="item.target || disabled"
              :aria-current="item.target ? 'location' : undefined" @click="$emit('select', item.code, item.name)">
              <span class="directory-number">{{ item.number }}</span>
              <span class="directory-name">{{ item.name }}</span>
              <span v-if="item.target" class="directory-tag">{{ labels.end }}</span>
            </button>
          </li>
        </ol>
      </section>

      <!-- Chú giải ký hiệu giống chân bảng sơ đồ thật -->
      <div class="map-legend">
        <span><i class="legend-dot dot-origin"></i>{{ labels.legend.yah }}</span>
        <span><i class="legend-line"></i>{{ labels.legend.route }}</span>
        <span><i class="legend-dot dot-arrival"></i>{{ labels.legend.dest }}</span>
        <span><i class="legend-dot dot-transfer">⇅</i>{{ labels.legend.transfer }}</span>
        <span><svg viewBox="-11 -10 22 20" aria-hidden="true"><rect x="-10" y="-9" width="20" height="18" rx="4" class="legend-box" /><path d="M -4 -1.5 L 0 -6 L 4 -1.5 Z M -4 1.5 L 0 6 L 4 1.5 Z" class="glyph-fill" /></svg>{{ labels.legend.elevator }}</span>
        <span><svg viewBox="-11 -10 22 20" aria-hidden="true"><rect x="-10" y="-9" width="20" height="18" rx="4" class="legend-box" /><path d="M -6 5 H -3 V 2 H 0 V -1 H 3 V -4 H 6" class="glyph-line" /></svg>{{ labels.legend.stairs }}</span>
        <span><svg viewBox="-11 -10 22 20" aria-hidden="true"><rect x="-10" y="-9" width="20" height="18" rx="4" class="legend-box" /><text y="3.4" text-anchor="middle" class="legend-text">WC</text></svg>{{ labels.legend.restroom }}</span>
        <span><i class="legend-exit">EXIT</i>{{ labels.legend.exit }}</span>
        <template v-if="detailedPlan">
          <span><i class="legend-swatch swatch-sunroom"></i>{{ labels.legend.sunroom }}</span>
          <span><i class="legend-swatch swatch-hall"></i>{{ labels.legend.hall }}</span>
          <span><i class="legend-swatch swatch-board"></i>{{ labels.legend.board }}</span>
          <span v-if="directory.some(({ tone }) => tone === 'desk')"><i class="legend-swatch swatch-desk"></i>{{ labels.legend.desk }}</span>
        </template>
      </div>
      <p class="map-note">{{ plan ? labels.mapNote : labels.guideNote }}</p>
    </aside>

    <div ref="viewport" class="map-viewport">
      <canvas v-show="is3D" ref="sceneCanvas" class="map-scene" aria-hidden="true"
        @webglcontextlost="sceneReady = false" @webglcontextrestored="sceneReady = Boolean(scene)" />
      <svg v-if="drawing.points.length || plan || asset" class="indoor-map" :viewBox="`0 0 ${size.width} ${size.height}`"
        role="img" :aria-label="labels.mapLabel(floor?.label)"
        @pointerdown="startDrag" @pointermove="moveDrag"
        @lostpointercapture="endDrag" @pointercancel="endDrag" @pointerup="endDrag">
        <g :transform="`translate(${camera.x} ${camera.y}) scale(${camera.scaleX} ${camera.scaleY})`">
          <g v-if="!is3D" :class="{ 'is-dim': highlighting }">
            <rect v-if="plan" class="map-floor" v-bind="floorBounds" rx="10" />
            <image v-else-if="asset" :href="asset" :width="mapWidth" :height="mapHeight"
              preserveAspectRatio="none" @error="assetFailed = true" />
            <template v-if="plan">
              <!-- Khu khám: đa giác màu cam/xanh như bảng thật; bản cũ chỉ có hình chữ nhật -->
              <template v-for="zone in plan.zones" :key="zone.code">
                <polygon v-if="zone.outline?.length" :points="polygon(zone.outline)" class="map-zone"
                  :class="[zone.tone && `tone-${zone.tone}`, {
                    'map-zone-target': zone.code === targetZone, 'map-zone-cand': candidateZones.has(zone.code),
                  }]" />
                <rect v-else v-bind="{ x: zone.x, y: zone.y, width: zone.width, height: zone.height }" rx="10"
                  class="map-zone" :class="{
                    'map-zone-target': zone.code === targetZone, 'map-zone-cand': candidateZones.has(zone.code),
                  }" />
              </template>
              <!-- Giếng trời: ô xám có mảng bóng chéo -->
              <g v-for="(block, index) in sunrooms" :key="`sun-${index}`" class="map-sunroom">
                <rect v-bind="{ x: block.x, y: block.y, width: block.width, height: block.height }" />
                <polygon :points="sunroomShade(block)" class="map-sunroom-shade" />
              </g>
              <!-- Hành lang chính màu vàng -->
              <polygon v-if="plan.hall?.length" :points="polygon(plan.hall)" class="map-hall" />
              <line v-for="([x1, y1, x2, y2], index) in (plan.hall?.length ? [] : plan.corridors)" :key="index"
                v-bind="{ x1, y1, x2, y2 }" class="map-corridor" :stroke-width="x1 === x2 ? 56 : 33" />
              <!-- Lõi hành lang: WC, thang thoát hiểm, thang máy, giếng sảnh -->
              <g v-for="(block, index) in coreBlocks" :key="`core-${index}`" :class="`map-core core-${block.kind}`">
                <title v-if="block.kind === 'board'">{{ labels.legend.board }}</title>
                <rect v-bind="{ x: block.x, y: block.y, width: block.width, height: block.height }" rx="3" />
                <path v-if="block.kind === 'escalator'" :d="stairTreads(block)" />
              </g>
            </template>
          </g>
          <!-- Biển EXIT (rìa khu và lõi hành lang) hiện ở cả 2D lẫn 3D -->
          <g v-if="plan" class="map-exits">
            <text v-for="(block, index) in coreBlocks.filter(({ kind }) => kind === 'exit_stair')" :key="`exit-core-${index}`"
              :x="block.x + block.width / 2" :y="block.y + block.height / 2 + 4" text-anchor="middle"
              class="core-exit-text">EXIT</text>
            <g v-for="(sign, index) in plan.exits ?? []" :key="`exit-${index}`" class="map-exit"
              :transform="at(sign.x, sign.y)">
              <rect x="-19" y="-8" width="38" height="16" rx="3" />
              <text y="4" text-anchor="middle">EXIT</text>
            </g>
          </g>
          <g v-if="plan && !is3D">
            <g v-for="room in flatRooms" :key="room.code">
              <rect :x="room.x" :y="room.y" :width="room.width" :height="room.height"
                rx="2" class="map-room" :class="{ 'map-room-target': room.code === route?.destination.code }" />
              <circle :cx="room.entrance.x" :cy="room.entrance.y" r="2.6" class="map-door" />
            </g>
          </g>
          <!-- Tuyến: viền trắng + xanh; khi đang mô phỏng thì phần phía trước mờ đi -->
          <g fill="none" stroke-linecap="round" stroke-linejoin="round" :class="{ 'route-ahead': inProgress }">
            <path :d="routePath" stroke="white" stroke-width="13" vector-effect="non-scaling-stroke" />
            <path :d="routePath" class="route-line" stroke-width="8" vector-effect="non-scaling-stroke" />
          </g>
          <g v-if="progressPath" fill="none" stroke-linecap="round" stroke-linejoin="round">
            <path :d="progressPath" stroke="white" stroke-width="13" vector-effect="non-scaling-stroke" />
            <path :d="progressPath" class="route-line" stroke-width="8" vector-effect="non-scaling-stroke" />
          </g>
        </g>

        <g v-for="badge in zoneBadges" :key="badge.code" :transform="at(badge.x, badge.y)" class="zone-badge"
          :class="[badge.tone && `tone-${badge.tone}`, { 'zone-badge-target': badge.target, 'zone-badge-cand': badge.candidate }]">
          <template v-if="badge.hasNumber">
            <circle cy="12" r="11" class="zone-number" />
            <text y="16.2" text-anchor="middle" class="zone-number-text">{{ badge.number }}</text>
          </template>
          <text v-for="(line, index) in badge.vi" :key="`vi-${index}`" text-anchor="middle"
            :y="lineY(badge, index)" class="zone-label">{{ line }}</text>
          <text v-for="(line, index) in badge.en" :key="`en-${index}`" text-anchor="middle"
            :y="lineY(badge, index, true)" class="zone-label zone-label-alt">{{ line }}</text>
        </g>
        <path v-for="arrow in arrows" :key="arrow" :transform="arrow" d="M -3 -2.5 L 0 0 L -3 2.5"
          fill="none" stroke="white" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" />
        <!-- Mốc trong lõi vẽ bằng ký hiệu giống chân bảng sơ đồ -->
        <g v-for="landmark in landmarks" :key="landmark.code" class="map-landmark"
          :transform="at(...screen(landmark.x, landmark.y))">
          <title>{{ labels.landmark(landmark.kind) }}</title>
          <rect x="-11" y="-10" width="22" height="20" rx="5" />
          <path v-if="landmark.kind === 'elevator'" d="M -4 -1.5 L 0 -6 L 4 -1.5 Z M -4 1.5 L 0 6 L 4 1.5 Z" class="glyph-fill" />
          <path v-else-if="landmark.kind === 'stairs'" d="M -6 5 H -3 V 2 H 0 V -1 H 3 V -4 H 6" class="glyph-line" />
          <text v-else-if="landmark.kind === 'restroom'" y="3.4" text-anchor="middle" class="landmark-label">WC</text>
          <text v-else y="3.4" text-anchor="middle" class="landmark-label">i</text>
        </g>

        <!-- Chấm đánh dấu như prototype: xanh = bạn đang ở đây, đỏ = điểm đến, tím = chuyển tầng -->
        <g v-for="(marker, index) in markers" :key="index" :transform="at(...position(marker.point))">
          <title>{{ marker.tag ?? labels.end }}</title>
          <g v-if="marker.kind === 'origin'">
            <circle r="20" class="yah-ring" />
            <circle r="11" class="yah-dot" />
          </g>
          <g v-else-if="marker.kind === 'arrival'">
            <circle r="18" class="dest-ring" />
            <circle r="11" class="dest-dot" />
          </g>
          <g v-else class="xfer-dot">
            <circle r="12" />
            <text y="5" text-anchor="middle">⇅</text>
          </g>
        </g>
        <g v-for="tag in tags" :key="`${tag.kind}-${tag.x}-${tag.y}`" :class="`map-tag tag-${tag.kind}`" aria-hidden="true">
          <rect :x="tag.x" :y="tag.y" :width="tag.width" :height="tag.height" rx="15" />
          <text :x="tag.x + tag.width / 2" :y="tag.y + 20" text-anchor="middle">{{ tag.text }}</text>
        </g>

        <!-- Người dẫn đường 2D: huy hiệu tròn có biểu tượng người + mũi tên hướng đi.
             Chưa phát mô phỏng thì ẩn để không che chấm "Bạn đang ở đây". -->
        <g v-if="showWalker && !is3D && elapsed > 0" :transform="at(...position(walker.point))" aria-hidden="true"
          class="map-guide" :class="{ 'is-walking': playing && walker.walking }">
          <ellipse cy="15" rx="11" ry="3.8" class="guide-shadow" />
          <circle r="16" class="guide-pulse" />
          <g v-if="walkerHeading !== null" :transform="`rotate(${walkerHeading})`">
            <path d="M 25 0 L 16 -7.5 L 16 7.5 Z" class="guide-heading" />
          </g>
          <g class="guide-bob">
            <circle r="14" class="guide-badge" />
            <circle cy="-4.2" r="3.8" class="guide-icon" />
            <path d="M -6.6 8 C -6.6 1.4 6.6 1.4 6.6 8 Z" class="guide-icon" />
          </g>
        </g>
      </svg>
      <p v-else class="map-empty">{{ labels.lineOnly }}</p>

      <!-- Nút bản đồ nổi góc trên phải -->
      <div v-if="hasFloorMap || drawing.points.length" class="map-actions">
        <button v-if="drawing.points.length" class="map-mode" type="button"
          :aria-pressed="!framingWholeFloor" @click="chooseFraming('route')">
          <LocateFixed :size="16" /> {{ labels.recenter }}
        </button>
        <button v-if="hasFloorMap" class="map-mode" type="button"
          :aria-pressed="framingWholeFloor" @click="chooseFraming('overview')">
          <Map :size="16" /> {{ labels.overview }}
        </button>
        <button v-if="plan && !sceneFailed" class="map-mode" type="button" :aria-label="labels.map3D" :aria-pressed="is3D"
          @click="show3D = !show3D">
          <Layers :size="16" /> {{ is3D ? '3D' : '2D' }}
        </button>
        <button v-if="canFullscreen" class="map-mode" type="button"
          :aria-label="fullscreen ? labels.exitFullscreen : labels.fullscreen"
          :title="fullscreen ? labels.exitFullscreen : labels.fullscreen" @click="toggleFullscreen">
          <Minimize v-if="fullscreen" :size="16" />
          <Maximize v-else :size="16" />
        </button>
      </div>
      <p v-if="fullscreenError" class="map-alert" role="status">{{ labels.fullscreenError }}</p>
      <p v-else-if="route && routeFloorIds.has(floorId) && !drawing.points.length" class="map-alert">
        {{ labels.noCoordinates }}
      </p>

      <!-- Thanh mô phỏng đường đi nổi góc dưới trái -->
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
      <div v-if="hasFloorMap" class="map-controls" role="group" :aria-label="labels.mapControls">
        <button type="button" :aria-label="labels.zoomIn" :disabled="zoom >= 3" @click="changeZoom(1.25)">
          <Plus :size="19" />
        </button>
        <button type="button" :aria-label="labels.zoomOut" :disabled="zoom <= 0.45" @click="changeZoom(0.8)">
          <Minus :size="19" />
        </button>
      </div>
    </div>
  </div>
</template>
