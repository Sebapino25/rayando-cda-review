import { assertEquals } from 'https://deno.land/std@0.224.0/assert/mod.ts'
import { excedeLimite, MAX_INTENTOS_PIN } from './pin.ts'

Deno.test('excedeLimite es false por debajo del máximo', () => {
  assertEquals(excedeLimite(MAX_INTENTOS_PIN - 1), false)
})

Deno.test('excedeLimite es true en el máximo exacto', () => {
  assertEquals(excedeLimite(MAX_INTENTOS_PIN), true)
})

Deno.test('excedeLimite es true por encima del máximo', () => {
  assertEquals(excedeLimite(MAX_INTENTOS_PIN + 3), true)
})

Deno.test('excedeLimite es false con cero intentos', () => {
  assertEquals(excedeLimite(0), false)
})
