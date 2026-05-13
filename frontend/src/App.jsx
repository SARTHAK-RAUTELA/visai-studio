import React from 'react'
import useEditStore from './stores/editStore.js'
import UploadZone from './components/UploadZone.jsx'
import StyleSelector from './components/StyleSelector.jsx'
import ProcessingScreen from './components/ProcessingScreen.jsx'
import PreviewPlayer from './components/PreviewPlayer.jsx'
import FineTuneEditor from './components/FineTuneEditor.jsx'
import BatchQueue from './components/BatchQueue.jsx'
import StyleDNALibrary from './components/StyleDNALibrary.jsx'

// ─── Top Navigation ────────────────────────────────────────────────────────────
function TopNav() {
  const { screen, setScreen, dnaLibraryOpen, setDnaLibraryOpen } = useEditStore()

  // Hide nav while processing
  if (screen === 'processing') return null

  return (
    <nav className="flex items-center gap-3 px-4 sm:px-6 py-3 border-b border-[#1e1e2e] bg-[#0a0a0f] sticky top-0 z-40">
      {/* Brand */}
      <button
        onClick={() => setScreen('upload')}
        className="flex items-center gap-2 shrink-0"
      >
        <div className="w-7 h-7 rounded-lg bg-violet-600 flex items-center justify-center text-white font-bold text-xs">
          V
        </div>
        <span className="text-sm font-semibold text-slate-100 tracking-tight hidden sm:inline">
          VisualAI Studio
        </span>
      </button>

      {/* Spacer */}
      <div className="flex-1" />

      {/* Nav links */}
      <div className="flex items-center gap-1">
        <button
          onClick={() => setScreen('upload')}
          className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
            screen === 'upload'
              ? 'bg-violet-900/40 text-violet-300'
              : 'text-slate-400 hover:text-slate-200 hover:bg-[#1e1e2e]'
          }`}
        >
          Home
        </button>

        <button
          onClick={() => setScreen('batch')}
          className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
            screen === 'batch'
              ? 'bg-violet-900/40 text-violet-300'
              : 'text-slate-400 hover:text-slate-200 hover:bg-[#1e1e2e]'
          }`}
        >
          Batch Queue
        </button>

        <button
          onClick={() => setDnaLibraryOpen(true)}
          className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
            dnaLibraryOpen
              ? 'bg-violet-900/40 text-violet-300'
              : 'text-slate-400 hover:text-slate-200 hover:bg-[#1e1e2e]'
          }`}
        >
          DNA Library
        </button>
      </div>
    </nav>
  )
}

// ─── Root App ──────────────────────────────────────────────────────────────────
export default function App() {
  const { screen, dnaLibraryOpen } = useEditStore()

  return (
    <div className="min-h-screen bg-[#0a0a0f] text-slate-100">
      <TopNav />

      {screen === 'upload'     && <UploadZone />}
      {screen === 'style'      && <StyleSelector />}
      {screen === 'processing' && <ProcessingScreen />}
      {screen === 'preview'    && <PreviewPlayer />}
      {screen === 'finetune'   && <FineTuneEditor />}
      {screen === 'batch'      && <BatchQueue />}

      {/* DNA Library overlay — can appear on any screen */}
      {dnaLibraryOpen && <StyleDNALibrary />}
    </div>
  )
}
