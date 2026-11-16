export const hasCoordinates = (point) => Number.isFinite(point.x) && Number.isFinite(point.y)

export const isTransfer = (step) => step.start.floor_id !== step.end.floor_id

// Mã khu từ mã phòng: "3-10-01" → "3-10"; mã khu giữ nguyên.
export const zoneCode = (code) => code.split('-').slice(0, 2).join('-')

// Chia tên khu thành tối đa 2 dòng, mỗi dòng không quá `limit` ký tự; quá dài thì thêm "…".
export function wrapLabel(text, limit) {
  if (limit < 6) return []
  if (text.length <= limit) return [text]
  const lines = ['']
  for (const word of text.split(' ')) {
    const line = lines.at(-1)
    if (!line || line.length + 1 + word.length <= limit) lines[lines.length - 1] = line ? `${line} ${word}` : word
    else lines.push(word)
  }
  if (lines.length <= 2 && lines.every((line) => line.length <= limit)) return lines
  const second = lines.slice(1).join(' ')
  return [
    lines[0].length > limit ? `${lines[0].slice(0, limit - 1).trimEnd()}…` : lines[0],
    second.length > limit ? `${second.slice(0, limit - 1).trimEnd()}…` : second,
  ]
}

// Hướng đi (độ, 0 = sang phải, chiều kim đồng hồ trên màn hình); đoạn quá ngắn thì không có hướng.
export function headingDegrees([startX, startY], [endX, endY]) {
  const dx = endX - startX
  const dy = endY - startY
  if (Math.hypot(dx, dy) < 1) return null
  return Math.atan2(dy, dx) * 180 / Math.PI
}

// Điểm nằm trong (hoặc trên cạnh) đa giác — dùng để giữ nhãn khu nằm trong khu.
export function insidePolygon(points, x, y) {
  let inside = false
  for (let index = 0; index < points.length; index++) {
    const [x1, y1] = points[index]
    const [x2, y2] = points[(index + 1) % points.length]
    if (x1 === x2 && x1 === x && y >= Math.min(y1, y2) && y <= Math.max(y1, y2)) return true
    if (y1 === y2 && y1 === y && x >= Math.min(x1, x2) && x <= Math.max(x1, x2)) return true
    if ((y1 > y) !== (y2 > y) && x < (x2 - x1) * (y - y1) / (y2 - y1) + x1) inside = !inside
  }
  return inside
}

// Mảng bóng chéo trong giếng trời, giống hình thang tối trên bảng sơ đồ.
export function sunroomShade({ x, y, width, height }) {
  return [[x, y], [x + width * 0.32, y + height * 0.24], [x + width * 0.32, y + height], [x, y + height]]
    .map((point) => point.join(',')).join(' ')
}

// Các bậc thang bộ trong giếng sảnh.
export function stairTreads({ x, y, width, height }) {
  return Array.from({ length: 7 }, (_, step) => `M ${x + 5} ${y + 6 + step * (height - 12) / 6} H ${x + width - 5}`).join(' ')
}

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
  // Biển EXIT nằm sát mép khu, tính vào khung để không bị cắt.
  for (const { x, y } of plan.exits ?? []) include(x - 20, y - 9, 40, 18)

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

// `minimum` = khung tối thiểu (đơn vị bản đồ) để tuyến ngắn vẫn thấy các khu xung quanh.
export function fitRouteView(size, points, hasFloorMap, minimum = hasFloorMap ? [480, 280] : [260, 150]) {
  const xs = points.map(([x]) => x)
  const ys = points.map(([, y]) => y)
  const [left, right] = [Math.min(...xs), Math.max(...xs)]
  const [top, bottom] = [Math.min(...ys), Math.max(...ys)]
  const horizontalPadding = Math.min(64, size.width * 0.15)
  const verticalPadding = Math.min(60, size.height * 0.16)
  const [minimumWidth, minimumHeight] = minimum
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
