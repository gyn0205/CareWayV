// Hội thoại giọng nói realtime: mic → Scribe Realtime (WebSocket, trình duyệt nói thẳng tới ElevenLabs)
// → câu hoàn chỉnh → App tìm đường → đọc trả lời bằng TTS stream. Không ngắt lời khách:
// câu trả lời được chuẩn bị ngay khi STT chốt câu (để nhanh), nhưng chỉ cất lời khi mic đo thấy khách
// đã im đủ lâu; câu còn dở thì chờ thêm; khách nói tiếp thì bỏ câu trả lời, gộp câu và hỏi lại.
import { requestRealtime } from './api.js'

const SAMPLE_RATE = 16_000
// Giọng đọc trả về PCM16 24 kHz (/speech?format=pcm).
const SPEECH_RATE = 24_000
// 50 ms mỗi gói: đủ nhỏ để server thấy khoảng lặng sớm, đủ lớn để không nghẽn socket.
const CHUNK_SAMPLES = 800
// Câu nghe còn dở ("cho tôi hỏi…", "phòng…") → chờ thêm chừng này cho khách nói nốt.
export const HOLD_MS = 1500
// Khách nói tiếp trong khoảng này sau khi câu trước đã gửi → coi là cùng một câu, gộp lại hỏi lại.
export const CONTINUE_MS = 3000
// Không có câu chốt sau chừng này kể từ chữ tạm cuối cùng (server lỡ chốt) → tự chốt.
const STALL_MS = 4000
// Kiosk chỉ cất lời khi mic đo thấy khách đã im liền chừng này (không chen vào lúc khách ngập ngừng).
export const QUIET_MS = 1200
// Mic còn tiếng người trong chừng này → khách đang nói dở, lần chốt câu của server là quá sớm.
const TALKING_MS = 300
// Ồn liên tục không đo được khoảng im → chờ tối đa chừng này rồi vẫn trả lời.
const MAX_QUIET_WAIT_MS = 4000
// Ngưỡng RMS (0..1) tối thiểu coi là tiếng người; ngưỡng thật tự nâng theo tiếng ồn nền.
const VOICE_RMS = 0.01
// Server chốt câu sau khoảng lặng → câu vọng có thể tới ngay sau khi kiosk đọc xong; vẫn lọc thêm chừng này.
const ECHO_TAIL_MS = 1500
// Không ai nói trong khoảng này → tắt mic (riêng tư + chi phí).
export const IDLE_MS = 20_000
// Gói âm thanh giữ lại khi socket chưa mở (~10 giây) để không mất mấy chữ đầu.
const MAX_PENDING = 200

const FILLERS = new Set(['ờ', 'ơ', 'à', 'ừ', 'ừm', 'ưm', 'hmm', 'hm', 'um', 'uh', 'ah', 'er', 'erm', 'mm'])
// Chữ cuối kiểu này nghĩa là câu chưa xong. Không đưa vào các chữ hay đứng cuối câu trọn vẹn
// ("chỉ đường cho tôi", "… đi", "please", "which floor is it on").
const DANGLING = new Set([
  'ở', 'tới', 'đến', 'vào', 'của', 'phòng', 'khoa', 'tầng', 'mã', 'số', 'cho', 'hỏi', 'là', 'và', 'với', 'thì',
  'để', 'muốn', 'cần', 'chỗ', 'nơi', 'trung', 'tâm', 'quầy', 'khu', 'tìm', 'xin',
  'the', 'to', 'of', 'room', 'floor', 'where', 'is', 'and', 'for', 'a', 'an', 'at', 'go', 'my',
  'i', 'need', 'want', 'looking', 'find', 'department', 'number', 'code',
])
const DIGIT_WORDS = new Set([
  'không', 'một', 'mốt', 'hai', 'ba', 'bốn', 'tư', 'năm', 'lăm', 'sáu', 'bảy', 'tám', 'chín', 'mười', 'mươi',
  'zero', 'oh', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten',
])

const words = (text) => text.toLowerCase().normalize('NFC').match(/[\p{L}\p{N}]+/gu) ?? []
const join = (...parts) => parts.filter(Boolean).join(' ')

// Có chữ nào ngoài tiếng đệm ("ờ", "à") không.
export const meaningful = (text) => words(text).some((word) => !FILLERS.has(word))

export function looksUnfinished(text) {
  const list = words(text).filter((word) => !FILLERS.has(word))
  return !list.length || DANGLING.has(list.at(-1)) || /(\.\.\.|…|,|-)\s*$/.test(text)
}

