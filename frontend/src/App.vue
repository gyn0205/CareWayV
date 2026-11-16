<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import {
  Accessibility, ArrowRight, Building2, ChevronDown, CircleAlert, Compass, Globe2, HeartPulse,
  Keyboard, MapPin, Mic, Pill, Search, WalletCards,
} from '@lucide/vue'
import { audioBase64, replyUrl, requestDirections } from './api'
import { copy } from './copy'
import { MAX_AUDIO_BYTES } from './recording'
import RoutePanel from './components/RoutePanel.vue'
import VoiceInput from './components/VoiceInput.vue'

const language = ref('vi')
const kioskFloor = ref(3)
const wheelchair = ref(false)
const mode = ref('text')
const query = ref('')
const result = ref(null)
const busy = ref(false)
const problem = ref('')
const audioUrl = ref('')
const labels = computed(() => copy[language.value])
const iconMap = { heart: HeartPulse, wallet: WalletCards, pill: Pill }
let activeRequest

function clearAudio() {
  if (audioUrl.value) URL.revokeObjectURL(audioUrl.value)
  audioUrl.value = ''
}

function reset() {
  activeRequest?.abort()
  activeRequest = undefined
  busy.value = false
  result.value = null
  problem.value = ''
  query.value = ''
  mode.value = 'text'
  clearAudio()
}

watch([language, kioskFloor], () => {
  document.documentElement.lang = language.value
  reset()
})

function setMode(value) {
  mode.value = value
  problem.value = ''
}

function showProblem(key) {
  problem.value = labels.value[key]
}

async function submit(kind, prepare, newSearch = false) {
  if (busy.value) return
  const controller = new AbortController()
  activeRequest = controller
  const context = !newSearch && result.value?.context
    ? { ...result.value.context, wheelchair: wheelchair.value }
    : null
  const payload = {
    kiosk_code: `KIOSK-${kioskFloor.value}`,
    wheelchair: wheelchair.value,
    language: language.value,
    context,
  }

  problem.value = ''
  clearAudio()
  busy.value = true
  try {
    const answer = await requestDirections(kind, { ...payload, ...await prepare() }, controller.signal)
    if (controller.signal.aborted) return
    result.value = answer
    wheelchair.value = answer.context?.wheelchair ?? wheelchair.value
    query.value = ''
    if (answer.audio_base64) {
      try {
        audioUrl.value = replyUrl(answer.audio_base64, answer.audio_media_type)
      } catch {
        result.value = { ...answer, speech_status: 'unavailable' }
      }
    }
  } catch (error) {
    if (controller.signal.aborted) return
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

function submitText(value = query.value, newSearch = false) {
  const text = value.trim()
  if (!text.length) return
  setMode('text')
  submit('text', () => ({ text }), newSearch)
}

function submitAudio(blob, format) {
  if (!blob.size || blob.size > MAX_AUDIO_BYTES) {
    showProblem('audioSize')
    return
  }
  submit('voice', async () => ({ audio_base64: await audioBase64(blob), format, speak: true }))
}

onBeforeUnmount(() => {
  activeRequest?.abort()
  clearAudio()
})
</script>

<template>
  <header class="site-header">
    <div class="shell header-inner">
      <div class="brand" aria-label="CareWayV">
        <span class="brand-mark"><Compass :size="28" :stroke-width="1.75" /></span>
        <div><strong>CareWay<span>V</span></strong><small>{{ labels.product }}</small></div>
      </div>
      <div class="header-controls">
        <label class="select-control">
          <MapPin :size="18" aria-hidden="true" />
          <select v-model="kioskFloor" :aria-label="labels.kiosk">
            <option :value="3">{{ labels.kioskAt(3) }}</option>
            <option :value="4">{{ labels.kioskAt(4) }}</option>
          </select>
          <ChevronDown :size="15" aria-hidden="true" class="select-arrow" />
        </label>
        <label class="select-control language-control">
          <Globe2 :size="17" aria-hidden="true" />
          <select v-model="language" :aria-label="labels.language">
            <option value="vi">Tiếng Việt</option>
            <option value="en">English</option>
          </select>
          <ChevronDown :size="15" aria-hidden="true" class="select-arrow" />
        </label>
      </div>
    </div>
  </header>

  <main class="shell main-shell">
    <section class="hero" aria-labelledby="page-title">
      <div class="hero-photo" aria-hidden="true"></div>
      <div class="hero-content">
        <div class="hero-zone"><Building2 :size="16" /> {{ labels.zones }}</div>
        <h1 id="page-title">{{ labels.headline }}</h1>
        <p>{{ labels.intro }}</p>
      </div>
    </section>

    <div class="workspace">
      <div class="input-column">
        <section class="panel search-panel" aria-labelledby="search-title">
          <div class="panel-heading">
            <span class="heading-icon"><Search :size="21" /></span>
            <h2 id="search-title">{{ labels.searchTitle }}</h2>
          </div>
          <div class="mode-selector">
            <button type="button" :aria-pressed="mode === 'text'" @click="setMode('text')">
                <Keyboard :size="19" /> {{ labels.textTab }}
            </button>
            <button type="button" :aria-pressed="mode === 'voice'" @click="setMode('voice')">
                <Mic :size="18" /> {{ labels.voiceTab }}
            </button>
          </div>
          <form v-if="mode === 'text'" class="query-form" @submit.prevent="submitText()">
            <label class="input-label" for="wayfinding-question">
              {{ result?.context ? labels.followUp : labels.question }}
            </label>
            <textarea id="wayfinding-question" v-model="query" rows="2" required maxlength="500"
              :placeholder="result?.context ? labels.followPlaceholder : labels.guess"></textarea>
            <button class="primary-button" type="submit" :disabled="busy">
              <Search :size="19" /> {{ busy ? labels.thinking : labels.search }}
              <ArrowRight class="button-arrow" :size="19" />
            </button>
          </form>
          <VoiceInput v-else :key="`${kioskFloor}:${language}`" :labels="labels" :busy="busy"
            @submit="submitAudio" @problem="showProblem" />
          <label class="accessibility-option">
            <Accessibility :size="20" />
            <span>{{ labels.accessible }}</span>
            <input v-model="wheelchair" type="checkbox" role="switch" :disabled="busy">
          </label>
          <p v-if="problem" class="error-message" role="alert"><CircleAlert :size="20" /> {{ problem }}</p>
        </section>

        <section class="shortcuts" aria-labelledby="shortcuts-title">
          <h2 id="shortcuts-title">{{ labels.shortcuts }}</h2>
          <div class="shortcut-list">
            <button v-for="choice in labels.choices" :key="choice.icon" type="button" class="shortcut"
              :disabled="busy" @click="submitText(choice.query, true)">
              <span class="shortcut-icon"><component :is="iconMap[choice.icon]" :size="19" /></span>
              <strong>{{ choice.label }}</strong>
              <ArrowRight :size="17" class="shortcut-arrow" />
            </button>
          </div>
        </section>
      </div>
      <RoutePanel :labels="labels" :kiosk-floor="kioskFloor" :result="result" :audio-url="audioUrl"
        :busy="busy" @select="submitText" @reset="reset" />
    </div>
  </main>

  <footer class="shell footer">
    <span><Compass :size="17" /> CareWayV</span>
    <span>{{ labels.sample }}</span>
  </footer>
</template>
