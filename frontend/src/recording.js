export const MAX_AUDIO_BYTES = 2 * 1024 * 1024
export const RECORDING_LIMIT_MS = 15_000

const formats = { wav: 'wav', mp3: 'mp3', webm: 'webm' }

export function fileFormat(file) {
  const extension = file.name.split('.').pop()?.toLowerCase()
  return Object.hasOwn(formats, extension) ? formats[extension] : null
}

export async function encodeRecording(blob) {
  if (blob.type.startsWith('audio/webm')) return { blob, format: 'webm' }

  const Decoder = window.AudioContext || window.webkitAudioContext
  const OfflineDecoder = window.OfflineAudioContext || window.webkitOfflineAudioContext
  if (!Decoder || !OfflineDecoder) throw new Error('Web Audio is unavailable')
  const context = new Decoder()
  let decoded
  try {
    decoded = await context.decodeAudioData(await blob.arrayBuffer())
  } finally {
    await context.close()
  }

  const sampleRate = 16_000
  const offline = new OfflineDecoder(1, Math.ceil(decoded.duration * sampleRate), sampleRate)
  const source = offline.createBufferSource()
  source.buffer = decoded
  source.connect(offline.destination)
  source.start()
  const rendered = await offline.startRendering()
  const samples = rendered.getChannelData(0)
  const buffer = new ArrayBuffer(44 + samples.length * 2)
  const data = new DataView(buffer)
  function writeLabel(offset, label) {
    for (let i = 0; i < label.length; i++) data.setUint8(offset + i, label.charCodeAt(i))
  }
  writeLabel(0, 'RIFF')
  data.setUint32(4, buffer.byteLength - 8, true)
  writeLabel(8, 'WAVE')
  writeLabel(12, 'fmt ')
  data.setUint32(16, 16, true)
  data.setUint16(20, 1, true)
  data.setUint16(22, 1, true)
  data.setUint32(24, sampleRate, true)
  data.setUint32(28, sampleRate * 2, true)
  data.setUint16(32, 2, true)
  data.setUint16(34, 16, true)
  writeLabel(36, 'data')
  data.setUint32(40, samples.length * 2, true)
  samples.forEach((sample, index) => {
    data.setInt16(44 + index * 2, Math.max(-1, Math.min(1, sample)) * 32767, true)
  })
  return { blob: new Blob([buffer], { type: 'audio/wav' }), format: 'wav' }
}
