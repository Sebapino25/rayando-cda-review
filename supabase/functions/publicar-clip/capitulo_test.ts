import { assertEquals } from 'https://deno.land/std@0.224.0/assert/mod.ts'
import { descripcionConCapitulo } from './capitulo.ts'

Deno.test('sin capítulo la descripción queda tal cual', () => {
  assertEquals(descripcionConCapitulo('Hola  \n', null), 'Hola  \n')
  assertEquals(descripcionConCapitulo('Hola', undefined), 'Hola')
})

Deno.test('agrega la línea y el hashtag al final', () => {
  assertEquals(
    descripcionConCapitulo('Texto del clip.', 81),
    'Texto del clip.\n\nDel capítulo 81 de Rayando el CDA\n#RECDA81',
  )
})

Deno.test('es idempotente y reemplaza un capítulo anterior', () => {
  const con80 = descripcionConCapitulo('Texto del clip.', 80)
  assertEquals(descripcionConCapitulo(con80, 80), con80)
  assertEquals(
    descripcionConCapitulo(con80, 81),
    'Texto del clip.\n\nDel capítulo 81 de Rayando el CDA\n#RECDA81',
  )
})

Deno.test('descripción vacía queda solo con el cierre', () => {
  assertEquals(descripcionConCapitulo('', 81), 'Del capítulo 81 de Rayando el CDA\n#RECDA81')
})
