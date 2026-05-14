import { create } from 'zustand'

const useEditStore = create((set, get) => ({
  // ─── Navigation ──────────────────────────────────────────────────────────
  screen: 'upload', // 'upload' | 'style' | 'processing' | 'preview' | 'finetune' | 'batch'

  // ─── Uploaded files ───────────────────────────────────────────────────────
  clips: [],        // [{ id, name, sizeMb, thumbnail }]
  audio: null,      // { id, name } | null
  reference: null,  // { id, name } | null

  // ─── Style settings ───────────────────────────────────────────────────────
  selectedStyle: 'cinematic_travel',
  targetDuration: 30,
  aspectRatio: '9:16',
  autoCaptions: false,
  soundFx: false,
  lutIntensity: 0.85,
  styleDnaId: null,       // ref_id from reference analysis
  styleDna: null,         // Style DNA object from reference analysis
  refAnalysisStatus: 'idle', // 'idle' | 'analyzing' | 'done' | 'failed'

  // ─── Job state ────────────────────────────────────────────────────────────
  jobId: null,
  jobStatus: 'idle',  // 'idle' | 'pending' | 'processing' | 'complete' | 'failed'
  jobProgress: 0,
  jobMessage: '',
  outputUrl: null,

  // ─── Phase 4+5 state ──────────────────────────────────────────────────────
  resolution: '1080p',        // '720p' | '1080p' | '4K'
  backgroundRemoval: false,
  speedRamp: null,            // null | 'ease_in' | 'ease_out' | 'slow_mo'
  exportPreset: null,         // selected EXPORT_PRESETS id or null
  dnaLibraryOpen: false,
  batchJobs: [],              // [{ id, style, duration, aspectRatio, status, progress }]
  fineTuneJobId: null,        // job_id being fine-tuned
  timelineEdl: null,          // EDL loaded for timeline editing
  beatSync: false,            // snap cut points to beat grid
  audioDucking: false,        // compress music peaks for dialog clarity

  // ─── Actions ──────────────────────────────────────────────────────────────

  addClip: (clip) =>
    set((state) => ({
      clips: [...state.clips, clip],
    })),

  removeClip: (id) =>
    set((state) => ({
      clips: state.clips.filter((c) => c.id !== id),
    })),

  setAudio: (audio) => set({ audio }),

  setReference: (reference) => set({ reference }),

  setScreen: (screen) => set({ screen }),

  setSelectedStyle: (selectedStyle) => set({ selectedStyle }),

  setTargetDuration: (targetDuration) => set({ targetDuration }),

  setAspectRatio: (aspectRatio) => set({ aspectRatio }),

  setAdvanced: (patch) =>
    set((state) => ({
      autoCaptions:
        patch.autoCaptions !== undefined ? patch.autoCaptions : state.autoCaptions,
      soundFx:
        patch.soundFx !== undefined ? patch.soundFx : state.soundFx,
      lutIntensity:
        patch.lutIntensity !== undefined ? patch.lutIntensity : state.lutIntensity,
      beatSync:
        patch.beatSync !== undefined ? patch.beatSync : state.beatSync,
      audioDucking:
        patch.audioDucking !== undefined ? patch.audioDucking : state.audioDucking,
    })),

  setJobState: (patch) =>
    set((state) => ({
      jobId: patch.jobId !== undefined ? patch.jobId : state.jobId,
      jobStatus: patch.jobStatus !== undefined ? patch.jobStatus : state.jobStatus,
      jobProgress: patch.jobProgress !== undefined ? patch.jobProgress : state.jobProgress,
      jobMessage: patch.jobMessage !== undefined ? patch.jobMessage : state.jobMessage,
    })),

  setOutputUrl: (outputUrl) => set({ outputUrl }),

  setStyleDna: (styleDna, styleDnaId) => set({ styleDna, styleDnaId }),

  setRefAnalysisStatus: (refAnalysisStatus) => set({ refAnalysisStatus }),

  // ─── Phase 4+5 actions ────────────────────────────────────────────────────
  setResolution: (resolution) => set({ resolution }),
  setBackgroundRemoval: (backgroundRemoval) => set({ backgroundRemoval }),
  setSpeedRamp: (speedRamp) => set({ speedRamp }),
  setExportPreset: (exportPreset) => set({ exportPreset }),
  setDnaLibraryOpen: (open) => set({ dnaLibraryOpen: open }),
  addBatchJob: (job) => set((state) => ({ batchJobs: [...state.batchJobs, job] })),
  updateBatchJob: (id, patch) =>
    set((state) => ({
      batchJobs: state.batchJobs.map((j) => (j.id === id ? { ...j, ...patch } : j)),
    })),
  setFineTuneJobId: (id) => set({ fineTuneJobId: id }),
  setTimelineEdl: (edl) => set({ timelineEdl: edl }),

  reset: () =>
    set({
      screen: 'upload',
      clips: [],
      audio: null,
      reference: null,
      selectedStyle: 'cinematic_travel',
      targetDuration: 30,
      aspectRatio: '9:16',
      autoCaptions: false,
      soundFx: false,
      lutIntensity: 0.85,
      styleDnaId: null,
      styleDna: null,
      refAnalysisStatus: 'idle',
      jobId: null,
      jobStatus: 'idle',
      jobProgress: 0,
      jobMessage: '',
      outputUrl: null,
      resolution: '1080p',
      backgroundRemoval: false,
      speedRamp: null,
      exportPreset: null,
      fineTuneJobId: null,
      timelineEdl: null,
      beatSync: false,
      audioDucking: false,
    }),
}))

export default useEditStore
