import assert from 'node:assert/strict'
import { beforeEach, afterEach, mock, test } from 'node:test'
import vm from 'node:vm'
import {
  CONTINUE_MS, HOLD_MS, IDLE_MS, QUIET_MS, WORKLET, createConversation, isEcho, looksUnfinished, meaningful,
} from '../src/realtime.js'

/* ---------- Giả lập trình duyệt: mic, Web Audio, WebSocket, <audio>, fetch ---------- */
let sockets, sources, speechFetches, tracks, worklet, tokenResponse, micGate

class FakeSocket {
  static OPEN = 1
  constructor(url) {
    this.url = url
    this.readyState = 0
    this.sent = []
    sockets.push(this)
  }
  send(data) { this.sent.push(JSON.parse(data)) }
  close() { this.readyState = 3; this.closed = true }
  open() { this.readyState = 1; this.onopen?.() }
  emit(message) { this.onmessage?.({ data: JSON.stringify(message) }) }
}


beforeEach(() => {
  sockets = []
  sources = []
  speechFetches = []
  tracks = []
  tokenResponse = { ok: true, status: 200, json: async () => ({ url: 'wss://stt.test/realtime?token=t' }) }
  micGate = null
  globalThis.WebSocket = FakeSocket
  globalThis.fetch = async (url) => {
    if (!String(url).includes('/speech')) return tokenResponse
    speechFetches.push(url)
    // 4801 byte: hai gói, gói đầu lẻ một byte → phải ghép đúng mẫu 16-bit.
    return new Response(new ReadableStream({
      start(controller) {
        controller.enqueue(new Uint8Array(2401).fill(0x10))
        controller.enqueue(new Uint8Array(2400).fill(0x10))
        controller.close()
      },
    }))
  }
  globalThis.AudioContext = class {
    currentTime = 0
    destination = {}
    audioWorklet = { addModule: async () => {} }
    createBuffer(channels, length, rate) {
      const data = new Float32Array(length)
      return { length, duration: length / rate, getChannelData: () => data }
    }
    createBufferSource() {
      const source = { connect() {}, start(at) { this.at = at }, stop() { this.stopped = true } }
      sources.push(source)
      return source
    }
    createMediaStreamSource() { return { connect: () => {} } }
    resume() { return Promise.resolve() }
    close() { this.closed = true; return Promise.resolve() }
  }
  globalThis.AudioWorkletNode = class {
    constructor() { this.port = {}; worklet = this }
  }
  Object.defineProperty(globalThis, 'navigator', {
    configurable: true,
    value: {
      mediaDevices: {
        async getUserMedia() {
          if (micGate) await micGate
          const track = { stopped: false, stop() { this.stopped = true } }
          tracks.push(track)
          return { getTracks: () => [track] }
        },
      },
    },
  })
  mock.timers.enable({ apis: ['setTimeout', 'Date'] })
})

afterEach(() => mock.timers.reset())

const flush = () => new Promise((done) => setImmediate(done))
// Một gói 50 ms từ mic; level > 0 là khách đang nói.
const chunk = (level = 0) => worklet.port.onmessage({ data: new Int16Array(800).fill(level * 32767).buffer })
// Để luồng giọng đọc (giả) tải xong các gói.
const load = async () => { await flush(); await flush() }

async function session(language = 'vi') {
  const log = { states: [], heard: [], said: [], interrupts: 0, errors: [] }
  const talk = createConversation({
    language,
    onState: (value) => log.states.push(value),
    onHeard: (text) => log.heard.push(text),
    onUtterance: (text, continuation) => log.said.push([text, continuation]),
    onInterrupt: () => log.interrupts++,
    onError: (key) => log.errors.push(key),
  })
  await talk.start()
  await flush()
  return { talk, log, socket: sockets.at(-1) }
}

/* ---------- Hàm thuần ---------- */
test('câu còn dở thì chờ, câu đủ ý thì gửi', () => {
  for (const text of ['Cho tôi hỏi.', 'Tôi muốn đến', 'phòng', 'Ờ.', '', 'Where is the', 'khoa tim mạch,', 'ừm à']) {
    assert.equal(looksUnfinished(text), true, text)
  }
  for (const text of ['Cho tôi hỏi phòng siêu âm.', 'Phòng 4-053', 'Khoa tim mạch ạ', 'Where is the pharmacy?', 'ở tầng mấy vậy',
    'Where is the pharmacy, please?', 'Chỉ đường cho tôi', 'Which floor is it on?']) {
    assert.equal(looksUnfinished(text), false, text)
  }
  assert.equal(meaningful('Ờ. À.'), false)
  assert.equal(meaningful('ờ nhà thuốc'), true)
})

