<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  Accessibility, ArrowRight, ChevronDown, CircleAlert, Compass, HeartPulse, Info, MapPin, Pill, Stethoscope, Volume2,
  WalletCards,
} from '@lucide/vue'
import { audioBase64, replyUrl, requestDirections, requestKioskMap, speechUrl } from './api'
import { copy } from './copy'
import { MAX_AUDIO_BYTES } from './recording'
import { createConversation, supportsConversation } from './realtime'
import RouteDiagram from './components/RouteDiagram.vue'
import RoutePanel from './components/RoutePanel.vue'
import VoiceInput from './components/VoiceInput.vue'

// ?kiosk=… cài vị trí cho từng màn khi lắp đặt; ?q=… hỏi sẵn; ?demo=1 tự chạy cho trang giới thiệu.
const params = new URLSearchParams(location.search)
const DEMO = params.get('demo') === '1'
const IDLE_SECONDS = 60
// Câu trả lời "chỉ đường tới quầy tư vấn" khi không tìm thấy (mã khu quầy lễ tân – tư vấn).
const DESK_CODE = '4-14'

const language = ref('vi')
// 4 kiosk = 4 bảng sơ đồ: mỗi tầng một bảng cạnh thang máy A và một bảng cạnh thang máy B.
const kiosks = [
  { code: 'KIOSK-4', floor: 4, lift: 'B' },
  { code: 'KIOSK-4-A', floor: 4, lift: 'A' },
  { code: 'KIOSK-3', floor: 3, lift: 'B' },
  { code: 'KIOSK-3-A', floor: 3, lift: 'A' },
]
const kioskCode = ref(kiosks.some(({ code }) => code === params.get('kiosk')) ? params.get('kiosk') : 'KIOSK-4')
const kiosk = computed(() => kiosks.find(({ code }) => code === kioskCode.value))
const kioskFloor = computed(() => kiosk.value.floor)
const kioskMap = ref(null)
const mapProblem = ref(false)
const wheelchair = ref(false)
const query = ref('')
const result = ref(null)
const busy = ref(false)
const problem = ref('')
const audioUrl = ref('')
const voiceActive = ref(false)
const voiceKey = ref(0)
// Trò chuyện realtime (mặc định); tắt khi máy chủ chưa có STT realtime → lùi về bấm để nói.
const liveVoice = ref(supportsConversation())
const talk = ref('off')
const heard = ref('')
// Câu khách đã hỏi (nối các câu trả lời bổ sung bằng "→" để thấy mạch hội thoại).
const said = ref('')
// Câu gần nhất đến từ giọng nói → hiện "Tôi nghe:" để khách thấy ngay khi kiosk nghe sai.
const saidByVoice = ref(false)
const activeStep = ref(-1)
const walkDone = ref(false)
const idleLeft = ref(IDLE_SECONDS)
const now = ref(new Date())
const diagram = ref(null)
const labels = computed(() => copy[language.value])
const inputLocked = computed(() => busy.value || voiceActive.value)
const mode = computed(() => busy.value ? 'busy' : result.value ? 'result' : 'idle')
// Ứng viên đang hỏi lại → tô trên bản đồ.
const candidates = computed(() => result.value?.status === 'clarify' ? result.value.candidates : [])
const iconMap = { heart: HeartPulse, wallet: WalletCards, pill: Pill, clinic: Stethoscope }
const clock = computed(() => `${String(now.value.getHours()).padStart(2, '0')}:${String(now.value.getMinutes()).padStart(2, '0')}`)
let activeRequest
let mapRequest
let mapRetry
let lastTurn
let idleTimer
let clockTimer
let conversation
// Ngữ cảnh của câu nói gần nhất: khách nói tiếp thì gộp câu và hỏi lại trên đúng ngữ cảnh đó.
let spokenTurn

// Lối tắt hiển thị tên theo ngôn ngữ đang chọn, kèm tên ở ngôn ngữ còn lại như prototype.
const shortcuts = computed(() => labels.value.choices.map((choice, index) => ({
  ...choice, alt: copy[language.value === 'vi' ? 'en' : 'vi'].choices[index].label,
})))

