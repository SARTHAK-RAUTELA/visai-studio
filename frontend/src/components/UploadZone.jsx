import React, { useState, useCallback } from 'react'
import { useDropzone } from 'react-dropzone'
import useEditStore from '../stores/editStore.js'
import { uploadFiles, uploadReference, detectScenes } from '../api/client.js'

// ─── Spinner ─────────────────────────────────────────────────────────────────
function Spinner({ size = 'sm' }) {
  const cls = size === 'sm' ? 'w-4 h-4' : 'w-6 h-6'
  return (
    <svg
      className={`${cls} animate-spin text-violet-400`}
      fill="none"
      viewBox="0 0 24 24"
    >
      <circle
        className="opacity-25"
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        strokeWidth="4"
      />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"
      />
    </svg>
  )
}

// ─── Drop Zone Shell ──────────────────────────────────────────────────────────
function DropZoneShell({ isDragActive, getRootProps, getInputProps, label, hint, icon }) {
  return (
    <div
      {...getRootProps()}
      className={`
        relative flex flex-col items-center justify-center gap-2 p-6 rounded-xl border-2 border-dashed
        cursor-pointer transition-all duration-200 select-none
        ${isDragActive
          ? 'border-violet-500 bg-violet-900/20'
          : 'border-[#1e1e2e] bg-[#12121a] hover:border-violet-600 hover:bg-violet-900/10'
        }
      `}
    >
      <input {...getInputProps()} />
      <span className="text-3xl">{icon}</span>
      <p className="text-sm font-medium text-slate-200">{label}</p>
      <p className="text-xs text-slate-500">{hint}</p>
    </div>
  )
}

