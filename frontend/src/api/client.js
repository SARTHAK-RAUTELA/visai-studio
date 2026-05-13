import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 60000,
})

// Response interceptor for consistent error handling
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const message =
      error.response?.data?.detail ||
      error.response?.data?.message ||
      error.message ||
      'An unexpected error occurred'
    return Promise.reject(new Error(message))
  }
)

/**
 * Upload video clips or audio file.
 * formData should include the file field named "file".
 * Returns { file_id, name, size }
 */
export function uploadFiles(formData, onUploadProgress) {
  return api.post('/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress,
  })
}

/**
 * Upload a reference video (file or URL).
 * formData may include "file" (binary) or "url" (string).
 * Returns { file_id, name }
 */
export function uploadReference(formData, onUploadProgress) {
  return api.post('/upload/reference', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress,
  })
}

/**
 * Start a reference video analysis job.
 * payload: { reference_type: 'file' | 'url', url?: string, or_file_id?: string }
 * Returns { ref_id }
 */
export function analyzeReference(payload) {
  return api.post('/analyze/reference', payload)
}

/**
 * Poll for reference analysis result.
 * Returns Style DNA object with status field.
 */
export function getReferenceResult(refId) {
  return api.get(`/analyze/reference/${refId}`)
}

/**
 * Get all 8 built-in styles.
 * Returns array of style objects.
 */
export function getStyles() {
  return api.get('/styles')
}

/**
 * Start an edit generation job.
 * payload: { clip_ids, audio_id, style, style_dna_id, target_duration,
 *            aspect_ratio, auto_captions, sound_fx, lut_intensity }
 * Returns { job_id }
 */
export function generateEdit(payload) {
  return api.post('/generate', payload)
}

/**
 * Get job status and progress.
 * Returns { job_id, status, progress, message }
 */
export function getJobStatus(jobId) {
  return api.get(`/job/${jobId}/status`)
}

/**
 * Get job result (download URL or stream).
 * Returns download URL or blob depending on backend.
 */
export function getJobResult(jobId) {
  return api.get(`/job/${jobId}/result`)
}

// ─── Phase 4+5 API calls ──────────────────────────────────────────────────────

/**
 * Fine-tune an existing edit.
 * adjustments: { lut_override, lut_intensity, brightness, contrast, saturation,
 *                clip_transitions, remove_text_overlays, new_text_overlays }
 * Returns { job_id }
 */
export function fineTuneEdit(jobId, adjustments) {
  return api.post(`/finetune/${jobId}`, adjustments)
}

/** GET /api/dna — returns { library: [...] } */
export function getDnaLibrary() {
  return api.get('/dna')
}

/** POST /api/dna — save a named Style DNA */
export function saveDna(payload) {
  return api.post('/dna', payload)
}

/** GET /api/dna/:name */
export function getDna(name) {
  return api.get(`/dna/${name}`)
}

/** DELETE /api/dna/:name */
export function deleteDna(name) {
  return api.delete(`/dna/${name}`)
}

/** POST /api/batch — start batch processing */
export function startBatch(jobs) {
  return api.post('/batch', { jobs })
}

/** GET /api/batch/:batchId — batch status */
export function getBatchStatus(batchId) {
  return api.get(`/batch/${batchId}`)
}

/** GET /api/history */
export function getHistory() {
  return api.get('/history')
}

/** GET /api/history/:jobId — get EDL for a past job */
export function getHistoryEdl(jobId) {
  return api.get(`/history/${jobId}`)
}

/** GET /api/analytics */
export function getAnalytics() {
  return api.get('/analytics')
}

export default api