function clearAudio() {
  if (audioUrl.value) URL.revokeObjectURL(audioUrl.value)
  audioUrl.value = ''
}

function reset() {
  activeRequest?.abort()
  activeRequest = undefined
  lastTurn = undefined
  busy.value = false
  result.value = null
  problem.value = ''
  query.value = ''
  said.value = ''
  saidByVoice.value = false
  voiceActive.value = false
  voiceKey.value++
  stopTalk()
  clearAudio()
  try { speechSynthesis.cancel() } catch { /* không hỗ trợ giọng đọc */ }
}

async function loadKioskMap() {
  clearTimeout(mapRetry)
  mapRequest?.abort()
  const controller = mapRequest = new AbortController()
  kioskMap.value = null
  mapProblem.value = false
  try {
    const data = await requestKioskMap(kioskCode.value, language.value, controller.signal)
    if (mapRequest === controller) kioskMap.value = data
  } catch {
    if (mapRequest !== controller) return
    mapProblem.value = true
    // Kiosk có thể bật trước khi API sẵn sàng → tự thử lại.
    mapRetry = setTimeout(() => mapRequest === controller && loadKioskMap(), 10000)
  }
}

function stopTalk() {
  conversation?.stop()
}

function startTalk() {
  if (conversation || busy.value) return
  problem.value = ''
  const session = conversation = createConversation({
    language: language.value,
    onState(value) {
      if (conversation !== session) return
      talk.value = value
      if (value === 'off') conversation = undefined
    },
    onHeard(text) {
      if (conversation === session) heard.value = text
    },
    onUtterance: submitSpoken,
    // Khách nói tiếp khi kiosk đang tìm câu trước → bỏ yêu cầu đó, chờ câu đầy đủ.
    onInterrupt() {
      activeRequest?.abort()
      activeRequest = undefined
      busy.value = false
    },
    onError(key) {
      if (key === 'liveUnconfigured') liveVoice.value = false
      showProblem(key)
    },
  })
  session.start()
}

function submitSpoken(text, continuation) {
  // Giọng khách là ý mới nhất → thay cho yêu cầu (gõ / bấm) đang chạy.
  if (busy.value) {
    activeRequest?.abort()
    activeRequest = undefined
    busy.value = false
  }
  if (!continuation || !spokenTurn) {
    const context = contextFor(false)
    spokenTurn = { context, saidBase: context ? said.value : '' }
  }
  submit('text', () => ({ text }), spokenTurn.context, spokenTurn.saidBase, { text, shown: text }, true)
}

watch(kioskCode, () => {
  reset()
  loadKioskMap()
})

// Đổi ngôn ngữ giữa chừng: hỏi lại đúng câu cũ bằng ngôn ngữ mới thay vì xoá kết quả.
watch(language, (value) => {
  document.documentElement.lang = value
  // STT realtime nghe theo một ngôn ngữ → đổi ngôn ngữ thì khách bấm mic lại.
  stopTalk()
  problem.value = ''
  if (result.value && lastTurn && !inputLocked.value) {
    const { text, shown, context, saidBase } = lastTurn
    submit('text', () => ({ text }), context, saidBase, { text, shown })
  }
}, { immediate: true })

function showProblem(key) {
  problem.value = labels.value[key]
}

const join = (base, text) => base && text ? `${base} → ${text}` : base || text || ''

function contextFor(newSearch) {
  return !newSearch && result.value?.context ? { ...result.value.context, wheelchair: wheelchair.value } : null
}

