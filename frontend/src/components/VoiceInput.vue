<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { Mic, Square } from '@lucide/vue'
import { encodeRecording, MAX_AUDIO_BYTES, RECORDING_LIMIT_MS } from '../recording'

// compact: nút mic nhỏ cạnh ô trả lời (khi kiosk hỏi lại); mặc định: nút mic lớn ở màn hình chờ.
// live: bấm mic là bắt đầu hội thoại realtime (App lo), không ghi âm từng câu ở đây.
const props = defineProps({ labels: { type: Object, required: true }, busy: Boolean, compact: Boolean, live: Boolean })
const emit = defineEmits(['submit', 'problem', 'activity', 'live'])
const recording = ref(false)
const preparing = ref(false)
const active = computed(() => recording.value || preparing.value)
watch(active, (value) => emit('activity', value), { flush: 'sync' })
const supportsRecording = Boolean(navigator.mediaDevices?.getUserMedia && window.MediaRecorder)
let recorder
let stream
let timer
let disposed = false
// Khách bấm "Hủy" → bỏ bản ghi, không gửi.
let cancelled = false
// Số lần bấm mic: yêu cầu mic cũ (đã hủy) trả về muộn thì tắt ngay, không mở mic chồng.
let attempts = 0

function releaseMicrophone() {
  clearTimeout(timer)
  stream?.getTracks().forEach((track) => track.stop())
  stream = undefined
}

function stop() {
  if (recorder?.state === 'recording') recorder.stop()
}

function cancel() {
  cancelled = true
  attempts++
  if (recorder?.state === 'recording') {
    recorder.stop()
    return
  }
  releaseMicrophone()
  preparing.value = false
}

async function record() {
  if (props.live) {
    emit('live')
    return
  }
  if (recording.value) {
    stop()
    return
  }
  if (!supportsRecording || preparing.value) return
  const attempt = ++attempts
  cancelled = false
  preparing.value = true
  try {
    const media = await navigator.mediaDevices.getUserMedia({ audio: true })
    if (disposed || attempt !== attempts) {
      media.getTracks().forEach((track) => track.stop())
      return
    }
    stream = media
    const webm = 'audio/webm;codecs=opus'
    recorder = MediaRecorder.isTypeSupported(webm)
      ? new MediaRecorder(stream, { mimeType: webm })
      : new MediaRecorder(stream)
    const chunks = []
    recorder.ondataavailable = (event) => {
      if (event.data.size) chunks.push(event.data)
    }
    recorder.onerror = () => {
      recorder.onstop = null
      releaseMicrophone()
      recording.value = false
      emit('problem', 'micError')
    }
    recorder.onstop = async () => {
      const clip = new Blob(chunks, { type: recorder.mimeType || chunks[0]?.type })
      releaseMicrophone()
      recording.value = false
      if (disposed) return
      if (cancelled) {
        preparing.value = false
        return
      }
      preparing.value = true
      try {
        if (!clip.size || clip.size > MAX_AUDIO_BYTES) {
          emit('problem', 'audioSize')
          return
        }
        const encoded = await encodeRecording(clip)
        if (!disposed && !cancelled) emit('submit', encoded.blob, encoded.format)
      } catch {
        if (!disposed && !cancelled) emit('problem', 'audioError')
      } finally {
        preparing.value = false
      }
    }
    recorder.start()
    recording.value = true
    timer = setTimeout(stop, RECORDING_LIMIT_MS)
  } catch {
    if (attempt !== attempts) return
    releaseMicrophone()
    if (!disposed) emit('problem', 'micError')
  } finally {
    if (attempt === attempts) preparing.value = false
  }
}

onBeforeUnmount(() => {
  disposed = true
  if (recorder) {
    recorder.onstop = null
    recorder.onerror = null
  }
  stop()
  releaseMicrophone()
})
</script>

<template>
  <div class="voice-input" :class="{ compact }">
    <button class="mic" type="button" :aria-label="labels.record" :title="labels.record"
      :disabled="busy || active || !supportsRecording" @click="record">
      <Mic :size="compact ? 22 : 46" aria-hidden="true" />
    </button>
    <div v-if="!compact" class="mic-label">
      {{ supportsRecording ? labels.record : labels.micUnavailable }}<small>{{ labels.recordAlt }}</small>
    </div>
    <!-- Màn "Đang nghe" phủ cả bảng bên phải như prototype -->
    <div v-if="active" class="listen" role="status">
      <div v-if="recording" class="bars" aria-hidden="true"><i v-for="bar in 5" :key="bar"></i></div>
      <span v-else class="spinner" aria-hidden="true"></span>
      <h2>{{ recording ? labels.recording : labels.preparingMic }}</h2>
      <p class="hint">{{ labels.micHint }}</p>
      <div class="listen-actions">
        <button v-if="recording" type="button" class="primary" @click="stop">
          <Square :size="18" aria-hidden="true" /> {{ labels.stopAndSend }}
        </button>
        <button type="button" class="ghost" @click="cancel">{{ labels.cancel }}</button>
      </div>
    </div>
  </div>
</template>