// ─── Video Clips Drop Zone ────────────────────────────────────────────────────
function ClipsDropZone() {
  const { clips, addClip, removeClip } = useEditStore()
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState(null)
  const [scenesLoading, setScenesLoading] = useState({}) // { [clipId]: bool }
  const [scenesResult, setScenesResult] = useState({})   // { [clipId]: scene_count }

  const onDrop = useCallback(
    async (acceptedFiles) => {
      if (!acceptedFiles.length) return
      setUploading(true)
      setError(null)
      for (const file of acceptedFiles) {
        try {
          const fd = new FormData()
          fd.append('file', file)
          const res = await uploadFiles(fd)
          const data = res.data
          addClip({
            id: data.file_id,
            name: file.name,
            sizeMb: data.size_mb ?? (file.size / 1024 / 1024).toFixed(1),
            thumbnail: data.thumbnail || null,
          })
        } catch (err) {
          setError(`Failed to upload "${file.name}": ${err.message}`)
        }
      }
      setUploading(false)
    },
    [addClip]
  )

  const handleDetectScenes = useCallback(async (clipId) => {
    setScenesLoading((s) => ({ ...s, [clipId]: true }))
    setScenesResult((s) => ({ ...s, [clipId]: null }))
    try {
      const res = await detectScenes(clipId)
      setScenesResult((s) => ({ ...s, [clipId]: res.data.scene_count }))
    } catch (err) {
      setScenesResult((s) => ({ ...s, [clipId]: `Error: ${err.message}` }))
    }
    setScenesLoading((s) => ({ ...s, [clipId]: false }))
  }, [])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'video/mp4': ['.mp4'],
      'video/quicktime': ['.mov'],
      'video/x-matroska': ['.mkv'],
      'video/webm': ['.webm'],
    },
    multiple: true,
  })

  return (
    <div className="flex flex-col gap-3">
      <DropZoneShell
        getRootProps={getRootProps}
        getInputProps={getInputProps}
        isDragActive={isDragActive}
        icon="📁"
        label="Drop your video clips here or browse"
        hint="MP4, MOV, MKV, WebM · Max 500 MB each · Multi-file"
      />

      {uploading && (
        <div className="flex items-center gap-2 text-sm text-violet-400">
          <Spinner />
          <span>Uploading...</span>
        </div>
      )}

      {error && (
        <p className="text-xs text-red-400 bg-red-900/20 border border-red-800 rounded-lg px-3 py-2">
          {error}
        </p>
      )}

      {clips.length > 0 && (
        <ul className="flex flex-col gap-2">
          {clips.map((clip) => (
            <li
              key={clip.id}
              className="flex items-center justify-between px-3 py-2 rounded-lg bg-[#12121a] border border-[#1e1e2e]"
            >
              <div className="flex items-center gap-2 min-w-0">
                {clip.thumbnail ? (
                  <img
                    src={`data:image/jpeg;base64,${clip.thumbnail}`}
                    alt=""
                    className="w-10 h-7 object-cover rounded flex-shrink-0 border border-[#1e1e2e]"
                  />
                ) : (
                  <span className="text-base flex-shrink-0">📎</span>
                )}
                <span className="text-sm text-slate-200 truncate max-w-[180px]">
                  {clip.name}
                </span>
                <span className="text-xs text-slate-500 whitespace-nowrap">
                  {clip.sizeMb} MB
                </span>
              </div>
              <div className="flex items-center gap-1 ml-2 flex-shrink-0">
                <button
                  onClick={() => handleDetectScenes(clip.id)}
                  disabled={scenesLoading[clip.id]}
                  title="Detect scene cuts"
                  className="px-2 py-1 text-xs rounded bg-[#1e1e2e] border border-[#2e2e3e] text-slate-400 hover:text-violet-300 hover:border-violet-700 disabled:opacity-40 transition-colors"
                >
                  {scenesLoading[clip.id] ? <Spinner size="sm" /> : 'Scenes'}
                </button>
                {scenesResult[clip.id] != null && (
                  <span className="text-xs text-violet-400 whitespace-nowrap">
                    {typeof scenesResult[clip.id] === 'number'
                      ? `${scenesResult[clip.id]} scenes`
                      : scenesResult[clip.id]}
                  </span>
                )}
                <button
                  onClick={() => removeClip(clip.id)}
                  className="w-6 h-6 flex items-center justify-center rounded-full text-slate-500 hover:text-red-400 hover:bg-red-900/20 transition-colors"
                  aria-label="Remove clip"
                >
                  ×
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

// ─── Audio Drop Zone ──────────────────────────────────────────────────────────
function AudioDropZone() {
  const { audio, setAudio } = useEditStore()
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState(null)

  const onDrop = useCallback(
    async (acceptedFiles) => {
      if (!acceptedFiles.length) return
      const file = acceptedFiles[0]
      setUploading(true)
      setError(null)
      try {
        const fd = new FormData()
        fd.append('file', file)
        const res = await uploadFiles(fd)
        const data = res.data
        setAudio({ id: data.file_id, name: file.name })
      } catch (err) {
        setError(`Failed to upload: ${err.message}`)
      }
      setUploading(false)
    },
    [setAudio]
  )

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'audio/mpeg': ['.mp3'],
      'audio/wav': ['.wav'],
      'audio/aac': ['.aac'],
    },
    multiple: false,
  })

  return (
    <div className="flex flex-col gap-3">
      <DropZoneShell
        getRootProps={getRootProps}
        getInputProps={getInputProps}
        isDragActive={isDragActive}
        icon="🎵"
        label="Drop your soundtrack here or browse"
        hint="MP3, WAV, AAC · Single file"
      />

      {uploading && (
        <div className="flex items-center gap-2 text-sm text-violet-400">
          <Spinner />
          <span>Uploading...</span>
        </div>
      )}

      {error && (
        <p className="text-xs text-red-400 bg-red-900/20 border border-red-800 rounded-lg px-3 py-2">
          {error}
        </p>
      )}

      {audio && (
        <div className="flex items-center justify-between px-3 py-2 rounded-lg bg-[#12121a] border border-[#1e1e2e]">
          <div className="flex items-center gap-2 min-w-0">
            <span className="text-base">🎶</span>
            <span className="text-sm text-slate-200 truncate max-w-[220px]">{audio.name}</span>
          </div>
          <button
            onClick={() => setAudio(null)}
            className="ml-3 w-6 h-6 flex items-center justify-center rounded-full text-slate-500 hover:text-red-400 hover:bg-red-900/20 transition-colors flex-shrink-0"
            aria-label="Remove audio"
          >
            ×
          </button>
        </div>
      )}
    </div>
  )
}

// ─── Reference Video Zone ────────────────────────────────────────────────────
function ReferenceDropZone() {
  const { reference, setReference } = useEditStore()
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState(null)
  const [urlInput, setUrlInput] = useState('')
  const [urlLoading, setUrlLoading] = useState(false)

  const onDrop = useCallback(
    async (acceptedFiles) => {
      if (!acceptedFiles.length) return
      const file = acceptedFiles[0]
      setUploading(true)
      setError(null)
      try {
        const fd = new FormData()
        fd.append('file', file)
        const res = await uploadReference(fd)
        const data = res.data
        setReference({ id: data.file_id, name: file.name })
      } catch (err) {
        setError(`Failed to upload: ${err.message}`)
      }
      setUploading(false)
    },
    [setReference]
  )

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'video/mp4': ['.mp4'],
      'video/quicktime': ['.mov'],
    },
    multiple: false,
  })

  const handleUrlSubmit = useCallback(async () => {
    const trimmed = urlInput.trim()
    if (!trimmed) return
    setUrlLoading(true)
    setError(null)
    try {
      const fd = new FormData()
      fd.append('url', trimmed)
      const res = await uploadReference(fd)
      const data = res.data
      setReference({ id: data.file_id, name: trimmed })
      setUrlInput('')
    } catch (err) {
      setError(`Failed to process URL: ${err.message}`)
    }
    setUrlLoading(false)
  }, [urlInput, setReference])

  return (
    <div className="flex flex-col gap-3">
      <DropZoneShell
        getRootProps={getRootProps}
        getInputProps={getInputProps}
        isDragActive={isDragActive}
        icon="📺"
        label="Reference video (optional)"
        hint="MP4, MOV · or paste a URL below"
      />

      {/* URL input */}
      <div className="flex gap-2">
        <input
          type="url"
          value={urlInput}
          onChange={(e) => setUrlInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleUrlSubmit()}
          placeholder="Paste Instagram / TikTok / YouTube URL..."
          className="flex-1 px-3 py-2 text-sm bg-[#12121a] border border-[#1e1e2e] rounded-lg text-slate-200 placeholder-slate-600 focus:outline-none focus:border-violet-600 transition-colors"
        />
        <button
          onClick={handleUrlSubmit}
          disabled={!urlInput.trim() || urlLoading}
          className="px-3 py-2 text-sm bg-violet-700 hover:bg-violet-600 disabled:opacity-40 disabled:cursor-not-allowed rounded-lg text-white font-medium transition-colors flex items-center gap-1"
        >
          {urlLoading ? <Spinner size="sm" /> : 'Add'}
        </button>
      </div>

      {uploading && (
        <div className="flex items-center gap-2 text-sm text-violet-400">
          <Spinner />
          <span>Uploading reference...</span>
        </div>
      )}

      {error && (
        <p className="text-xs text-red-400 bg-red-900/20 border border-red-800 rounded-lg px-3 py-2">
          {error}
        </p>
      )}

      {reference && (
        <div className="flex items-center justify-between px-3 py-2 rounded-lg bg-violet-900/20 border border-violet-800">
          <div className="flex items-center gap-2 min-w-0">
            <span className="text-base">🎯</span>
            <span className="text-sm text-violet-300 truncate max-w-[220px]">
              {reference.name}
            </span>
          </div>
          <button
            onClick={() => setReference(null)}
            className="ml-3 w-6 h-6 flex items-center justify-center rounded-full text-violet-400 hover:text-red-400 hover:bg-red-900/20 transition-colors flex-shrink-0"
            aria-label="Remove reference"
          >
            ×
          </button>
        </div>
      )}
    </div>
  )
}

