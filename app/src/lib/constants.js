// Nombre de la columna usada para ordenar los clips pendientes del más
// reciente al más antiguo. Cambiá esto si tu tabla usa otro nombre
// (por ejemplo "fecha_creacion" en vez del "created_at" por defecto de Supabase).
export const ORDER_COLUMN = 'created_at'

// Cuánto vive un clip aprobado sin publicar en la pestaña "Antiguas" antes de
// que la limpieza automática lo borre, contado desde su `semana` (la fecha
// del programa). Solo se usa para el texto de la UI — el filtro de qué mostrar
// es "programa anterior al vigente", no una cantidad de días. El borrado real
// lo hace pipeline/limpiar_clips.py con config.DIAS_RESERVA_ANTIGUAS (mismo
// valor).
export const RESERVA_DIAS = 30
