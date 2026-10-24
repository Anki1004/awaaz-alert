// Microphone capture -> 16 kHz mono int16 PCM frames, pushed to a callback every ~250 ms.
// Also exposes a live RMS level and a rolling waveform buffer for the scope.

export interface MicHandle {
  stop: () => void
  level: () => number
  wave: Float32Array
}

export async function startMic(onPcm: (pcm: ArrayBuffer) => void): Promise<MicHandle> {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
  })
  const ctx = new AudioContext({ sampleRate: 16000 })
  const src = ctx.createMediaStreamSource(stream)
  // ScriptProcessor is deprecated but universally available and good enough for a 16 kHz mono tap.
  const proc = ctx.createScriptProcessor(4096, 1, 1)
  const wave = new Float32Array(16000 * 3) // last 3 s for the scope
  let level = 0
  let acc: Int16Array[] = []
  let accLen = 0
  const FRAME = Math.round(ctx.sampleRate * 0.25)

  proc.onaudioprocess = (e) => {
    const input = e.inputBuffer.getChannelData(0)
    // rolling waveform
    wave.copyWithin(0, input.length)
    wave.set(input, wave.length - input.length)
    // level
    let s = 0
    for (let i = 0; i < input.length; i++) s += input[i] * input[i]
    level = Math.sqrt(s / input.length)
    // int16
    const i16 = new Int16Array(input.length)
    for (let i = 0; i < input.length; i++) i16[i] = Math.max(-32768, Math.min(32767, Math.round(input[i] * 32767)))
    acc.push(i16)
    accLen += i16.length
    if (accLen >= FRAME) {
      const out = new Int16Array(accLen)
      let o = 0
      for (const a of acc) { out.set(a, o); o += a.length }
      acc = []; accLen = 0
      onPcm(out.buffer)
    }
  }
  src.connect(proc)
  proc.connect(ctx.destination) // required in some browsers for the processor to run; output is silent-ish
  const gain = ctx.createGain(); gain.gain.value = 0 // make sure we do not echo the mic
  proc.disconnect(); proc.connect(gain); gain.connect(ctx.destination)

  return {
    stop: () => { proc.disconnect(); src.disconnect(); stream.getTracks().forEach((t) => t.stop()); void ctx.close() },
    level: () => level,
    wave,
  }
}