// ─── Main Component ────────────────────────────────────────────────────────────
export default function UploadZone() {
  const { clips, audio, setScreen } = useEditStore()
  const canContinue = clips.length >= 1 && audio !== null

  return (
    <div className="min-h-screen bg-[#0a0a0f] flex flex-col">
      {/* Header — hidden on mobile since TopNav handles branding */}
      <header className="hidden sm:flex items-center gap-3 px-4 sm:px-6 py-4 border-b border-[#1e1e2e]">
        <div className="w-8 h-8 rounded-lg bg-violet-600 flex items-center justify-center text-white font-bold text-sm shrink-0">
          V
        </div>
        <h1 className="text-lg font-semibold text-slate-100 tracking-tight">
          VisualAI Studio
        </h1>
        <span className="ml-auto text-xs text-slate-600">AI-Powered Video Editor</span>
      </header>

      {/* Main content */}
      <main className="flex-1 flex flex-col items-center justify-center px-4 py-6 sm:py-10">
        <div className="w-full max-w-2xl flex flex-col gap-6 sm:gap-8">
          {/* Page heading */}
          <div className="text-center">
            <h2 className="text-3xl font-bold text-slate-100 mb-2">
              Upload your footage
            </h2>
            <p className="text-slate-400 text-sm">
              Add video clips and a soundtrack to get started. Reference video is optional.
            </p>
          </div>

          {/* Upload cards — always stacked vertically */}
          <div className="flex flex-col gap-4 sm:gap-6">
            {/* Video clips */}
            <section className="bg-[#12121a] border border-[#1e1e2e] rounded-2xl p-5">
              <h3 className="text-sm font-semibold text-slate-300 mb-3 flex items-center gap-2">
                <span className="w-5 h-5 rounded-full bg-violet-800 flex items-center justify-center text-xs text-violet-300">1</span>
                Video Clips
                <span className="text-slate-600 font-normal">(1–20 clips)</span>
              </h3>
              <ClipsDropZone />
            </section>

            {/* Soundtrack */}
            <section className="bg-[#12121a] border border-[#1e1e2e] rounded-2xl p-5">
              <h3 className="text-sm font-semibold text-slate-300 mb-3 flex items-center gap-2">
                <span className="w-5 h-5 rounded-full bg-violet-800 flex items-center justify-center text-xs text-violet-300">2</span>
                Soundtrack
                <span className="text-slate-600 font-normal">(required)</span>
              </h3>
              <AudioDropZone />
            </section>

            {/* Reference video */}
            <section className="bg-[#12121a] border border-[#1e1e2e] rounded-2xl p-5">
              <h3 className="text-sm font-semibold text-slate-300 mb-3 flex items-center gap-2">
                <span className="w-5 h-5 rounded-full bg-[#1e1e2e] flex items-center justify-center text-xs text-slate-500">3</span>
                Reference Video
                <span className="text-slate-600 font-normal">(optional — clone any style)</span>
              </h3>
              <ReferenceDropZone />
            </section>
          </div>

          {/* Continue button */}
          <div className="flex flex-col items-center gap-3">
            <button
              disabled={!canContinue}
              onClick={() => setScreen('style')}
              className={`
                w-full max-w-xs py-3 rounded-xl font-semibold text-base transition-all duration-200
                ${canContinue
                  ? 'bg-violet-600 hover:bg-violet-500 text-white shadow-lg shadow-violet-900/40 hover:shadow-violet-800/50 cursor-pointer'
                  : 'bg-[#1e1e2e] text-slate-600 cursor-not-allowed'
                }
              `}
            >
              Continue →
            </button>
            {!canContinue && (
              <p className="text-xs text-slate-600">
                Add at least 1 clip and 1 audio file to continue
              </p>
            )}
          </div>
        </div>
      </main>
    </div>
  )
}
