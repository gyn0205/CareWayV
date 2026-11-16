<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { Mic, Square } from '@lucide/vue'
import { encodeRecording, MAX_AUDIO_BYTES, RECORDING_LIMIT_MS } from '../recording'

defineProps({ labels: { type: Object, required: true }, busy: Boolean })
const emit = defineEmits(['submit', 'problem', 'activity'])
const recording = ref(false)
const preparing = ref(false)
const active = computed(() => recording.value || preparing.value)
watch(active, (value) => emit('activity', value), { flush: 'sync' })
const supportsRecording = Boolean(navigator.mediaDevices?.getUserMedia && window.MediaRecorder)
let recorder
let stream
let timer
let disposed = false

function releaseMicrophone() {
  clearTimeout(timer)
  stream?.getTracks().forEach((track) => track.stop())
  stream = undefined
}

function stop() {
  if (recorder?.state === 'recording') recorder.stop()
}

async function record() {
  if (recording.value) {
    stop()
    return
  }
  if (!supportsRecording || preparing.value) return
  preparing.value = true
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    if (disposed) {
      releaseMicrophone()
      return
    }
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
      preparing.value = true
      recording.value = false
      if (disposed) return
      try {
        if (!clip.size || clip.size > MAX_AUDIO_BYTES) {
          emit('problem', 'audioSize')
          return
        }
        const encoded = await encodeRecording(clip)
        if (!disposed) emit('submit', encoded.blob, encoded.format)
      } catch {
        if (!disposed) emit('problem', 'audioError')
      } finally {
        preparing.value = false
      }
    }
    recorder.start()
    recording.value = true
    timer = setTimeout(stop, RECORDING_LIMIT_MS)
  } catch {
    releaseMicrophone()
    if (!disposed) emit('problem', 'micError')
  } finally {
    preparing.value = false
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
  <div class="voice-input">
    <button class="record-button" :class="{ 'is-recording': recording }" type="button"
      aria-describedby="mic-status"
      :disabled="busy || preparing || !supportsRecording" @click="record">
      <Square v-if="recording" :size="30" aria-hidden="true" />
      <Mic v-else :size="34" aria-hidden="true" />
      <span>{{ recording ? labels.stopAndSend : labels.record }}</span>
    </button>
    <p id="mic-status" class="mic-status" :class="{ 'recording-status': recording }" role="status">
      {{ recording ? labels.recording : preparing ? labels.preparingMic : supportsRecording ? labels.micHint : labels.micUnavailable }}
    </p>
  </div>
</template>
