-- Bodega Peligrosa · tablas para Supabase.
-- Pegar COMPLETO en Supabase > SQL Editor > New query > Run. Se puede ejecutar más de una vez.
-- Prefijo bt_ para no mezclarse con tablas de otros juegos (por ejemplo, las de Obra Maldita).

create table if not exists public.bt_config (
  id        int primary key check (id = 1),          -- una sola fila
  abierto   boolean not null default false,
  ganador   text,
  datos     jsonb not null default '{}'::jsonb       -- reloj, publicación de resultados, duración
);
insert into public.bt_config (id) values (1) on conflict (id) do nothing;

create table if not exists public.bt_grupos (
  id             text primary key,
  nombre         text not null,
  sellos         int not null default 0,
  completado_en  double precision,
  datos          jsonb not null,                     -- integrantes, PIN, respuestas, expediente, rúbrica, salidas
  actualizado    timestamptz not null default now()
);

-- Seguridad: RLS activado SIN políticas = la clave pública (anon) no puede leer ni escribir.
-- Solo el servidor de Vercel, con la clave secreta, accede a los datos.
alter table public.bt_config enable row level security;
alter table public.bt_grupos enable row level security;
revoke all on public.bt_config from anon, authenticated;
revoke all on public.bt_grupos from anon, authenticated;
