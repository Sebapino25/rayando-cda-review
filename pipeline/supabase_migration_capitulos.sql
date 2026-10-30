-- Rayando el CDA: capítulo de cada programa (PLAN-CAPSULAS.md, Fase 1).
-- Solo aditiva e idempotente: se puede correr de nuevo sin romper nada.
-- Aplicada contra el proyecto real el 22/10/2026.
--
-- Un capítulo = un programa. Los lunes se numeran solos (procesar_programa.py,
-- ver capitulos.py); un extraordinario (ej. un miércoles) solo recibe número
-- con --extraordinario o --capitulo N. El número NO se edita en la app: se
-- corrige con pipeline/corregir_capitulo.py, que también arregla YouTube.

create table if not exists rayando_cda.capitulos (
    numero int primary key,
    fecha date not null unique,
    tipo text not null default 'normal' check (tipo in ('normal', 'extraordinario')),
    creado_en timestamptz not null default now()
);

grant all on table rayando_cda.capitulos to service_role;
alter table rayando_cda.capitulos enable row level security;
-- Sin policies para anon/authenticated: solo el pipeline (service_role) la
-- escribe. La app arma el filtro con clips.capitulo, no lee esta tabla.

alter table rayando_cda.clips add column if not exists capitulo int;

-- Semilla: el capítulo 80 fue el lunes 19/10/2026 (el 81 es el 26/10).
insert into rayando_cda.capitulos (numero, fecha, tipo)
values (80, '2026-10-19', 'normal')
on conflict do nothing;

update rayando_cda.clips set capitulo = 80
where semana = '2026-10-19' and capitulo is null;
