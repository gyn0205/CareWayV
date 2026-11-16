import {
  BoxGeometry, CircleGeometry, Color, DirectionalLight, Group, HemisphereLight, InstancedMesh,
  Mesh, MeshBasicMaterial, MeshLambertMaterial, Object3D, OrthographicCamera, Scene,
  SphereGeometry, WebGLRenderer,
} from 'three'
import { corridorFootprint, roomEntrance } from './route-map.js'

const roomColors = [
  ['#dce9f1', '#a2bacd'],
  ['#dfebe3', '#a8c2b1'],
  ['#eee8df', '#c9b8a3'],
  ['#e8e5f0', '#bab0d1'],
]

function planBoxes(plan, destinationCode) {
  const boxes = []
  // The y coordinate in the floor plan maps to the depth axis in Three.js.
  const box = (x, z, width, depth, base, height, color) => {
    boxes.push({ x, z, width, depth, base, height, color })
  }
  const zoneColors = new Map()
  for (const [index, zone] of plan.zones.entries()) {
    const colors = roomColors[index % roomColors.length]
    zoneColors.set(zone.code, colors)
    const x = zone.x + zone.width / 2
    const z = zone.y + zone.height / 2
    box(x, z, zone.width, zone.height, -9, 8, colors[1])
    box(x, z, zone.width, zone.height, -1, 0.8, colors[0])
  }

  for (const segment of plan.corridors) {
    const { x, y: z, width, height: depth } = corridorFootprint(segment)
    box(x, z, width, depth, -9, 7, '#adbfc9')
    box(x, z, width - 1, depth - 1, -2, 2, '#f3f3ea')
  }

  for (const [index, room] of plan.rooms.entries()) {
    const door = roomEntrance(room, plan.corridors)
    const north = door.side === 'north'
    const z = room.y + room.height / 2
    const [floorColor, accent] = zoneColors.get(room.code.split('-').slice(0, 2).join('-')) ?? roomColors[0]
    const destination = room.code === destinationCode
    const wall = destination ? '#4f91dd' : '#9dafbc'
    const thickness = 2.5
    const wallHeight = destination ? 14 : 12
    const gap = Math.min(14, room.width / 2)
    const wing = (room.width - gap) / 2

    box(door.x, z, room.width, room.height, -0.2, 1, destination ? '#acd4fa' : floorColor)
    box(room.x + 3, z, 4, room.height - 2, 0.8, 0.22, accent)
    box(door.x, north ? room.y + room.height : room.y, room.width, thickness, 0.8, wallHeight, wall)
    box(room.x, z, thickness, room.height, 0.8, wallHeight, wall)
    box(room.x + room.width, z, thickness, room.height, 0.8, wallHeight, wall)
    box(room.x + wing / 2, door.y, wing, thickness, 0.8, 7.5, wall)
    box(room.x + room.width - wing / 2, door.y, wing, thickness, 0.8, 7.5, wall)
    box(door.x, door.y, gap, 5, 0.3, 0.75, destination ? '#317acb' : accent)
    for (const side of [-1, 1]) {
      box(door.x + side * gap / 2, door.y, 2.3, 3.7, 0.8, 8.8, destination ? '#1b62ba' : accent)
    }

    // Small props give a sense of room scale. Leave the doorway and its approach clear.
    const back = north ? 1 : -1
    const furnitureColor = destination ? '#6e9dc3' : accent
    if (index % 3 === 0) {
      box(door.x - 7, z + back * 6, 13, 12, 0.8, 6.5, furnitureColor)
      box(door.x - 7, z + back * 6, 13, 12, 7.3, 1.4, '#fcfcf8')
      box(door.x + 5, z + back * 5, 5, 6, 0.8, 4, '#758c9f')
    } else if (index % 3 === 1) {
      box(door.x + 10, z + back * 7, 7, 10, 0.8, 5, furnitureColor)
      box(door.x + 10, z + back * 10, 7, 3, 5.8, 4, furnitureColor)
    }
  }

  for (const { x, y: z, kind } of plan.landmarks) {
    if (kind === 'elevator') {
      box(x, z, 22, 24, 0, 2, '#b5a7d0')
      box(x - 10, z, 2.5, 24, 2, 13, '#706098')
      box(x + 10, z, 2.5, 24, 2, 13, '#706098')
      box(x, z - 11, 21, 2.5, 2, 13, '#9182ad')
    } else if (kind === 'stairs') {
      for (let step = 0; step < 5; step++) {
        box(x, z - 10 + step * 5, 17, 5, 0, (step + 1) * 2.4, '#a3b1bd')
      }
    } else if (kind === 'restroom') {
      box(x, z, 18, 16, 0, 3, '#a5c6d8')
    } else {
      box(x, z, 16, 15, 0, 2, '#82b9cf')
      box(x, z - 4, 11, 4, 2, 12, '#187b9e')
      box(x, z - 3, 8, 2, 9, 4, '#c1f2fa')
    }
  }
  return boxes
}

