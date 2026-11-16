<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import {
  Accessibility, ArrowRight, Building2, ChevronDown, CircleAlert, Compass, Globe2, HeartPulse,
  MapPin, Pill, Search, Stethoscope, WalletCards,
} from '@lucide/vue'
import { audioBase64, replyUrl, requestDirections } from './api'
import { copy } from './copy'
import { MAX_AUDIO_BYTES } from './recording'
import RoutePanel from './components/RoutePanel.vue'
import VoiceInput from './components/VoiceInput.vue'

const language = ref('vi')
const kioskFloor = ref(3)
const wheelchair = ref(false)
const query = ref('')
const result = ref(null)
const busy = ref(false)
const problem = ref('')
const audioUrl = ref('')
const voiceActive = ref(false)
const voiceKey = ref(0)
const searchSection = ref(null)
const routeSection = ref(null)
const labels = computed(() => copy[language.value])
const inputLocked = computed(() => busy.value || voiceActive.value)
const iconMap = { heart: HeartPulse, wallet: WalletCards, pill: Pill, clinic: Stethoscope }
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
  voiceActive.value = false
  voiceKey.value++
  clearAudio()
}

async function startOver() {
  reset()
  await nextTick()
  searchSection.value?.scrollIntoView({ block: 'start' })
}

watch([language, kioskFloor], () => {
  document.documentElement.lang = language.value
  reset()
})

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
  let returnedRoute
  try {
    const answer = await requestDirections(kind, { ...payload, ...await prepare() }, controller.signal)
    if (controller.signal.aborted) return
    result.value = answer
    returnedRoute = answer.route
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
  if (returnedRoute) {
    await nextTick()
    if (!busy.value && result.value?.route) routeSection.value?.scrollIntoView({ block: 'start' })
  }
}

function submitText(value = query.value, newSearch = false) {
  const text = value.trim()
  if (inputLocked.value || !text) return
  submit('text', () => ({ text }), newSearch)
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

  <main class="main-shell">
    <section class="shell hero" aria-labelledby="page-title">
      <div class="hero-photo" aria-hidden="true"></div>
      <div class="hero-content">
        <div class="hero-zone"><Building2 :size="16" /> {{ labels.zones }}</div>
        <h1 id="page-title">{{ labels.headline }}</h1>
        <p>{{ labels.intro }}</p>
      </div>
    </section>

    <div class="workspace">
      <section ref="searchSection" class="panel search-panel" :aria-label="labels.searchTitle">
        <div class="search-inputs">
          <VoiceInput :key="voiceKey" :labels="labels" :busy="busy"
            @submit="submitAudio" @problem="showProblem" @activity="onVoiceActivity" />
          <form class="query-form" @submit.prevent="submitText()">
            <label class="input-label" for="wayfinding-question">
              {{ result?.context ? labels.followUp : labels.question }}
            </label>
            <div class="query-field">
              <input id="wayfinding-question" v-model="query" type="text" required maxlength="500"
                :placeholder="result?.context ? labels.followPlaceholder : labels.guess">
              <button class="primary-button" type="submit" :disabled="inputLocked">
                <Search :size="19" /> {{ labels.search }}
              </button>
            </div>
          </form>
        </div>
        <div class="search-options">
          <section class="shortcuts" aria-labelledby="shortcuts-title">
            <h2 id="shortcuts-title">{{ labels.shortcuts }}</h2>
            <div class="shortcut-list">
              <button v-for="choice in labels.choices" :key="choice.icon" type="button" class="shortcut"
                :disabled="inputLocked" @click="submitText(choice.codes?.[kioskFloor] ?? choice.code, true)">
                <span class="shortcut-icon"><component :is="iconMap[choice.icon]" :size="19" /></span>
                <strong>{{ choice.label }}<span v-if="choice.codes"> · {{ labels.floor(kioskFloor) }}</span></strong>
                <ArrowRight :size="16" class="shortcut-arrow" />
              </button>
            </div>
          </section>
          <label class="accessibility-option">
            <Accessibility :size="20" />
            <span>{{ labels.accessible }}</span>
            <input v-model="wheelchair" type="checkbox" role="switch" :disabled="inputLocked">
          </label>
        </div>
        <p v-if="problem" class="error-message" role="alert"><CircleAlert :size="20" /> {{ problem }}</p>
      </section>
      <div ref="routeSection" class="route-section">
        <RoutePanel :labels="labels" :kiosk-floor="kioskFloor" :result="result" :audio-url="audioUrl"
          :busy="busy" :input-locked="inputLocked" @select="submitText" @reset="startOver" />
      </div>
    </div>
  </main>

  <footer class="shell footer">
    <span><Compass :size="17" /> CareWayV</span>
    <span>{{ labels.sample }}</span>
  </footer>
</template>
