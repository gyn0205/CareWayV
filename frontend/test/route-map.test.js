import assert from 'node:assert/strict'
import test from 'node:test'
import { Vector3 } from 'three'
import { frameFloorCamera, makeFloorCamera } from '../src/floor-scene.js'
import { fitOverview, fitRouteView, floorFootprint, floorRoute, previewFrame, previewTimeline, roomEntrance, routeFloors } from '../src/route-map.js'

const kiosk = { floor_id: 54, floor: 4, x: 0.54, y: 0.64 }
const liftIn = { floor_id: 54, floor: 4, x: 0.46, y: 0.69 }
const liftOut = { floor_id: 39, floor: 3, x: 0.46, y: 0.69 }
const cashier = { floor_id: 39, floor: 3, x: 0.58, y: 0.49 }
const walk = (start, end) => ({ start, end, kind: 'walk', seconds: 8 })
const transfer = { start: liftIn, end: liftOut, kind: 'elevator', seconds: 42 }
const route = {
  origin: kiosk,
  arrival: cashier,
  steps: [walk(kiosk, liftIn), transfer, walk(liftOut, cashier)],
  floor_plans: [{ floor_id: 39 }, { floor_id: 54 }],
}

test('floor plans follow the trip order, with the elevator marked on each floor', () => {
  assert.deepEqual(routeFloors(route).map(({ plan }) => plan.floor_id), [54, 39])
  const upper = floorRoute(route, kiosk.floor_id)
  const lower = floorRoute(route, cashier.floor_id)
  assert.deepEqual(upper.segments, [route.steps[0]])
  assert.deepEqual(lower.segments, [route.steps[2]])
  assert.deepEqual(upper.transfers.map(({ point, leaving }) => [point, leaving]), [[liftIn, true]])
  assert.deepEqual(lower.transfers.map(({ point, leaving }) => [point, leaving]), [[liftOut, false]])
})

test('preview walks to the elevator, changes floors inside it, and ends at the room', () => {
  const timeline = previewTimeline(route)
  const [approach, changeFloor, exit] = timeline
  const walking = previewFrame(timeline, approach.duration / 2)
  assert.ok(walking.walking)
  assert.equal(walking.point.floor_id, kiosk.floor_id)
  assert.ok(walking.point.x < kiosk.x && walking.point.x > liftIn.x)
  const before = previewFrame(timeline, changeFloor.begins + changeFloor.duration / 4)
  assert.deepEqual(before.point, liftIn)
  assert.ok(!before.walking)
  assert.deepEqual(previewFrame(timeline, changeFloor.ends - 1).point, liftOut)
  assert.deepEqual(previewFrame(timeline, exit.ends).point, cashier)
})

test('missing coordinates break the line and disable preview instead of inventing a shortcut', () => {
  const unknown = { ...liftIn, x: null, y: null }
  const incomplete = { ...route, steps: [walk(kiosk, unknown), { ...transfer, start: unknown }, route.steps[2]] }
  assert.deepEqual(floorRoute(incomplete, kiosk.floor_id).segments, [])
  assert.deepEqual(floorRoute(incomplete, cashier.floor_id).segments, [route.steps[2]])
  assert.deepEqual(previewTimeline(incomplete), [])
})

test('a destination at the starting point keeps its pin without starting a preview', () => {
  const arrived = { origin: kiosk, arrival: kiosk, steps: [] }
  assert.deepEqual(routeFloors(arrived).map(({ id }) => id), [kiosk.floor_id])
  assert.deepEqual(previewTimeline(arrived), [])
  assert.deepEqual(floorRoute(arrived, kiosk.floor_id).segments, [])
})

test('a door cuts the wall that faces the corridor, including on older floor plans', () => {
  const room = { x: 620, y: 244, width: 38, height: 35 }
  const corridors = [[600, 228, 670, 228], [600, 300, 670, 300]]
  assert.deepEqual(roomEntrance(room, corridors), { side: 'north', x: 639, y: 244 })
  assert.deepEqual(roomEntrance({ ...room, door_side: 'south' }, corridors),
    { side: 'south', x: 639, y: 279 })
})

test('route overlay aligns with the overhead camera without rotation or skew', () => {
  const size = { width: 820, height: 470 }
  const camera = makeFloorCamera()
  camera.updateMatrixWorld()
  const views = [
    { x: 55, y: -370, scaleX: 1.2, scaleY: 1.2 },
    { x: -22, y: -54, scaleX: 0.69, scaleY: 0.43 },
  ]
  for (const view of views) {
    frameFloorCamera(camera, size, view)
    for (const [x, elevation, y] of [[648, 0, 697], [552, 16, 697], [648, 12, 218]]) {
      const position = new Vector3(x, elevation, y).project(camera)
      const screenX = (position.x + 1) * size.width / 2
      const screenY = (1 - position.y) * size.height / 2
      assert.ok(Math.abs(screenX - (view.x + x * view.scaleX)) < 1e-6)
      assert.ok(Math.abs(screenY - (view.y + y * view.scaleY)) < 1e-6)
    }
  }
})

test('overview fills the width using the actual floor footprint and keeps every edge visible', () => {
  const floor = floorFootprint({
    width: 1200, height: 1070,
    zones: [{ x: 90, y: 200, width: 400, height: 120 }],
    rooms: [{ x: 1050, y: 680, width: 38, height: 35 }],
    corridors: [[600, 63, 600, 1002]],
    landmarks: [{ x: 650, y: 1002 }],
  })
  assert.deepEqual(floor, { x: 90, y: 45, width: 1000, height: 975 })
  for (const size of [{ width: 1530, height: 524 }, { width: 316, height: 460 }]) {
    const bounds = fitOverview(size, floor, true)
    assert.equal(bounds.centerX, 590)
    assert.equal(bounds.centerY, 532.5)
    assert.ok(floor.width * bounds.scaleX < size.width)
    assert.ok(floor.height * bounds.scaleY < size.height)
    assert.ok(size.width - floor.width * bounds.scaleX <= 64)
  }
  const image = fitOverview({ width: 1530, height: 524 }, floor)
  assert.equal(image.scaleX, image.scaleY)
})

test('route view enlarges a short route and keeps a long route within the map', () => {
  const viewport = { width: 1530, height: 524 }
  const overview = fitOverview(viewport, { x: 0, y: 0, width: 1200, height: 1070 }, true)
  const nearby = fitRouteView(viewport, [[552, 737], [648, 697]], true)
  assert.equal(nearby.centerX, 600)
  assert.equal(nearby.centerY, 717)
  assert.equal(nearby.scaleX, nearby.scaleY)
  assert.ok(nearby.scaleY > overview.scaleY * 2)

  const longRoute = [[90, 100], [620, 400], [1080, 970]]
  for (const size of [viewport, { width: 316, height: 460 }]) {
    const { centerX, centerY, scaleX, scaleY } = fitRouteView(size, longRoute, true)
    for (const [x, y] of longRoute) {
      assert.ok(Math.abs(x - centerX) * scaleX < size.width / 2 - 24)
      assert.ok(Math.abs(y - centerY) * scaleY < size.height / 2 - 24)
    }
  }
})
