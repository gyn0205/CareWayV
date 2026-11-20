<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { ArrowDownUp, ArrowLeft, Clock3, Footprints, Play, Volume2 } from '@lucide/vue'

// Bảng bên phải sau khi khách hỏi: hỏi lại (clarify), tuyến (route) hoặc không tìm thấy.
const props = defineProps({
  labels: { type: Object, required: true },
  kioskFloor: { type: Number, required: true },
  result: { type: Object, required: true },
  said: String,
  saidByVoice: Boolean,
  audioUrl: String,
  inputLocked: Boolean,
  // Bước đang đi trong mô phỏng trên bản đồ (-1 = chưa phát).
  activeStep: { type: Number, default: -1 },
})
defineEmits(['select', 'reply', 'reset', 'replay', 'desk'])

const route = computed(() => props.result.route)
const english = computed(() => props.result.language === 'en')
const steps = ref(null)
const player = ref(null)

const floorLabel = computed(() => {
  const { origin, arrival } = route.value
  const end = props.labels.floor(arrival.floor)
  return origin.floor_id === arrival.floor_id ? end : `${props.labels.floor(origin.floor)} → ${end}`
})

function destinationName(destination) {
  return english.value ? destination.name_en || destination.name : destination.name
}

// Tên ở ngôn ngữ còn lại (nghiêng, nhỏ) như bảng song ngữ của prototype.
const altName = computed(() => {
  const { name, name_en: nameEn } = route.value.destination
  const alt = english.value ? name : nameEn
  return alt && alt !== destinationName(route.value.destination) ? alt : ''
})

const isTransfer = (step) => step.start.floor_id !== step.end.floor_id

// Giữ bước đang đi luôn trong tầm nhìn.
watch(() => props.activeStep, async (index) => {
  // Khi nhúng trong iframe (demo trang giới thiệu), scrollIntoView kéo cả trang cha về đầu → bỏ qua.
  if (window.self !== window.top) return
  await nextTick()
  steps.value?.children[index]?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
})

// Có bản đọc từ máy chủ (hỏi bằng giọng nói) thì phát bản đó, không thì đọc bằng giọng của trình duyệt.
function listen() {
  if (player.value) {
    player.value.currentTime = 0
    player.value.play().catch(() => {})
    return
  }
  try {
    speechSynthesis.cancel()
    const utterance = new SpeechSynthesisUtterance(props.result.message)
    utterance.lang = english.value ? 'en-US' : 'vi-VN'
    speechSynthesis.speak(utterance)
  } catch {
    // Trình duyệt không có giọng đọc: chỉ dẫn chữ vẫn ở bên dưới.
  }
}
const canListen = computed(() => Boolean(props.audioUrl) || 'speechSynthesis' in window)

onBeforeUnmount(() => {
  try { speechSynthesis.cancel() } catch { /* không hỗ trợ */ }
})
</script>

<template>
  <div class="res-top">
    <button type="button" class="ghost" @click="$emit('reset')"><ArrowLeft :size="18" /> {{ labels.newSearch }}</button>
  </div>
  <p v-if="said" class="bubble"><b>{{ saidByVoice ? labels.weHeard : labels.youAsked }}</b>“{{ said }}”</p>

  <template v-if="route">
    <div class="dest">
      <span class="k">{{ labels.to }} · {{ route.destination.code }}</span>
      <h2>{{ destinationName(route.destination) }}</h2>
      <span v-if="altName" class="en">{{ altName }}</span>
      <div v-if="route.destination.department" class="room">{{ route.destination.department }}</div>
      <div v-if="route.destination.doctor" class="room">{{ route.destination.doctor }}</div>
      <div class="meta">
        <span><ArrowDownUp :size="15" /> {{ floorLabel }}</span>
        <span><Clock3 :size="15" /> {{ labels.minutes(Math.floor(route.seconds / 60), route.seconds % 60) }}</span>
        <span v-if="route.steps.length"><Footprints :size="15" /> {{ labels.stepCount(route.steps.length) }}</span>
      </div>
    </div>
    <div class="actions">
      <button v-if="route.steps.length" type="button" class="ghost" @click="$emit('replay')">
        <Play :size="16" /> {{ labels.replayGuide }}
      </button>
      <button v-if="canListen" type="button" class="ghost" @click="listen"><Volume2 :size="17" /> {{ labels.audioReply }}</button>
    </div>
    <audio v-if="audioUrl" ref="player" :key="audioUrl" :src="audioUrl" controls preload="none" class="audio-reply"
      :aria-label="labels.audioReply"></audio>
    <p v-else-if="result.speech_status === 'unavailable'" class="audio-note">{{ labels.audioUnavailable }}</p>
    <ol v-if="route.steps.length" ref="steps" class="steps">
      <li v-for="(step, index) in route.steps" :key="index"
        :class="{ xfer: isTransfer(step), act: index === activeStep, done: index < activeStep }">
        <span class="step-icon">
          <ArrowDownUp v-if="isTransfer(step)" :size="16" />
          <template v-else>{{ index + 1 }}</template>
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
  </template>

  <template v-else-if="result.status === 'clarify'">
    <div>
      <h1 class="state-title">{{ result.replies?.length ? labels.confirm : labels.pick }}</h1>
      <p class="sub">{{ result.message }}</p>
    </div>
    <!-- Câu trả lời nhanh (vd. "Đúng rồi" / "Không phải") gửi như khách tự nói. -->
    <div v-if="result.replies?.length" class="replies">
      <button v-for="reply in result.replies" :key="reply" type="button" class="primary"
        :disabled="inputLocked" @click="$emit('reply', reply)">{{ reply }}</button>
    </div>
    <slot name="reply" />
    <!-- Câu hỏi lịch hẹn: điểm đến chỉ để tô trên bản đồ, không thành thẻ bấm (bấm không trả lời câu hỏi). -->
    <div v-if="result.candidates.length && result.context?.pending !== 'appointment'" class="cands">
      <button v-for="candidate in result.candidates" :key="candidate.code" class="cand-btn" type="button"
        :disabled="inputLocked" @click="$emit('select', candidate.code, destinationName(candidate))">
        <span class="fl" :class="{ 'here-fl': candidate.floor === kioskFloor }">
          {{ labels.floorShort }}<br>{{ candidate.floor }}
        </span>
        <span>
          <!-- Hỏi theo bác sĩ: tên bác sĩ là dòng chính để phân biệt người trùng tên. -->
          <b>{{ candidate.doctor || destinationName(candidate) }}</b>
          <small>{{ [candidate.doctor && destinationName(candidate), candidate.department, candidate.code].filter(Boolean).join(' · ') }}</small>
        </span>
      </button>
    </div>
  </template>

  <template v-else>
    <div class="none-box">
      <h2>{{ { no_route: labels.noRouteTitle, emergency: labels.emergencyTitle }[result.status] ?? labels.noneTitle }}</h2>
      <p>{{ result.message }}</p>
      <button type="button" class="primary" :disabled="inputLocked" @click="$emit('desk')">
        <Footprints :size="18" /> {{ labels.toDesk }}
      </button>
    </div>
    <slot name="reply" />
  </template>
</template>
