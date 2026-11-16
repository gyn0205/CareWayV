export const hasCoordinates = (point) => Number.isFinite(point.x) && Number.isFinite(point.y)

export const isTransfer = (step) => step.start.floor_id !== step.end.floor_id

export function routeFloors(route) {
  const floors = new Map()
  for (const point of [route.origin, ...route.steps.flatMap(({ start, end }) => [start, end]), route.arrival]) {
    if (floors.has(point.floor_id)) continue
    floors.set(point.floor_id, {
      id: point.floor_id,
      label: point.floor,
      asset: point.map_asset_url,
      plan: route.floor_plans?.find((plan) => plan.floor_id === point.floor_id),
    })
  }
  return [...floors.values()]
}

export function floorRoute(route, floorId) {
  const onFloor = (point) => point.floor_id === floorId && hasCoordinates(point)
  const segments = route.steps.filter((step) => onFloor(step.start) && onFloor(step.end))
  const points = [route.origin, ...route.steps.flatMap(({ start, end }) => [start, end]), route.arrival]
    .filter(onFloor)
  const transfers = route.steps.filter(isTransfer).flatMap((step) => [
    { point: step.start, step, leaving: true },
    { point: step.end, step, leaving: false },
  ]).filter(({ point }) => onFloor(point))
  return { points, segments, transfers }
}

export function previewTimeline(route) {
  if (!route.steps.length || !route.steps.every(({ start, end }) => (
    hasCoordinates(start) && hasCoordinates(end)
  ))) return []

  let elapsed = 0
  return route.steps.map((step) => {
    const duration = isTransfer(step) ? 2000 : Math.max(470, Math.min(3600, step.seconds * 185))
    const begins = elapsed
    elapsed += duration
    return { step, begins, ends: elapsed, duration }
  })
}

export function previewFrame(timeline, elapsed) {
  if (!timeline.length) return null
  const current = timeline.find(({ ends }) => elapsed < ends) ?? timeline.at(-1)
  const { step, begins, duration } = current
  const fraction = Math.min(1, Math.max(0, (elapsed - begins) / duration))
  if (isTransfer(step)) {
    return { point: fraction >= 0.5 ? step.end : step.start, step, walking: false }
  }
  const { start, end } = step
  return {
    point: { ...start, x: start.x + (end.x - start.x) * fraction, y: start.y + (end.y - start.y) * fraction },
    step,
    walking: fraction < 1,
  }
}

export function corridorFootprint([x1, y1, x2, y2]) {
  const horizontal = y1 === y2
  return {
    x: (x1 + x2) / 2,
    y: (y1 + y2) / 2,
    width: horizontal ? Math.abs(x2 - x1) + 13 : 56,
    height: horizontal ? 33 : Math.abs(y2 - y1) + 36,
  }
}

export function floorFootprint(plan) {
  let left = Infinity
  let top = Infinity
  let right = -Infinity
  let bottom = -Infinity

  function include(x, y, width, height) {
    left = Math.min(left, x)
    top = Math.min(top, y)
    right = Math.max(right, x + width)
    bottom = Math.max(bottom, y + height)
  }

  for (const { x, y, width, height } of plan.zones) include(x, y, width, height)
  for (const { x, y, width, height } of plan.rooms) include(x - 2, y - 2, width + 4, height + 4)
  for (const segment of plan.corridors) {
    const { x, y, width, height } = corridorFootprint(segment)
    include(x - width / 2, y - height / 2, width, height)
  }
  for (const { x, y } of plan.landmarks) include(x - 12, y - 14, 24, 28)

  if (!Number.isFinite(left)) return { x: 0, y: 0, width: plan.width, height: plan.height }
  return { x: left, y: top, width: right - left, height: bottom - top }
}

export function fitOverview(size, bounds, fillWidth = false) {
  const horizontalPadding = Math.min(32, size.width * 0.08)
  const verticalPadding = Math.min(28, size.height * 0.08)
  const widthScale = (size.width - 2 * horizontalPadding) / bounds.width
  const heightScale = (size.height - 2 * verticalPadding) / bounds.height
  const scaleY = Math.min(widthScale, heightScale)
  return {
    centerX: bounds.x + bounds.width / 2,
    centerY: bounds.y + bounds.height / 2,
    scaleX: fillWidth ? widthScale : scaleY,
    scaleY,
  }
}

export function fitRouteView(size, points, hasFloorMap) {
  const xs = points.map(([x]) => x)
  const ys = points.map(([, y]) => y)
  const [left, right] = [Math.min(...xs), Math.max(...xs)]
  const [top, bottom] = [Math.min(...ys), Math.max(...ys)]
  const horizontalPadding = Math.min(64, size.width * 0.15)
  const verticalPadding = Math.min(60, size.height * 0.16)
  const minimumWidth = hasFloorMap ? 480 : 260
  const minimumHeight = hasFloorMap ? 280 : 150
  const scale = Math.min(
    (size.width - 2 * horizontalPadding) / Math.max(right - left, minimumWidth),
    (size.height - 2 * verticalPadding) / Math.max(bottom - top, minimumHeight),
    1.7,
  )
  return { centerX: (left + right) / 2, centerY: (top + bottom) / 2, scaleX: scale, scaleY: scale }
}

export function roomEntrance(room, corridors) {
  const x = room.x + room.width / 2
  let side = room.door_side
  if (!side) {
    // Plans from older API versions omit the door side. Use the adjacent corridor.
    const middle = room.y + room.height / 2
    let bestDistance = Infinity
    for (const [startX, startY, endX, endY] of corridors) {
      if (startY !== endY || x < Math.min(startX, endX) || x > Math.max(startX, endX)) continue
      const distance = Math.abs(middle - startY)
      if (distance >= bestDistance) continue
      bestDistance = distance
      side = startY < middle ? 'north' : 'south'
    }
  }
  side ??= 'south'
  return { side, x, y: side === 'north' ? room.y : room.y + room.height }
}