// Mic thu lại chính giọng kiosk đang đọc? Ít hơn 1/3 chữ mới so với câu đang đọc → coi là tiếng vọng.
// Chữ số bỏ qua vì STT có thể đọc "4-053" thành "bốn không năm ba".
export function isEcho(heard, spoken) {
  const said = new Set(words(spoken))
  const list = words(heard).filter((word) => !FILLERS.has(word) && !DIGIT_WORDS.has(word) && !/^\d+$/.test(word))
  return list.filter((word) => !said.has(word)).length * 3 < list.length || !list.length
}

// Chạy trong luồng âm thanh: gộp trung bình về 16 kHz, đổi sang PCM16, gửi từng gói 50 ms.
export const WORKLET = `
class MicPcm extends AudioWorkletProcessor {
  constructor() {
    super()
    this.step = sampleRate / ${SAMPLE_RATE}
    this.pos = 0; this.sum = 0; this.count = 0; this.index = 0
    this.out = new Int16Array(${CHUNK_SAMPLES})
  }
  process([input]) {
    const data = input[0]
    if (!data) return true
    for (let k = 0; k < data.length; k++) {
      this.sum += data[k]; this.count++; this.pos++
      if (this.pos < this.step) continue
      this.pos -= this.step
      this.out[this.index++] = Math.max(-1, Math.min(1, this.sum / this.count)) * 32767
      this.sum = 0; this.count = 0
      if (this.index === this.out.length) {
        this.port.postMessage(this.out.buffer, [this.out.buffer])
        this.out = new Int16Array(${CHUNK_SAMPLES}); this.index = 0
      }
    }
    return true
  }
}
registerProcessor('mic-pcm', MicPcm)`

function base64(buffer) {
  const bytes = new Uint8Array(buffer)
  let binary = ''
  for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i])
  return btoa(binary)
}

export const supportsConversation = () => Boolean(
  navigator.mediaDevices?.getUserMedia && window.AudioWorkletNode && window.WebSocket,
)

/**
 * Một phiên hội thoại. Callback:
 * onState('connecting'|'listening'|'waiting'|'speaking'|'off'), onHeard(chữ khách đang nói),
 * onUtterance(câu đã nói xong, continuation = gộp với câu vừa gửi), onInterrupt() khi khách nói tiếp
 * trong lúc kiosk đang xử lý câu trước, onError(khóa lỗi trong copy.js).
 */