// saidBase: phần hội thoại trước đó; turn.text: câu gửi đi, turn.shown: chữ hiện cho khách.
// Giọng nói thì chỉ biết câu sau khi có bản chép lời.
// spoken: câu đến từ hội thoại realtime → đọc câu trả lời bằng TTS stream.
async function submit(kind, prepare, context, saidBase, turn = {}, spoken = false) {
  if (busy.value) return
  // Khách bấm / gõ trong lúc kiosk đang đọc → im để khỏi đọc câu cũ.
  if (!spoken) conversation?.hush()
  const controller = new AbortController()
  activeRequest = controller
  const payload = {
    kiosk_code: kioskCode.value,
    wheelchair: wheelchair.value,
    language: language.value,
    context,
  }
  const saidBefore = said.value
  const byVoiceBefore = saidByVoice.value
  said.value = join(saidBase, turn.shown)
  saidByVoice.value = spoken || kind === 'voice'
  problem.value = ''
  clearAudio()
  busy.value = true
  try {
    const answer = await requestDirections(kind, { ...payload, ...await prepare() }, controller.signal)
    if (controller.signal.aborted) return
    const text = turn.text ?? answer.transcript
    const shown = turn.shown ?? answer.transcript
    said.value = join(saidBase, shown)
    // Nhớ câu vừa hỏi để hỏi lại khi khách đổi ngôn ngữ.
    lastTurn = text ? { text, shown, context, saidBase } : undefined
    result.value = answer
    walkDone.value = false
    wheelchair.value = answer.context?.wheelchair ?? wheelchair.value
    query.value = ''
    if (spoken) {
      // false: khách đã nói tiếp → không đọc đè, câu gộp sẽ được hỏi lại.
      if (conversation?.speak(speechUrl(answer.message, answer.language, 'pcm'), answer.message)) {
        audioUrl.value = speechUrl(answer.message, answer.language)
      }
    } else if (answer.audio_base64) {
      try {
        audioUrl.value = replyUrl(answer.audio_base64, answer.audio_media_type)
      } catch {
        result.value = { ...answer, speech_status: 'unavailable' }
      }
    }
  } catch (error) {
    if (controller.signal.aborted) return
    if (spoken) conversation?.done()
    said.value = saidBefore
    saidByVoice.value = byVoiceBefore
    if (kind === 'voice' && error.status === 503) {
      showProblem('voiceUnavailable')
    } else {
      problem.value = error.status && error.message ? error.message : labels.value.connection
    }
  } finally {
    if (activeRequest === controller) {
      activeRequest = undefined
      busy.value = false
    }
  }
}

// shown: chữ hiện trong bong bóng "Bạn hỏi" (vd. tên lối tắt thay cho mã phòng).
function submitText(value = query.value, newSearch = false, shown) {
  const text = value.trim()
  if (inputLocked.value || !text) return
  const context = contextFor(newSearch)
  submit('text', () => ({ text }), context, context ? said.value : '', { text, shown: shown || text })
}

function onVoiceActivity(active) {
  voiceActive.value = active
  if (active) problem.value = ''
}

function submitAudio(blob, format) {
  if (!blob.size || blob.size > MAX_AUDIO_BYTES) {
    showProblem('audioSize')
    return
  }
  const context = contextFor(false)
  submit('voice', async () => ({ audio_base64: await audioBase64(blob), format, speak: true }),
    context, context ? said.value : '')
}

function onProgress(step, done) {
  activeStep.value = step
  walkDone.value = done
}

/* ---------- Tự về màn hình chính khi không ai dùng ---------- */
const idleActive = computed(() => !DEMO && Boolean(result.value) && !inputLocked.value && talk.value === 'off')
watch(idleActive, (on) => {
  clearInterval(idleTimer)
  idleLeft.value = IDLE_SECONDS
  if (on) {
    idleTimer = setInterval(() => {
      idleLeft.value--
      if (idleLeft.value <= 0) reset()
    }, 1000)
  }
})
function stillHere() {
  idleLeft.value = IDLE_SECONDS
}

/* ---------- Chế độ demo (?demo=1): tự chạy vòng lặp cho trang giới thiệu ---------- */
const wait = (ms) => new Promise((done) => setTimeout(done, ms))
async function typeInto(text) {
  for (let index = 1; index <= text.length; index++) {
    query.value = text.slice(0, index)
    await wait(70)
  }
  await wait(350)
}
async function ask(text) {
  await typeInto(text)
  submitText()
  while (busy.value) await wait(100)
}
async function walked() {
  // Chờ người dẫn đường tới nơi (tối đa 40 giây) rồi dừng ngắm thêm một chút.
  for (let waited = 0; result.value?.route && !walkDone.value && waited < 40000; waited += 200) await wait(200)
  await wait(3200)
}
async function demoLoop() {
  for (;;) {
    await wait(1400)
    await ask('siêu âm vú')
    await wait(2600)
    if (result.value?.status === 'clarify') {
      await ask('3-093')
      // Phòng khám → kiosk hỏi đã đặt lịch chưa.
      if (result.value?.context?.pending === 'appointment') await ask('Đã đặt lịch')
      await walked()
    }
    reset()
    await wait(1200)
    await ask('Phòng 4-053 ở đâu?')
    await walked()
    reset()
  }
}

