export const MAX_INTENTOS_PIN = 5
export const VENTANA_MINUTOS_PIN = 10

export function excedeLimite(intentosRecientes: number): boolean {
  return intentosRecientes >= MAX_INTENTOS_PIN
}
