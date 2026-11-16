# Publicar Bodega Peligrosa en Vercel + Supabase

Tiempo estimado: 20 a 30 minutos la primera vez. Necesita cuentas en **GitHub**, **Supabase** y **Vercel** (las tres tienen plan gratuito).

## Qué contiene esta carpeta (lo único que se sube)

```
api/index.py        servidor del juego (Python, sin dependencias)
api/banco.json      preguntas y RESPUESTAS: queda dentro del servidor, no es público
api/logo.jpg        logo para los PDF
public/             pantalla de grupos (index.html), panel docente (docente.html), gráficos y Archivo 142
vercel.json         enrutado y configuración de la función
supabase.sql        tablas de la base de datos
.env.example        nombres de las variables (sin valores)
.gitignore
```

**No están en esta carpeta, a propósito:** la lista de estudiantes (`grupos_semana4.txt`), el solucionario y la matriz. Están en la carpeta superior, solo para usted.

## Paso 1 · Supabase (base de datos)

1. En supabase.com → **New project**. Nombre sugerido: `bodega-peligrosa`. Elija una región cercana (por ejemplo **East US**). Guarde la contraseña de la base.
2. Abra **SQL Editor → New query**, pegue **todo** `supabase.sql` y pulse **Run**. Crea las tablas `bt_config` y `bt_grupos` (con prefijo `bt_`, para no chocar con las de Obra Maldita si usa el mismo proyecto).
3. En **Project Settings → API Keys** copie:
   - **Project URL** → será `SUPABASE_URL`.
   - La clave **secreta** del servidor: la nueva `sb_secret_…` o, en proyectos antiguos, la `service_role` (empieza con `eyJ…`). Cualquiera de las dos sirve → será `SUPABASE_SERVICE_KEY`.
4. **Nunca** ponga la clave secreta en el navegador, en un mensaje ni en GitHub. Da control total de la base. Esa clave la pega **usted**, directamente en Vercel.

## Paso 2 · GitHub

1. Cree un repositorio **privado** (por ejemplo `bodega-peligrosa`). Debe ser privado porque `api/banco.json` contiene las respuestas.
2. Suba el **contenido** de esta carpeta (en GitHub: **Add file → Upload files**). Abra la carpeta `publicar-vercel` en el Explorador, seleccione **todo lo que hay dentro** (las carpetas `api` y `public` y los archivos sueltos) y arrástrelo a la página; luego pulse **Commit changes**. `vercel.json` debe quedar en la raíz del repositorio, no dentro de otra carpeta.
3. Compruebe que en el repositorio se ven `api/index.py`, `api/banco.json`, `public/index.html`, la carpeta `public/img` y `vercel.json`.

## Paso 3 · Vercel

1. En vercel.com → **Add New… → Project** → importe el repositorio.
2. **Framework Preset: Other.** Deje **Root Directory** en la raíz y sin comandos de build.
3. En **Environment Variables** agregue estas 4 (nombres exactos):

| Nombre | Valor |
|---|---|
| `SUPABASE_URL` | URL del paso 1 |
| `SUPABASE_SERVICE_KEY` | Clave secreta del paso 1 (también se aceptan los nombres `SUPABASE_SECRET_KEY` y `SUPABASE_SERVICE_ROLE_KEY`) |
| `DOCENTE_CLAVE` | Una clave larga que solo usted sabrá (para entrar a `/docente`) |
| `SESSION_SECRET` | Una cadena aleatoria larga |

Los valores de `DOCENTE_CLAVE` y `SESSION_SECRET` ya están generados en el archivo privado `CLAVES_VERCEL_PRIVADO.txt` (carpeta superior, no se sube): ábralo y copie cada valor. Marque las cuatro variables para **Production** (y Preview, si aparece).

4. Pulse **Deploy**. Vercel le dará una dirección como `https://bodega-peligrosa.vercel.app`.

## Paso 4 · Ensayo antes de la clase (10 minutos)

1. Abra `https://SU-DIRECCION/docente` y entre con `DOCENTE_CLAVE`.
2. En **Crear grupos** pegue dos grupos de prueba: `Prueba X;1111;Ana Pérez, Luis Paredes` y `Prueba Y;2222;Rosa Cruz, Pedro Vera`.
3. Abra la dirección principal en dos celulares, entre (acertijo o PIN) y pulse **Abrir para todos** en el panel.
4. Responda unas preguntas, cambie de app en un celular (debe contar una salida), abra el Archivo 142 y la Matriz, y revise que el panel se actualice.
5. Pulse **Borrar todo y empezar de cero**. Luego pegue las 5 líneas del archivo privado `grupos_semana4.txt` (carpeta superior). **El orden importa:** A, B, D, E, F, como vienen en el archivo, para que cada grupo reciba el caso indicado en el solucionario.

## Durante la clase

- Antes de abrir, revise **Preguntas por zona** en el panel: debe quedar en **5 de 10 (85 min)**, que es lo que cabe en una clase de 90. Con 6 o 7 la actividad dura 105 o 115 minutos. Una vez abierto el juego ya no se puede cambiar.
- **Abrir para todos** inicia el reloj de 85 minutos. **Pausar** lo detiene; **+5 min / −5 min** lo ajustan.
- Al llegar a 0, los grupos no pueden responder más; el expediente y el reto final se entregan solos con lo guardado.
- Califique cada expediente en «detalle y rúbrica». Cuando termine, pulse **Publicar resultados**: cada grupo verá su rúbrica y su PDF tendrá el detalle con explicaciones.
- **Informe PDF del curso** descarga el resumen de todos los grupos; en cada ficha está el **PDF de este grupo**.

## Si algo falla

| Síntoma | Causa probable |
|---|---|
| «Servidor sin configurar (faltan variables…)» | Falta `SESSION_SECRET` o `DOCENTE_CLAVE`. Agréguela y haga **Redeploy**. |
| «Error temporal de base de datos» | `SUPABASE_URL` o la clave están mal, o no se ejecutó `supabase.sql`. |
| La página carga, pero `/api/...` da 404 | `vercel.json` no está en la raíz: se subió la carpeta superior en vez de su contenido. |
| Clave del docente «incorrecta» | Revise `DOCENTE_CLAVE`; tras cambiar variables hay que hacer **Redeploy**. |
| Otro error | Vercel → **Deployments → el despliegue → Logs**. Copie el mensaje para corregirlo. |

## Privacidad

- La base guarda nombres de grupos e integrantes, PIN, respuestas, salidas y notas. Al terminar el período, use **Borrar todo** o vacíe la tabla `bt_grupos`.
- El acertijo y el PIN son un mecanismo de aula, no una autenticación fuerte: el docente presente es el control principal.
- Revise que el plan gratuito de Vercel corresponda a su uso (el plan Hobby es para uso personal no comercial).