onMounted(() => {
  loadKioskMap()
  clockTimer = setInterval(() => { now.value = new Date() }, 15000)
  // Khách còn chạm / gõ → đếm lại thời gian tự quay về.
  document.addEventListener('pointerdown', stillHere, true)
  document.addEventListener('keydown', stillHere, true)
  if (DEMO) demoLoop()
  else if (params.get('q')) submitText(params.get('q'), true)
})

onBeforeUnmount(() => {
  activeRequest?.abort()
  mapRequest?.abort()
  clearTimeout(mapRetry)
  clearInterval(idleTimer)
  clearInterval(clockTimer)
  stopTalk()
  document.removeEventListener('pointerdown', stillHere, true)
  document.removeEventListener('keydown', stillHere, true)
  clearAudio()
})
</script>

<template>
  <header class="top">
    <div class="brand" aria-label="CareWayV">
      <span class="brand-mark"><Compass :size="26" :stroke-width="1.8" /></span>
      <div><b>CareWay<span>V</span></b><small>{{ labels.product }}</small></div>
    </div>
    <!-- Vị trí kiosk: cài sẵn qua ?kiosk=…, vẫn đổi được khi thử nghiệm -->
    <label class="here">
      <span class="dot"><MapPin :size="14" /></span>
      <span class="here-text">{{ labels.here }}</span>
      <select v-model="kioskCode" :aria-label="labels.kiosk">
        <option v-for="item in kiosks" :key="item.code" :value="item.code">
          {{ labels.kioskAt(item.floor, item.lift) }}
        </option>
      </select>
      <ChevronDown :size="15" aria-hidden="true" />
    </label>
    <div class="spacer"></div>
    <div class="clock">{{ clock }}</div>
    <div class="lang" role="group" :aria-label="labels.language">
      <button type="button" :aria-pressed="language === 'vi'" @click="language = 'vi'">VI</button>
      <button type="button" :aria-pressed="language === 'en'" @click="language = 'en'">EN</button>
    </div>
  </header>

  <main class="stage">
    <section class="map-wrap">
      <RouteDiagram v-if="kioskMap || result?.route" ref="diagram" :kiosk-map="kioskMap" :route="result?.route"
        :candidates="candidates" :labels="labels" :language="language" :disabled="inputLocked"
        @select="(code, name) => submitText(code, true, name)" @progress="onProgress" />
      <p v-else class="map-status" :role="mapProblem ? 'alert' : 'status'">
        <CircleAlert v-if="mapProblem" :size="20" />
        <span v-else class="spinner small"></span>
        {{ mapProblem ? labels.mapUnavailable : labels.mapLoading }}
      </p>
    </section>

    <section class="panel" :aria-busy="busy">
      <div class="panel-body" aria-live="polite">
        <template v-if="mode === 'idle'">
          <div>
            <h1>{{ labels.hello }}</h1>
            <p class="sub">{{ labels.helloAlt }}</p>
          </div>
          <VoiceInput :key="voiceKey" :labels="labels" :busy="busy || talk !== 'off'" :live="liveVoice"
            @live="startTalk" @submit="submitAudio" @problem="showProblem" @activity="onVoiceActivity" />
          <div class="or">{{ labels.orType }}</div>
          <form class="ask" @submit.prevent="submitText()">
            <input v-model="query" type="text" required maxlength="500" autocomplete="off"
              :placeholder="labels.guess" :aria-label="labels.guess">
            <button type="submit" :disabled="inputLocked" :aria-label="labels.search"><ArrowRight :size="22" /></button>
          </form>
          <p class="hint">{{ labels.hint }}</p>
          <div>
            <h2 class="sec-title">{{ labels.shortcuts }}</h2>
            <div class="quick">
              <button v-for="choice in shortcuts" :key="choice.icon" type="button" :disabled="inputLocked"
                @click="submitText(choice.codes?.[kioskFloor] ?? choice.code, true, choice.label)">
                <span class="qi"><component :is="iconMap[choice.icon]" :size="18" /></span>
                <span>
                  <b>{{ choice.label }}<template v-if="choice.codes"> · {{ labels.floor(kioskFloor) }}</template></b>
                  <small>{{ choice.alt }}</small>
                </span>
              </button>
            </div>
          </div>
          <label class="switch">
            <Accessibility :size="20" />
            <span>{{ labels.accessible }}</span>
            <input v-model="wheelchair" type="checkbox" role="switch" :disabled="inputLocked">
          </label>
        </template>

        <template v-else-if="mode === 'busy'">
          <p v-if="said" class="bubble"><b>{{ saidByVoice ? labels.weHeard : labels.youAsked }}</b>“{{ said }}”</p>
          <div class="listen inline" role="status">
            <span class="spinner"></span>
            <h2>{{ labels.thinking }}</h2>
            <p class="hint">{{ labels.checking }}</p>
          </div>
        </template>

        <RoutePanel v-else :labels="labels" :kiosk-floor="kioskFloor" :result="result" :said="said"
          :said-by-voice="saidByVoice"
          :audio-url="audioUrl" :input-locked="inputLocked" :active-step="activeStep"
          @select="(code, name) => submitText(code, false, name)" @reply="(text) => submitText(text)" @reset="reset"
          @replay="diagram?.replay()" @desk="submitText(DESK_CODE, true, labels.toDesk)">
          <template #reply>
            <div class="ask-row">
              <form class="ask" @submit.prevent="submitText()">
                <input v-model="query" type="text" required maxlength="500" autocomplete="off"
                  :placeholder="result.status === 'clarify' ? labels.reply : labels.guess"
                  :aria-label="result.status === 'clarify' ? labels.reply : labels.guess">
                <button type="submit" :disabled="inputLocked" :aria-label="labels.search"><ArrowRight :size="22" /></button>
              </form>
              <VoiceInput :key="voiceKey" compact :labels="labels" :busy="busy || talk !== 'off'" :live="liveVoice"
                @live="startTalk" @submit="submitAudio" @problem="showProblem" @activity="onVoiceActivity" />
            </div>
          </template>
        </RoutePanel>

        <p v-if="problem" class="error-message" role="alert"><CircleAlert :size="20" /> {{ problem }}</p>
      </div>

      <!-- Thanh hội thoại realtime: luôn thấy kiosk đang nghe / đang trả lời và chữ khách vừa nói -->
      <div v-if="talk !== 'off'" class="live" :class="talk" role="status">
        <div v-if="talk === 'listening'" class="bars" aria-hidden="true"><i v-for="bar in 5" :key="bar"></i></div>
        <Volume2 v-else-if="talk === 'speaking'" :size="24" aria-hidden="true" />
        <span v-else class="spinner small" aria-hidden="true"></span>
        <p class="live-text">
          <b>{{ labels.live[talk] }}</b>
          <span v-if="heard">“{{ heard }}”</span>
          <small v-else>{{ labels.liveHint }}</small>
        </p>
        <button v-if="talk === 'speaking'" type="button" class="ghost" @click="conversation?.hush()">{{ labels.liveSkip }}</button>
        <button type="button" class="ghost" @click="stopTalk">{{ labels.liveEnd }}</button>
      </div>

      <div class="panel-foot">
        <div v-if="mode === 'idle'" class="help"><Info :size="18" /><span>{{ labels.help }}</span></div>
        <template v-else-if="mode === 'result'">
          <span v-if="!DEMO">{{ labels.back(idleLeft) }}</span>
          <div v-if="!DEMO" class="back-timer"><i :style="{ transform: `scaleX(${idleLeft / IDLE_SECONDS})` }"></i></div>
          <button type="button" class="ghost" @click="reset">{{ labels.reset }}</button>
        </template>
      </div>
    </section>
  </main>
  <span v-if="DEMO" class="demo-tag">{{ labels.demoTag }}</span>
</template>
