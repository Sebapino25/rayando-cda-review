// Nombre de la columna usada para ordenar los clips pendientes del más
// reciente al más antiguo. Cambiá esto si tu tabla usa otro nombre
// (por ejemplo "fecha_creacion" en vez del "created_at" por defecto de Supabase).
export const ORDER_COLUMN = 'created_at'

// Un clip aprobado y sin publicar que lleva más de estos días en esa
// situación deja de contar como "cola de la semana" y pasa a la pestaña
// "Antiguas" — material de reserva para cuando falte contenido. Se mide
// contra `revisado_en` (cuándo se aprobó). Tiene que coincidir con
// DIAS_LIMPIAR_RECHAZADOS en pipeline/limpiar_rechazados.py solo por
// prolijidad; son parámetros independientes.
export const RESERVA_DIAS = 30
