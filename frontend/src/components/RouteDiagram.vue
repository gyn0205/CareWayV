<script setup>
import { computed, ref, watch, watchEffect } from 'vue'

const props = defineProps({
  route: { type: Object, required: true },
  labels: { type: Object, required: true },
})
const canvas = ref(null)
const floorId = ref(null)
const floors = computed(() => {
  const byId = new Map()
  for (const point of [props.route.origin, ...props.route.steps.map((step) => step.end), props.route.arrival]) {
    byId.set(point.floor_id, point.floor)
  }
  return [...byId].map(([id, label]) => ({ id, label }))
})
watch(() => props.route, (route) => {
  floorId.value = route.origin.floor_id
}, { immediate: true })

const hasCoordinates = (point) => Number.isFinite(point.x) && Number.isFinite(point.y)
const diagram = computed(() => {
  const { origin, arrival, steps } = props.route
  const points = [origin, ...steps.map((step) => step.end), arrival]
    .filter((point) => point.floor_id === floorId.value && hasCoordinates(point))
  const segments = steps.filter((step) =>
    [step.start, step.end].every((point) => point.floor_id === floorId.value && hasCoordinates(point)))
  const transfers = steps.filter((step) => step.start.floor_id !== step.end.floor_id)
    .flatMap((step) => [step.start, step.end])
    .filter((point) => point.floor_id === floorId.value && hasCoordinates(point))
  return { points, segments, transfers, origin, arrival }
})

watchEffect(() => {
  if (!canvas.value || !diagram.value.points.length) return
  const { points, segments, transfers, origin, arrival } = diagram.value
  const { width, height } = canvas.value
  const context = canvas.value.getContext('2d')
  const minX = Math.min(...points.map((point) => point.x))
  const maxX = Math.max(...points.map((point) => point.x))
  const minY = Math.min(...points.map((point) => point.y))
  const maxY = Math.max(...points.map((point) => point.y))
  const scale = Math.min((width - 124) / Math.max(maxX - minX, 0.25), (height - 88) / Math.max(maxY - minY, 0.2))
  const position = (point) => [
    width / 2 + (point.x - (minX + maxX) / 2) * scale,
    height / 2 + (point.y - (minY + maxY) / 2) * scale,
  ]

  context.clearRect(0, 0, width, height)
  context.beginPath()
  for (const { start, end } of segments) {
    context.moveTo(...position(start))
    context.lineTo(...position(end))
  }
  context.lineWidth = 8
  context.lineCap = 'round'
  context.strokeStyle = '#157c9d'
  context.stroke()

  function marker(point, color, radius) {
    if (point.floor_id !== floorId.value || !hasCoordinates(point)) return
    const [x, y] = position(point)
    context.beginPath()
    context.arc(x, y, radius, 0, Math.PI * 2)
    context.fillStyle = color
    context.fill()
    context.lineWidth = 3
    context.strokeStyle = '#fff'
    context.stroke()
  }
  for (const point of transfers) marker(point, '#157c9d', 11)
  marker(origin, '#075278', 12)
  marker(arrival, '#bd8b31', 12)
})
</script>

<template>
  <div class="route-diagram">
    <div v-if="floors.length > 1" class="floor-tabs">
      <button v-for="floor in floors" :key="floor.id" type="button"
        :aria-pressed="floorId === floor.id" @click="floorId = floor.id">
        {{ labels.floor(floor.label) }}
      </button>
    </div>
    <canvas v-if="diagram.points.length" ref="canvas" width="720" height="360" role="img"
      :aria-label="labels.mapLabel(floors.find((floor) => floor.id === floorId)?.label)" />
    <p v-else>{{ labels.noCoordinates }}</p>
    <template v-if="diagram.points.length">
      <div class="diagram-key">
        <span><i class="origin-key"></i>{{ labels.start }}</span>
        <span><i class="path-key"></i>{{ labels.path }}</span>
        <span><i class="arrival-key"></i>{{ labels.end }}</span>
      </div>
      <p class="map-note">{{ labels.mapNote }}</p>
    </template>
  </div>
</template>