test('lọc tiếng vọng của chính kiosk nhưng nhận ra khách nói', () => {
  const reply = 'Để đến Trung tâm Tim mạch, mã 3-01, tầng 3, anh chị đi theo hướng dẫn sau.'
  assert.equal(isEcho('để đến trung tâm tim mạch mã ba không một', reply), true)
  assert.equal(isEcho('Trung tâm tim mạch', reply), true)
  assert.equal(isEcho('ờ', reply), true)
  assert.equal(isEcho('không phải, tôi cần nhà thuốc', reply), false)
  assert.equal(isEcho('khoa tim mạch', reply), false)
})

test('worklet đổi 48 kHz về gói PCM16 16 kHz 50 ms', () => {
  const posted = []
  const sandbox = {
    sampleRate: 48_000,
    AudioWorkletProcessor: class { port = { postMessage: (buffer) => posted.push(new Int16Array(buffer)) } },
    registerProcessor: (name, Processor) => { sandbox.processor = new Processor() },
  }
  vm.runInNewContext(WORKLET, sandbox)
  for (let block = 0; block < 4800 / 128 + 1; block++) {
    sandbox.processor.process([[new Float32Array(128).fill(0.5)]])
  }
  assert.equal(posted.length, 2)
  assert.equal(posted[0].length, 800)
  assert.equal(posted[0][0], Math.trunc(0.5 * 32767))
})

/* ---------- Phiên hội thoại ---------- */
test('âm thanh trước khi socket mở được giữ lại và gửi đi theo thứ tự', async () => {
  const { log, socket } = await session('en')
  assert.deepEqual(log.states, ['connecting', 'listening'])
  assert.match(socket.url, /^wss:\/\/stt\.test/)
  chunk(); chunk()
  assert.equal(socket.sent.length, 0)
  socket.open()
  chunk()
  assert.equal(socket.sent.length, 3)
  assert.deepEqual(Object.keys(socket.sent[0]).sort(), ['audio_base_64', 'commit', 'message_type', 'sample_rate'])
  assert.equal(socket.sent[0].sample_rate, 16000)
  assert.equal(socket.sent[0].audio_base_64.length, Math.ceil(1600 / 3) * 4)
})

test('câu đủ ý: gửi ngay khi server chốt, không chờ thêm', async () => {
  const { log, socket } = await session()
  socket.open()
  socket.emit({ message_type: 'partial_transcript', text: 'Phòng 4' })
  assert.equal(log.heard.at(-1), 'Phòng 4')
  socket.emit({ message_type: 'committed_transcript', text: 'Phòng 4-053.' })
  assert.deepEqual(log.said, [['Phòng 4-053.', false]])
  assert.equal(log.states.at(-1), 'waiting')
})

test('khách ngập ngừng giữa câu: đợi nói hết rồi mới gửi cả câu', async () => {
  const { log, socket } = await session()
  socket.open()
  socket.emit({ message_type: 'committed_transcript', text: 'Cho tôi hỏi.' })
  mock.timers.tick(HOLD_MS - 100)
  assert.deepEqual(log.said, [])
  socket.emit({ message_type: 'partial_transcript', text: 'phòng siêu' })
  mock.timers.tick(HOLD_MS * 2) // vẫn đang nói (chưa chốt) → không gửi
  assert.deepEqual(log.said, [])
  socket.emit({ message_type: 'committed_transcript', text: 'phòng siêu âm vú.' })
  assert.deepEqual(log.said, [['Cho tôi hỏi. phòng siêu âm vú.', false]])
})

test('hết giờ chờ câu dở nhưng mic còn tiếng khách (chữ chưa về): chưa gửi', async () => {
  const { log, socket } = await session()
  socket.open()
  socket.emit({ message_type: 'committed_transcript', text: 'Cho tôi hỏi' })
  mock.timers.tick(HOLD_MS - 200)
  for (let i = 0; i < 20; i++) { // khách nói tiếp 1 giây, STT chưa trả chữ
    chunk(0.2)
    mock.timers.tick(50)
  }
  assert.deepEqual(log.said, [])
  mock.timers.tick(400) // im → gửi
  assert.deepEqual(log.said, [['Cho tôi hỏi', false]])
})