export function createConversation({ language, onState, onHeard, onUtterance, onInterrupt, onError }) {
  let state = 'off'
  let closed = false
  let socket
  let stream
  let context
  let audio
  let pending = []
  let buffer = '' // các đoạn server đã chốt của câu đang nói
  let partial = '' // đoạn đang nói dở (còn thay đổi)
  let carry = '' // câu trước đã gửi, khi khách nói tiếp thì gộp vào
  let last // { text, at } câu gửi gần nhất
  let spoken = '' // câu kiosk đang đọc, để lọc tiếng vọng
  let spokenUntil = 0
  let skipCommit = false
  let lastVoiceAt = -Infinity // lần cuối mic nghe tiếng người (đo tại máy, không trễ như chữ tạm của STT)
  let noise = 0 // mức ồn nền ước lượng
  let holdTimer
  let idleTimer

  const set = (value) => {
    state = value
    onState(value)
  }
  const show = () => onHeard(join(carry, buffer, partial))

  function armIdle() {
    clearTimeout(idleTimer)
    idleTimer = setTimeout(() => {
      if (state === 'listening' && !buffer && !partial && !carry) stop()
      else armIdle()
    }, IDLE_MS)
  }

  const talkingNow = () => Date.now() - lastVoiceAt < TALKING_MS

  // Đo năng lượng từng gói 50 ms; ồn nền theo mức thấp nhất, tăng chậm để không nuốt mất tiếng người.
  function measure(chunk) {
    const samples = new Int16Array(chunk)
    let sum = 0
    for (let i = 0; i < samples.length; i++) sum += samples[i] * samples[i]
    const rms = Math.sqrt(sum / samples.length) / 32768
    if (rms > Math.max(VOICE_RMS, noise * 3)) lastVoiceAt = Date.now()
    noise = rms < noise ? rms : noise + (rms - noise) * 0.002
  }

  // Chờ tới khi khách im liền QUIET_MS (tối đa MAX_QUIET_WAIT_MS).
  function quiet() {
    const until = Date.now() + MAX_QUIET_WAIT_MS
    return new Promise((done) => {
      const check = () => {
        const wait = QUIET_MS - (Date.now() - lastVoiceAt)
        if (wait <= 0 || Date.now() >= until) done()
        else setTimeout(check, Math.max(10, Math.min(wait, until - Date.now())))
      }
      check()
    })
  }

  function stopAudio() {
    if (!audio) return
    if (audio.started) spokenUntil = Date.now() + ECHO_TAIL_MS
    audio.controller.abort() // hủy luồng TTS đang tải
    audio.sources.forEach((source) => source.stop())
    audio = undefined
  }

  // Phát từng gói PCM ngay khi về: thẻ <audio> đệm ~2-3 giây MP3 rồi mới phát, chậm hơn ~0.4 giây.
  async function play(reply, url) {
    const response = await fetch(url, { signal: reply.controller.signal })
    if (!response.ok || !response.body) throw new Error(`speech ${response.status}`)
    const reader = response.body.getReader()
    let at = 0
    let odd // byte lẻ của mẫu 16-bit bị cắt giữa hai gói
    for (;;) {
      const { done, value } = await reader.read()
      if (done || audio !== reply) break
      let bytes = value
      if (odd !== undefined) {
        bytes = new Uint8Array(value.length + 1)
        bytes[0] = odd
        bytes.set(value, 1)
      }
      const count = bytes.length >> 1
      odd = bytes.length % 2 ? bytes[bytes.length - 1] : undefined
      if (!count) continue
      if (!reply.started) {
        // Câu trả lời đã sẵn sàng nhưng chỉ cất lời khi khách đã im đủ lâu.
        await quiet()
        if (audio !== reply) break
        reply.started = true
        set('speaking')
      }
      const view = new DataView(bytes.buffer, bytes.byteOffset, count * 2)
      const buffer = context.createBuffer(1, count, SPEECH_RATE)
      const channel = buffer.getChannelData(0)
      for (let i = 0; i < count; i++) channel[i] = view.getInt16(i * 2, true) / 32768
      const source = context.createBufferSource()
      source.buffer = buffer
      source.connect(context.destination)
      // Xếp nối tiếp; gói về trễ thì phát ngay khi tới.
      at = Math.max(at, context.currentTime + 0.02)
      source.start(at)
      at += buffer.duration
      reply.sources.add(source)
      source.onended = () => reply.sources.delete(source)
    }
    // Đợi phát hết phần đã xếp lịch rồi mới coi là đọc xong.
    if (audio === reply) await new Promise((done) => setTimeout(done, Math.max(0, at - context.currentTime) * 1000))
  }

  // Hết giờ chờ câu dở: chỉ gửi khi mic đã im (chữ tạm của STT về trễ hơn tiếng thật ~0.7 giây).
  function settle(since = Date.now()) {
    if (talkingNow() && Date.now() - since < MAX_QUIET_WAIT_MS) holdTimer = setTimeout(() => settle(since), TALKING_MS)
    else flush()
  }

  // Khách đã nói xong: gửi cả câu (gồm câu trước nếu đang nói tiếp).
  function flush() {
    clearTimeout(holdTimer)
    const text = join(carry, buffer, partial)
    const continuation = Boolean(carry)
    buffer = partial = carry = ''
    show()
    if (!meaningful(text)) return
    last = { text, at: Date.now() }
    set('waiting')
    onUtterance(text, continuation)
  }

  function heard(text, committed) {
    if ((state === 'speaking' || Date.now() < spokenUntil) && isEcho(text, spoken)) return
    // Khách lên tiếng → kiosk im ngay (hoặc bỏ câu trả lời đang chờ phát), nhường lời.
    stopAudio()
    if (state === 'speaking') set('listening')
    // Khách nói tiếp ngay sau câu vừa gửi (hoặc khi kiosk còn đang tìm) → câu trước chưa xong, gộp lại.
    if (!buffer && !partial && !carry && last && (state === 'waiting' || Date.now() - last.at < CONTINUE_MS)) {
      carry = last.text
      last = undefined
      if (state === 'waiting') set('listening')
      onInterrupt()
    }
    clearTimeout(holdTimer)
    if (committed) {
      buffer = join(buffer, text)
      partial = ''
      if (looksUnfinished(buffer) || talkingNow()) holdTimer = setTimeout(settle, HOLD_MS)
      else flush()
    } else {
      partial = text
      holdTimer = setTimeout(() => {
        skipCommit = true
        flush()
      }, STALL_MS)
    }
    if (state !== 'off') show()
    armIdle()
  }

  function receive(event) {
    let message
    try {
      message = JSON.parse(event.data)
    } catch {
      return
    }
    const type = message.message_type
    const text = typeof message.text === 'string' ? message.text.trim() : ''
    if (type === 'partial_transcript') {
      if (text) heard(text, false)
    } else if (type === 'committed_transcript') {
      if (skipCommit) {
        skipCommit = false
        return
      }
      if (text) heard(text, true)
      // Chốt rỗng mà còn câu dở (vd. khách chỉ "ờ") → xét lại có gửi được chưa.
      else if ((buffer || carry) && state !== 'speaking') {
        clearTimeout(holdTimer)
        if (looksUnfinished(join(carry, buffer)) || talkingNow()) holdTimer = setTimeout(settle, HOLD_MS)
        else flush()
      }
    } else if (type === 'session_time_limit_exceeded' || type === 'insufficient_audio_activity') {
      stop()
    } else if (type !== 'session_started' && (type?.endsWith('error') || 'error' in message)) {
      console.warn('Realtime STT:', type, message.error)
      fail('connection')
    }
  }

  function send(chunk) {
    measure(chunk)
    const payload = JSON.stringify({
      message_type: 'input_audio_chunk', audio_base_64: base64(chunk), commit: false, sample_rate: SAMPLE_RATE,
    })
    if (socket?.readyState === WebSocket.OPEN) socket.send(payload)
    else if (pending.length < MAX_PENDING) pending.push(payload)
  }

  function fail(key) {
    if (closed) return
    stop()
    onError(key)
  }

  async function start() {
    set('connecting')
    // Xin token song song với mở mic để rút ngắn thời gian chờ.
    const session = requestRealtime(language)
    session.catch(() => {})
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      })
      if (closed) return release()
      context = new AudioContext()
      const module = URL.createObjectURL(new Blob([WORKLET], { type: 'text/javascript' }))
      try {
        await context.audioWorklet.addModule(module)
      } finally {
        URL.revokeObjectURL(module)
      }
      if (closed) return release()
      const node = new AudioWorkletNode(context, 'mic-pcm', { numberOfInputs: 1, numberOfOutputs: 0 })
      node.port.onmessage = (event) => send(event.data)
      context.createMediaStreamSource(stream).connect(node)
      await context.resume()
    } catch {
      return fail('micError')
    }
    // Mic đã thu (âm thanh được giữ lại) → khách nói được ngay, không phải đợi socket.
    set('listening')
    armIdle()
    let url
    try {
      ({ url } = await session)
    } catch (error) {
      return fail(error.status === 503 ? 'liveUnconfigured' : 'connection')
    }
    if (closed) return
    socket = new WebSocket(url)
    socket.onopen = () => {
      pending.forEach((payload) => socket.send(payload))
      pending = []
    }
    socket.onmessage = receive
    socket.onclose = () => fail('connection')
  }

  // Tải trước câu trả lời (URL PCM stream), phát khi khách đã im. Trả về false nếu khách đã nói tiếp.
  function speak(url, text) {
    if (closed || state !== 'waiting') return false
    stopAudio()
    spoken = text
    const reply = audio = { controller: new AbortController(), sources: new Set(), started: false }
    const finish = () => {
      if (audio !== reply) return
      audio = undefined
      if (reply.started) spokenUntil = Date.now() + ECHO_TAIL_MS
      if (state === 'speaking' || state === 'waiting') set('listening')
      armIdle()
    }
    play(reply, url).then(finish, finish)
    return true
  }

  // Câu trả lời không có giọng đọc (lỗi, hoặc khách bấm thay vì nói) → nghe tiếp.
  function done() {
    if (state === 'waiting') set('listening')
    armIdle()
  }

  function hush() {
    stopAudio()
    if (state === 'speaking' || state === 'waiting') set('listening')
    armIdle()
  }

  function stop() {
    if (closed) return
    closed = true
    clearTimeout(holdTimer)
    clearTimeout(idleTimer)
    stopAudio()
    if (socket) {
      socket.onclose = socket.onmessage = null
      socket.close()
    }
    release()
    pending = []
    onHeard('')
    set('off')
  }

  // Tắt mic và luồng âm thanh (cũng dùng khi phiên đã dừng trong lúc đang xin mic).
  function release() {
    stream?.getTracks().forEach((track) => track.stop())
    context?.close().catch(() => {})
    stream = context = undefined
  }

  return { start, speak, done, hush, stop }
}
