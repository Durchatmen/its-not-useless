import { onBeforeUnmount, ref } from 'vue'

/**
 * 语音采集（功能设计 F1.1 症状描述支持语音输入）。
 *
 * 注意：MediaRecorder 默认产出 webm/opus，而接口 API-08 的 audioFormat 只接受
 * wav / mp3 / amr。转码方案待大模型选型确定（见《环境搭建方案》§8 待办 2），
 * 在确定前本函数只负责采集并回调原始 Blob。
 */
export function useVoice({ maxSeconds = 60 } = {}) {
  const recording = ref(false)
  const seconds = ref(0)
  const error = ref('')

  let recorder = null
  let stream = null
  let chunks = []
  let timer = null

  const UNSUPPORTED = '当前浏览器不支持录音'

  async function start() {
    error.value = ''
    if (!navigator.mediaDevices?.getUserMedia) {
      error.value = UNSUPPORTED
      throw new Error(UNSUPPORTED)
    }

    stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    chunks = []
    recorder = new MediaRecorder(stream)
    recorder.ondataavailable = (event) => {
      if (event.data?.size) chunks.push(event.data)
    }
    recorder.start()
    recording.value = true
    seconds.value = 0

    timer = setInterval(() => {
      seconds.value += 1
      if (seconds.value >= maxSeconds) stop()
    }, 1000)
  }

  function stop() {
    return new Promise((resolve) => {
      if (!recorder || recorder.state === 'inactive') {
        cleanup()
        resolve(null)
        return
      }
      recorder.onstop = () => {
        const blob = new Blob(chunks, { type: recorder.mimeType })
        cleanup()
        resolve(blob)
      }
      recorder.stop()
    })
  }

  function cleanup() {
    clearInterval(timer)
    timer = null
    stream?.getTracks().forEach((track) => track.stop())
    stream = null
    recorder = null
    recording.value = false
  }

  /** Blob 转 Base64（接口 API-08 的 audioData 为 Base64 编码） */
  function blobToBase64(blob) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = () => resolve(String(reader.result).split(',')[1] || '')
      reader.onerror = reject
      reader.readAsDataURL(blob)
    })
  }

  onBeforeUnmount(cleanup)

  return { recording, seconds, error, start, stop, blobToBase64 }
}
