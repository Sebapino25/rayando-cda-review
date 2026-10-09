import { PROGRAMA } from './programa'

// Rayando conserva la clave de siempre (René/Cristián no tienen que volver a escribir su nombre).
const STORAGE_KEY = PROGRAMA.id === 'rayando' ? 'rayando_cda_revisor_nombre' : `${PROGRAMA.id}_revisor_nombre`

export function getReviewerName() {
  return localStorage.getItem(STORAGE_KEY) || ''
}

export function setReviewerName(name) {
  localStorage.setItem(STORAGE_KEY, name.trim())
}

export function clearReviewerName() {
  localStorage.removeItem(STORAGE_KEY)
}
