<script setup>
import { onBeforeUnmount, ref } from 'vue'
import { Mic, Square, Upload } from '@lucide/vue'
import { encodeRecording, fileFormat, MAX_AUDIO_BYTES, RECORDING_LIMIT_MS } from '../recording'

defineProps({ labels: { type: Object, required: true }, busy: Boolean })
const emit = defineEmits(['submit', 'problem'])
const recording = ref(false)
const preparing = ref(false)
const fileInput = ref(null)
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
      recording.value = false
      if (disposed) return
      preparing.value = true
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

function upload(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file) return
  const format = fileFormat(file)
  if (!format) {
    emit('problem', 'fileError')
    return
  }
  emit('submit', file, format)
}

onBeforeUnmount(() => {
  disposed = true
  if (recorder) recorder.onstop = null
  stop()
  releaseMicrophone()
})
</script>

<template>
  <div class="voice-input">
    <p class="input-label">{{ supportsRecording ? labels.micHint : labels.micUnavailable }}</p>
    <button class="record-button" :class="{ 'is-recording': recording }" type="button"
      :disabled="busy || preparing || !supportsRecording" @click="record">
      <Square v-if="recording" :size="19" />
      <Mic v-else :size="21" />
      {{ recording ? labels.stopAndSend : labels.record }}
    </button>
    <p v-if="recording" class="recording-status" aria-live="polite"><span></span>{{ labels.recording }}</p>
    <div class="upload-row">
      <input ref="fileInput" type="file" hidden accept=".wav,.mp3,.webm,audio/wav,audio/mpeg,audio/webm"
        :disabled="busy || recording || preparing" :aria-label="labels.upload" @change="upload">
      <button class="quiet-button" type="button" :disabled="busy || recording || preparing" @click="fileInput.click()">
        <Upload :size="17" /> {{ labels.upload }}
      </button>
      <span>{{ labels.formats }}</span>
    </div>
  </div>
</template>