function makeWalker() {
  const root = new Group()
  const model = new Group()
  root.add(model)
  const block = new BoxGeometry(1, 1, 1)
  const sphere = new SphereGeometry(1, 12, 8)
  const disc = new CircleGeometry(1, 24)
  const navy = new MeshLambertMaterial({ color: '#153e79' })
  const blue = new MeshLambertMaterial({ color: '#246ce8' })
  const amber = new MeshLambertMaterial({ color: '#ffb24b' })
  const shadow = new MeshBasicMaterial({ color: '#0a2349', transparent: true, opacity: 0.22, depthWrite: false })
  const mesh = (geometry, material, scale, position, parent = model) => {
    const part = new Mesh(geometry, material)
    part.scale.set(...scale)
    part.position.set(...position)
    parent.add(part)
    return part
  }
  const spot = mesh(disc, shadow, [9, 7, 1], [0, 1.4, 0])
  spot.rotation.x = -Math.PI / 2
  mesh(sphere, amber, [4.7, 4.7, 4.7], [0, 25, 0])
  mesh(sphere, amber, [1.5, 1.4, 1.6], [0, 24, 4])
  mesh(block, blue, [7.5, 10, 5.2], [0, 16, 0])

  const arms = []
  const legs = []
  for (const side of [-1, 1]) {
    const arm = new Group()
    arm.position.set(side * 5.1, 20, 0)
    arm.rotation.z = side * 0.27
    mesh(block, navy, [2.6, 9, 2.6], [0, -4.4, 0], arm)
    const leg = new Group()
    leg.position.set(side * 2.1, 11.2, 0)
    mesh(block, navy, [3.2, 10.2, 3.2], [0, -5.1, 0], leg)
    mesh(block, navy, [3.4, 1.6, 5.1], [0, -10.4, 1], leg)
    model.add(arm, leg)
    arms.push(arm)
    legs.push(leg)
  }

  return {
    model: root,
    update({ x, y, facing, stride }, { scaleX, scaleY }) {
      root.position.set(x, 1.15, y)
      // The schematic can widen the floor, so keep the guide's screen proportions.
      const scale = Math.min(scaleX, scaleY)
      const bodyScale = Math.min(2, Math.max(0.95, 1.35 / scale))
      root.scale.set(bodyScale * scale / scaleX, bodyScale, bodyScale * scale / scaleY)
      model.rotation.y = facing
      for (const [index, side] of [-1, 1].entries()) {
        legs[index].rotation.x = side * stride
        arms[index].rotation.x = -side * stride * 0.85
      }
    },
    dispose() {
      for (const resource of [block, sphere, disc, navy, blue, amber, shadow]) resource.dispose()
    },
  }
}

export function makeFloorCamera() {
  const camera = new OrthographicCamera(0, 1, 1, 0, 0.1, 6000)
  camera.position.set(0, 2400, 0)
  // Keep the floor's north at the top of the screen in both map modes.
  camera.up.set(0, 0, -1)
  camera.lookAt(0, 0, 0)
  return camera
}

export function frameFloorCamera(camera, size, view) {
  camera.left = -view.x / view.scaleX
  camera.right = (size.width - view.x) / view.scaleX
  camera.top = view.y / view.scaleY
  camera.bottom = (view.y - size.height) / view.scaleY
  camera.updateProjectionMatrix()
}

export function createFloorScene(canvas) {
  const context = canvas.getContext('webgl2', { alpha: true, antialias: true })
  if (!context) return null
  const renderer = new WebGLRenderer({ canvas, context, alpha: true, antialias: true })
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2))
  renderer.setClearColor(0, 0)

  const scene = new Scene()
  const camera = makeFloorCamera()
  scene.add(new HemisphereLight('#fdfdff', '#6c8498', 1.55))
  const sun = new DirectionalLight('#fff5e8', 1.3)
  sun.position.set(-360, 740, -180)
  scene.add(sun)

  const geometry = new BoxGeometry(1, 1, 1)
  const material = new MeshLambertMaterial()
  const walker = makeWalker()
  scene.add(walker.model)
  let floor
  let width = 0
  let height = 0

  function clearFloor() {
    if (!floor) return
    scene.remove(floor)
    floor.dispose()
    floor = undefined
  }

  return {
    setFloor(plan, destinationCode) {
      clearFloor()
      const boxes = planBoxes(plan, destinationCode)
      const transform = new Object3D()
      const color = new Color()
      floor = new InstancedMesh(geometry, material, boxes.length)
      for (const [index, box] of boxes.entries()) {
        transform.position.set(box.x, box.base + box.height / 2, box.z)
        transform.scale.set(box.width, box.height, box.depth)
        transform.updateMatrix()
        floor.setMatrixAt(index, transform.matrix)
        floor.setColorAt(index, color.set(box.color))
      }
      floor.computeBoundingSphere()
      scene.add(floor)
    },
    draw(size, view, walkerPose) {
      const nextWidth = Math.max(1, Math.round(size.width))
      const nextHeight = Math.max(1, Math.round(size.height))
      if (width !== nextWidth || height !== nextHeight) {
        width = nextWidth
        height = nextHeight
        renderer.setSize(width, height, false)
      }
      frameFloorCamera(camera, size, view)
      walker.model.visible = Boolean(walkerPose)
      if (walkerPose) walker.update(walkerPose, view)
      renderer.render(scene, camera)
    },
    dispose() {
      clearFloor()
      walker.dispose()
      geometry.dispose()
      material.dispose()
      renderer.dispose()
    },
  }
}