test('câu dở mà khách không nói thêm: gửi sau thời gian chờ; tiếng đệm không gửi', async () => {
  const { log, socket } = await session()
  socket.open()
  socket.emit({ message_type: 'committed_transcript', text: 'Ờ.' })
  mock.timers.tick(HOLD_MS)
  assert.deepEqual(log.said, [])
  socket.emit({ message_type: 'committed_transcript', text: 'Nhà thuốc ở' })
  mock.timers.tick(HOLD_MS - 1)
  assert.deepEqual(log.said, [])
  mock.timers.tick(1)
  assert.deepEqual(log.said, [['Nhà thuốc ở', false]])
})

test('khách nói tiếp khi kiosk đang tìm: hủy yêu cầu, không đọc đè, gộp câu', async () => {
  const { talk, log, socket } = await session()
  socket.open()
  socket.emit({ message_type: 'committed_transcript', text: 'Phòng siêu âm' })
  assert.equal(log.states.at(-1), 'waiting')
  socket.emit({ message_type: 'partial_transcript', text: 'vú' })
  assert.equal(log.interrupts, 1)
  assert.equal(log.heard.at(-1), 'Phòng siêu âm vú')
  // Kết quả câu cũ về muộn → không được đọc.
  assert.equal(talk.speak('/speech?a', 'Không tìm thấy'), false)
  assert.equal(speechFetches.length, 0)
  socket.emit({ message_type: 'committed_transcript', text: 'vú.' })
  assert.deepEqual(log.said.at(-1), ['Phòng siêu âm vú.', true])
})

test('kiosk đang đọc: tiếng vọng không ngắt, khách lên tiếng thì im ngay', async () => {
  const { talk, log, socket } = await session()
  socket.open()
  socket.emit({ message_type: 'committed_transcript', text: 'Khoa tim mạch' })
  const reply = 'Để đến Trung tâm Tim mạch, mã 3-01, tầng 3, anh chị đi theo hướng dẫn sau.'
  assert.equal(talk.speak('/speech?b', reply), true)
  await load()
  assert.equal(log.states.at(-1), 'speaking')
  assert.equal(sources.length, 2)
  // 2401 + 2400 byte → 1200 + 1200 mẫu (byte lẻ được ghép sang gói sau), phát nối tiếp.
  assert.ok(Math.abs(sources[1].at - sources[0].at - 1200 / 24000) < 1e-9)
  assert.equal(sources[0].buffer.length + sources[1].buffer.length, 2400)
  socket.emit({ message_type: 'partial_transcript', text: 'Để đến trung tâm tim mạch' })
  assert.equal(sources[0].stopped, undefined)
  assert.equal(log.interrupts, 0)
  mock.timers.tick(CONTINUE_MS + 1) // quá cửa sổ nói tiếp → câu mới, không gộp
  socket.emit({ message_type: 'partial_transcript', text: 'Còn nhà thuốc thì sao' })
  assert.equal(sources.every((source) => source.stopped), true)
  assert.equal(log.states.at(-1), 'listening')
  socket.emit({ message_type: 'committed_transcript', text: 'Còn nhà thuốc thì sao?' })
  assert.deepEqual(log.said.at(-1), ['Còn nhà thuốc thì sao?', false])
})

test('mic còn tiếng khách: câu trả lời chờ, chỉ cất lời khi khách im đủ lâu', async () => {
  const { talk, log, socket } = await session()
  socket.open()
  socket.emit({ message_type: 'committed_transcript', text: 'Nhà thuốc' })
  talk.speak('/speech?d', 'Nhà thuốc ở tầng 3.')
  chunk(0.2) // khách "ừm" ngay khi câu trả lời đang tải
  await load()
  for (let i = 0; i < 30; i++) { // khách còn "ừm…" thành tiếng 1.5 giây, chưa ra chữ
    chunk(0.2)
    mock.timers.tick(50)
    await flush()
  }
  assert.equal(sources.length, 0)
  assert.equal(log.states.at(-1), 'waiting')
  mock.timers.tick(QUIET_MS - 100)
  await flush()
  assert.equal(sources.length, 0)
  mock.timers.tick(150)
  await flush(); await flush()
  assert.equal(log.states.at(-1), 'speaking')
  assert.equal(sources.length, 2)
})

