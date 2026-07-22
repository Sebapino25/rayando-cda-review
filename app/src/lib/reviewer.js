const STORAGE_KEY = 'rayando_cda_revisor_nombre'

export function getReviewerName() {
  return localStorage.getItem(STORAGE_KEY) || ''
}

export function setReviewerName(name) {
  localStorage.setItem(STORAGE_KEY, name.trim())
}

export function clearReviewerName() {
  localStorage.removeItem(STORAGE_KEY)
}
