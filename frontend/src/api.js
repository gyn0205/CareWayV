export class WayfindingRequestError extends Error {
  constructor(message, status) {
    super(message)
    this.status = status
  }
}

export async function requestDirections(mode, payload, signal) {
  const response = await fetch(`/gateway/${mode}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    signal,
  })
  const data = await response.json().catch(() => null)
  const statuses = ['route', 'clarify', 'not_found', 'no_route']
  if (!response.ok || !statuses.includes(data?.status)) {
    const detail = typeof data?.detail === 'string' ? data.detail : ''
    throw new WayfindingRequestError(detail, response.status)
  }
  return data
}

// Bản đồ màn hình chờ: vị trí kiosk + mặt bằng các tầng.
export async function requestKioskMap(code, language, signal) {
  const response = await fetch(`/gateway/kiosks/${encodeURIComponent(code)}?language=${language}`, { signal })
  const data = await response.json().catch(() => null)
  if (!response.ok || !data?.origin) {
    throw new WayfindingRequestError(typeof data?.detail === 'string' ? data.detail : '', response.status)
  }
  return data
}

// URL WebSocket (kèm token dùng một lần) để trình duyệt stream mic thẳng tới STT realtime.
export async function requestRealtime(language, signal) {
  const response = await fetch(`/gateway/realtime?language=${language}`, { method: 'POST', signal })
  const data = await response.json().catch(() => null)
  if (!response.ok || typeof data?.url !== 'string') {
    throw new WayfindingRequestError(typeof data?.detail === 'string' ? data.detail : '', response.status)
  }
  return data
}

// Giọng đọc câu trả lời dạng stream. mp3 cho thẻ <audio> (nghe lại); pcm cho hội thoại realtime.
export const speechUrl = (text, language, format = 'mp3') =>
  `/gateway/speech?language=${language}&format=${format}&text=${encodeURIComponent(text)}`

export function audioBase64(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result.split(',')[1])
    reader.onerror = () => reject(reader.error)
    reader.readAsDataURL(blob)
  })
}

export function replyUrl(base64, mediaType) {
  const bytes = Uint8Array.from(atob(base64), (byte) => byte.charCodeAt(0))
  return URL.createObjectURL(new Blob([bytes], { type: mediaType || 'audio/mpeg' }))
}