test('server chốt câu khi mic vẫn còn tiếng khách: không gửi, đợi phần sau', async () => {
  const { log, socket } = await session()
  socket.open()
  chunk(0.2)
  socket.emit({ message_type: 'committed_transcript', text: 'Phòng bốn.' })
  assert.deepEqual(log.said, [])
  mock.timers.tick(400) // khách nói tiếp rồi im; chữ của phần sau về sau
  socket.emit({ message_type: 'committed_transcript', text: 'không năm ba ở đâu?' })
  assert.deepEqual(log.said, [['Phòng bốn. không năm ba ở đâu?', false]])
})

test('trả lời đã tải xong nhưng khách nói tiếp: bỏ, không phát, gộp câu', async () => {
  const { talk, log, socket } = await session()
  socket.open()
  socket.emit({ message_type: 'committed_transcript', text: 'Cho tôi đến nhà thuốc' })
  assert.equal(talk.speak('/speech?e', 'Để đến Nhà thuốc, anh chị đi thẳng.'), true)
  chunk(0.2) // khách nói tiếp; chữ tạm về sau ~0.7 giây
  await load()
  assert.equal(sources.length, 0)
  mock.timers.tick(700)
  socket.emit({ message_type: 'partial_transcript', text: 'à không, phòng 4053' })
  assert.equal(log.interrupts, 1)
  mock.timers.tick(QUIET_MS * 2)
  await load()
  assert.equal(sources.length, 0)
  socket.emit({ message_type: 'committed_transcript', text: 'À không, phòng 4053.' })
  assert.deepEqual(log.said.at(-1), ['Cho tôi đến nhà thuốc À không, phòng 4053.', true])
})

test('đọc xong thì nghe tiếp; câu vọng tới muộn vẫn bị lọc', async () => {
  const { talk, log, socket } = await session()
  socket.open()
  socket.emit({ message_type: 'committed_transcript', text: 'Nhà thuốc' })
  talk.speak('/speech?c', 'Nhà thuốc ở tầng 3, anh chị đi thẳng.')
  await load()
  assert.equal(log.states.at(-1), 'speaking')
  mock.timers.tick(200) // phát hết 0.1 giây âm thanh
  await flush()
  assert.equal(log.states.at(-1), 'listening')
  socket.emit({ message_type: 'committed_transcript', text: 'đi thẳng' })
  assert.equal(log.said.length, 1)
})

test('server không chốt câu: tự gửi phần đã nghe, bỏ lần chốt trễ', async () => {
  const { log, socket } = await session()
  socket.open()
  socket.emit({ message_type: 'partial_transcript', text: 'Quầy thanh toán' })
  mock.timers.tick(4000)
  assert.deepEqual(log.said, [['Quầy thanh toán', false]])
  socket.emit({ message_type: 'committed_transcript', text: 'Quầy thanh toán.' })
  assert.equal(log.said.length, 1)
})

test('im lặng lâu thì tắt mic và đóng socket', async () => {
  const { log, socket } = await session()
  socket.open()
  mock.timers.tick(IDLE_MS)
  assert.equal(log.states.at(-1), 'off')
  assert.equal(socket.closed, true)
  assert.equal(tracks[0].stopped, true)
  assert.deepEqual(log.errors, [])
})

test('lỗi: mất kết nối, server chưa cấu hình, dừng khi đang xin mic', async () => {
  let { log, socket } = await session()
  socket.open()
  socket.onclose()
  assert.deepEqual(log.errors, ['connection'])
  assert.equal(tracks[0].stopped, true)

  tokenResponse = { ok: false, status: 503, json: async () => ({ detail: 'x' }) }
  ;({ log } = await session())
  await flush()
  assert.deepEqual(log.errors, ['liveUnconfigured'])

  tokenResponse = { ok: true, status: 200, json: async () => ({ url: 'wss://x' }) }
  ;({ log, socket } = await session())
  socket.open()
  socket.emit({ message_type: 'quota_exceeded', error: 'quota' })
  assert.deepEqual(log.errors, ['connection'])

  let release
  micGate = new Promise((done) => { release = done })
  const talk = createConversation({ language: 'vi', onState() {}, onHeard() {}, onUtterance() {}, onInterrupt() {}, onError() {} })
  const starting = talk.start()
  talk.stop()
  release()
  await starting
  assert.equal(tracks.at(-1).stopped, true)
})
