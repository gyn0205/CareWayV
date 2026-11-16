<script setup>
import { computed, ref, watch } from 'vue'
import {
  ArrowDownUp, ArrowRight, Clock3, Footprints, LocateFixed, MapPin, RotateCcw, Route, Volume2,
} from '@lucide/vue'
import RouteDiagram from './RouteDiagram.vue'

const props = defineProps({
  labels: { type: Object, required: true },
  kioskFloor: { type: Number, required: true },
  result: Object,
  audioUrl: String,
  busy: Boolean,
})
defineEmits(['select', 'reset'])

const view = ref('steps')
watch(() => props.result, () => { view.value = 'steps' })

const route = computed(() => props.result?.route)
const floorLabel = computed(() => {
  if (!route.value) return ''
  const { origin, arrival } = route.value
  const start = props.labels.floor(origin.floor)
  const end = props.labels.floor(arrival.floor)
  return origin.floor_id === arrival.floor_id ? end : `${start} → ${end}`
})

function destinationName(destination) {
  if (props.result.language === 'en') return destination.name_en || destination.name
  return destination.name
}
</script>

<template>
  <section class="panel route-panel" aria-labelledby="directions-title" :aria-busy="busy">
    <div class="result-header">
      <div class="panel-heading">
        <span class="heading-icon"><Route :size="21" /></span>
        <h2 id="directions-title">{{ labels.routeTitle }}</h2>
      </div>
      <button v-if="result" type="button" class="quiet-button reset-button" @click="$emit('reset')">
        <RotateCcw :size="16" /> {{ labels.reset }}
      </button>
    </div>

    <div class="result-content">
      <div v-if="busy" class="empty-route" role="status">
        <span class="loader"></span>
        <h3>{{ labels.thinking }}</h3>
        <p>{{ labels.checking }}</p>
      </div>
      <div v-else-if="!result" class="empty-route">
        <div class="empty-illustration" aria-hidden="true">
          <div class="illustration-track"></div>
          <span class="illustration-point"></span>
          <span class="illustration-pin"><MapPin :size="35" :stroke-width="1.65" /></span>
        </div>
        <h3>{{ labels.ready }}</h3>
        <p>{{ labels.readyHelp }}</p>
        <div class="origin-pill"><LocateFixed :size="16" /> {{ labels.kioskAt(kioskFloor) }}</div>
      </div>
      <template v-else>
        <p v-if="result.transcript" class="transcript">
          <strong>{{ labels.transcript }}</strong> {{ result.transcript }}
        </p>
        <div v-if="audioUrl" class="audio-reply">
          <span><Volume2 :size="19" /> {{ labels.audioReply }}</span>
          <audio :key="audioUrl" :src="audioUrl" controls :aria-label="labels.audioReply"></audio>
        </div>
        <p v-else-if="result.speech_status === 'unavailable'" class="audio-note">
          {{ labels.audioUnavailable }}
        </p>

        <div v-if="route" class="direction-result">
          <div class="destination-banner">
            <span class="destination-pin"><MapPin :size="24" /></span>
            <div>
              <p class="destination-label">{{ labels.to }} <span>· {{ route.destination.code }}</span></p>
              <h3>{{ destinationName(route.destination) }}</h3>
              <small v-if="route.destination.department">{{ route.destination.department }}</small>
            </div>
          </div>
          <div class="route-meta">
            <span><ArrowDownUp :size="16" /> {{ floorLabel }}</span>
            <span><Clock3 :size="16" /> {{ labels.minutes(Math.floor(route.seconds / 60), route.seconds % 60) }}</span>
          </div>
          <div class="result-views">
            <button type="button" :aria-pressed="view === 'steps'" @click="view = 'steps'">
              <Footprints :size="17" /> {{ labels.steps }}
            </button>
            <button type="button" :aria-pressed="view === 'map'" @click="view = 'map'">
              <Route :size="17" /> {{ labels.map }}
            </button>
          </div>
          <RouteDiagram v-if="view === 'map'" :route="route" :labels="labels" />
          <ol v-else-if="route.steps.length" class="steps">
            <li v-for="(step, index) in route.steps" :key="index"
              :class="{ 'floor-transfer': step.start.floor_id !== step.end.floor_id }">
              <span class="step-icon">
                <ArrowDownUp v-if="step.start.floor_id !== step.end.floor_id" :size="19" />
                <span v-else>{{ index + 1 }}</span>
              </span>
              <div>
                <small v-if="index === 0 || route.steps[index - 1].start.floor_id !== step.start.floor_id">
                  {{ labels.floor(step.start.floor) }}
                </small>
                <p>{{ step.instruction }}</p>
              </div>
            </li>
          </ol>
          <p v-else class="result-message">{{ result.message }}</p>
        </div>
        <div v-else class="clarification">
          <h3>{{ result.status === 'clarify' ? labels.selectDestination : labels.tryAgain }}</h3>
          <p class="result-message">{{ result.message }}</p>
          <div v-if="result.candidates.length" class="candidate-list">
            <button v-for="candidate in result.candidates" :key="candidate.code" class="candidate"
              type="button" @click="$emit('select', candidate.code)">
              <MapPin :size="19" />
              <span>
                <strong>{{ destinationName(candidate) }}</strong>
                <small>{{ candidate.code }} · {{ labels.floor(candidate.floor) }}</small>
              </span>
              <ArrowRight class="candidate-arrow" :size="19" />
            </button>
          </div>
        </div>
      </template>
    </div>
  </section>
</template>
