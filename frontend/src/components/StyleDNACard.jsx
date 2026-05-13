import React from 'react'

function Badge({ children, color = 'violet' }) {
  const colorMap = {
    violet: 'bg-violet-900/40 text-violet-300 border-violet-800',
    emerald: 'bg-emerald-900/40 text-emerald-300 border-emerald-800',
    amber: 'bg-amber-900/40 text-amber-300 border-amber-800',
    slate: 'bg-slate-800 text-slate-300 border-slate-700',
    teal: 'bg-teal-900/40 text-teal-300 border-teal-800',
  }
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border ${colorMap[color] || colorMap.slate}`}
    >
      {children}
    </span>
  )
}

function Row({ label, value, children }) {
  return (
    <div className="flex items-center justify-between gap-3 py-1.5">
      <span className="text-xs text-slate-500 shrink-0">{label}</span>
      <span className="text-xs text-slate-200 text-right">{children || value}</span>
    </div>
  )
}

function ColorSwatch({ color, label }) {
  // Simple color representation from name
  const colorMap = {
    teal_orange: 'linear-gradient(to right, #0d9488, #f97316)',
    warm_golden: 'linear-gradient(to right, #f59e0b, #fcd34d)',
    moody_blue: 'linear-gradient(to right, #1e3a5f, #3b82f6)',
    vintage_film: 'linear-gradient(to right, #78350f, #d97706)',
    airy_bright: 'linear-gradient(to right, #e2e8f0, #f0fdf4)',
    bleach_bypass: 'linear-gradient(to right, #374151, #9ca3af)',
    pink_dream: 'linear-gradient(to right, #ec4899, #fda4af)',
    forest_green: 'linear-gradient(to right, #14532d, #4ade80)',
    cyberpunk: 'linear-gradient(to right, #06b6d4, #d946ef)',
    matte_black: 'linear-gradient(to right, #0f0f0f, #374151)',
    sunrise: 'linear-gradient(to right, #dc2626, #f97316)',
    nordic: 'linear-gradient(to right, #1e3a5f, #cbd5e1)',
  }
  const bg = colorMap[color] || 'linear-gradient(to right, #7c3aed, #a78bfa)'

  return (
    <div className="flex items-center gap-2">
      <div
        className="w-8 h-4 rounded-sm border border-white/10 shrink-0"
        style={{ background: bg }}
      />
      <span className="text-xs text-slate-200">{label || color}</span>
    </div>
  )
}

export default function StyleDNACard({ dna }) {
  if (!dna) return null

  const pacing = dna.pacing || {}
  const transitions = dna.transitions || {}
  const color = dna.color || {}
  const audioSync = dna.audio_sync || {}
  const energy = dna.energy || {}
  const motion = dna.motion || {}
  const textOverlays = dna.text_overlays || {}

  const energyColor =
    energy.level === 'high' || energy.level === 'medium_high'
      ? 'amber'
      : energy.level === 'low' || energy.level === 'medium_low'
      ? 'teal'
      : 'violet'

  return (
    <div className="rounded-xl bg-[#0d0d16] border border-violet-800/60 p-4 flex flex-col gap-4">
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div>
          <h4 className="text-sm font-semibold text-violet-300 mb-0.5">Style DNA Extracted</h4>
          {dna.overall_style && (
            <p className="text-xs text-slate-400 leading-relaxed">{dna.overall_style}</p>
          )}
        </div>
        {energy.mood && (
          <Badge color={energyColor}>{energy.mood}</Badge>
        )}
      </div>

      <div className="grid grid-cols-2 gap-4">
        {/* Color */}
        <div className="flex flex-col gap-1">
          <p className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-1">Color</p>
          {color.matched_lut && (
            <ColorSwatch color={color.matched_lut} label={color.matched_lut.replace(/_/g, ' ')} />
          )}
          <div className="flex flex-col">
            {color.overall_temperature && (
              <Row label="Temp">{color.overall_temperature}</Row>
            )}
            {color.saturation_level && (
              <Row label="Saturation">{color.saturation_level}</Row>
            )}
            {color.contrast_level && (
              <Row label="Contrast">{color.contrast_level}</Row>
            )}
            <Row label="Vignette">
              {color.has_vignette ? (
                <Badge color="slate">{color.vignette_strength || 'yes'}</Badge>
              ) : (
                <span className="text-slate-500">none</span>
              )}
            </Row>
            <Row label="Film grain">
              {color.has_film_grain ? (
                <Badge color="slate">yes</Badge>
              ) : (
                <span className="text-slate-500">none</span>
              )}
            </Row>
          </div>
        </div>

        {/* Pacing & Transitions */}
        <div className="flex flex-col gap-1">
          <p className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-1">Pacing</p>
          {pacing.avg_clip_duration && (
            <Row label="Avg clip">{pacing.avg_clip_duration.toFixed(1)}s</Row>
          )}
          {pacing.cuts_per_second && (
            <Row label="Cuts/sec">{pacing.cuts_per_second.toFixed(2)}</Row>
          )}
          {pacing.pacing_style && (
            <Row label="Style">{pacing.pacing_style.replace(/_/g, ' ')}</Row>
          )}
          {transitions.dominant_transition && (
            <Row label="Main transition">
              <Badge color="slate">{transitions.dominant_transition.replace(/_/g, ' ')}</Badge>
            </Row>
          )}
          {audioSync.is_beat_synced !== undefined && (
            <Row label="Beat sync">
              {audioSync.is_beat_synced ? (
                <Badge color="emerald">yes — {audioSync.sync_frequency || 'synced'}</Badge>
              ) : (
                <span className="text-slate-500">no</span>
              )}
            </Row>
          )}
        </div>
      </div>

      {/* Motion & Text */}
      <div className="grid grid-cols-2 gap-4 pt-1 border-t border-[#1e1e2e]">
        <div>
          <p className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-1">Motion</p>
          {motion.speed_ramps_detected && (
            <Badge color="amber">speed ramps</Badge>
          )}
          {motion.slow_motion_used && (
            <Badge color="teal">slow-mo</Badge>
          )}
          {!motion.speed_ramps_detected && !motion.slow_motion_used && (
            <span className="text-xs text-slate-500">standard speed</span>
          )}
        </div>
        <div>
          <p className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-1">Text</p>
          {textOverlays.present ? (
            <div className="flex flex-wrap gap-1">
              <Badge color="slate">{textOverlays.position || 'lower_third'}</Badge>
              <Badge color="slate">{textOverlays.frequency || 'sparse'}</Badge>
            </div>
          ) : (
            <span className="text-xs text-slate-500">no text detected</span>
          )}
        </div>
      </div>

      {/* Claude analysis */}
      {dna.claude_analysis && (
        <div className="pt-2 border-t border-[#1e1e2e]">
          <p className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-1">Claude's Analysis</p>
          <p className="text-xs text-slate-300 leading-relaxed italic">
            "{dna.claude_analysis}"
          </p>
        </div>
      )}

      {/* Energy badge */}
      {energy.level && (
        <div className="flex items-center gap-2 flex-wrap">
          <Badge color={energyColor}>
            {energy.level.replace(/_/g, ' ')} energy
          </Badge>
          {energy.emotional_tone && (
            <Badge color="slate">{energy.emotional_tone}</Badge>
          )}
          {energy.platform_feel && (
            <Badge color="slate">{energy.platform_feel.replace(/_/g, ' ')}</Badge>
          )}
        </div>
      )}
    </div>
  )
}
