"""
Bodega Peligrosa · Código de Contención — servidor del juego (Python, sin dependencias externas).

Funciona de dos maneras con el MISMO código:
  * Vercel (función Python) + Supabase: si existen SUPABASE_URL y SUPABASE_SERVICE_KEY.
  * Local (servidor_local.py): guarda el estado en datos/estado.json.
Variables en Vercel: SUPABASE_URL, SUPABASE_SERVICE_KEY, DOCENTE_CLAVE, SESSION_SECRET.
La clave service_role SOLO se usa aquí. Nunca llega al navegador. banco.json (con las respuestas) tampoco.
"""
import hashlib, hmac, json, math, os, random, secrets, sys, textwrap, threading, time, traceback, unicodedata
import urllib.error, urllib.parse, urllib.request
from http.server import BaseHTTPRequestHandler

HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(HERE, "banco.json"), encoding="utf-8") as _f:
    BANCO = json.load(_f)

# ---------------------------------------------------------------- reglas
SELLOS_POR_ZONA = 4
UMBRALES = [(0.85, 4), (0.65, 3), (0.45, 2), (0.25, 1)]      # fracción de la zona -> sellos
SALIDAS_GRATIS = 2
DESCUENTO_SALIDA = 0.5
NOTA_MAX = 10.0
PESO_ZONAS = float(BANCO["pesos"]["zonas"])                   # 7,0
PESO_RETO = float(BANCO["pesos"]["reto"])                     # 1,0 (10 %)
PESO_DOCENTE = float(BANCO["pesos"]["docente"])               # 2,0 (20 %)
MIN_RETO_GANAR = 0.5
DURACION_SESION = 12 * 3600
DURACION_DEF = int(BANCO.get("duracion_min", 80))

TEMAS = BANCO["temas"]
NUM_TEMAS = len(TEMAS)
TOTAL_SELLOS = NUM_TEMAS * SELLOS_POR_ZONA
PESO_ZONA = PESO_ZONAS / NUM_TEMAS
PREG = {}
for _t in TEMAS:
    for _q in _t["preguntas"]:
        PREG[_q["id"]] = (_q, _t["id"], False)
    for _q in _t.get("extras", []):
        PREG[_q["id"]] = (_q, _t["id"], True)
TOTAL_PRINCIPAL = sum(len(t["preguntas"]) for t in TEMAS)
EXP = BANCO["expediente"]
CRITERIOS = EXP["criterios"]
RETO = BANCO["reto_final"]
TEMA = {t["id"]: t for t in TEMAS}

# Matriz de incompatibilidades del Anexo K de la NTE INEN 2266 (V compatible, A precaución, R incompatible)
CLASES_K = ["1", "2.1", "2.2", "2.3", "3", "4.1", "4.2", "4.3", "5.1", "5.2", "6", "7", "8", "9"]
_FILAS_K = ["AAAAAAAAAAAAAA", "AVVAVVVVVVRRVA", "AVVVVVVVVVVVVA", "AAVVRRRRRRVVRA", "AVVRVVVVRVAVVA",
            "AVVRVVVVRVAVRA", "AVVRVVVVRVAVRA", "AVVRVVVVRVAVRA", "AVVRRRRRVVAVRA", "AVVRVVVVVVAVRA",
            "ARVVAAAAAAVVAA", "ARVVVVVVVVVVVA", "AVVRVRARRRAVAA", "AAAAAAAAAAAAAA"]
MATRIZ = {(a, b): _FILAS_K[i][j] for i, a in enumerate(CLASES_K) for j, b in enumerate(CLASES_K)}


def compat(a, b):
    """El peor de los dos sentidos de la tabla (la tabla publicada no es del todo simétrica)."""
    x, y = MATRIZ.get((a, b), "A"), MATRIZ.get((b, a), "A")
    for nivel in ("R", "A", "V"):
        if nivel in (x, y):
            return nivel
    return "A"


def env(n):
    v = os.environ.get(n, "").strip()
    if not v and n == "SUPABASE_SERVICE_KEY":
        # nombres alternativos: integración Supabase–Vercel y claves nuevas sb_secret_...
        v = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "") or os.environ.get("SUPABASE_SECRET_KEY", "")).strip()
    return v


# ---------------------------------------------------------------- almacenamiento
class ErrorBD(Exception):
    pass


CONFIG_INICIAL = {"abierto": False, "ganador": None,
                  "datos": {"iniciado_en": None, "fin_en": None, "pausado_en": None, "publicado": False,
                            "duracion_min": DURACION_DEF}}


class Supabase:
    def __init__(self):
        self.base = env("SUPABASE_URL").rstrip("/") + "/rest/v1"
        self.key = env("SUPABASE_SERVICE_KEY")

    def _req(self, metodo, ruta, cuerpo=None, extra=None):
        h = {"apikey": self.key, "Content-Type": "application/json"}
        if self.key.startswith("eyJ"):          # clave service_role clásica (JWT); las sb_secret_ van solo en apikey
            h["Authorization"] = "Bearer " + self.key
        h.update(extra or {})
        data = json.dumps(cuerpo).encode() if cuerpo is not None else None
        r = urllib.request.Request(self.base + ruta, data=data, headers=h, method=metodo)
        try:
            with urllib.request.urlopen(r, timeout=10) as x:
                raw = x.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            print("Supabase HTTP", e.code, e.read()[:300], file=sys.stderr)
            raise ErrorBD()
        except Exception as e:
            print("Supabase error", repr(e), file=sys.stderr)
            raise ErrorBD()

    def config(self):
        r = self._req("GET", "/bt_config?id=eq.1&select=abierto,ganador,datos")
        if not r:
            return json.loads(json.dumps(CONFIG_INICIAL))
        c = r[0]
        d = dict(CONFIG_INICIAL["datos"])
        d.update(c.get("datos") or {})
        return {"abierto": bool(c.get("abierto")), "ganador": c.get("ganador"), "datos": d}

    def set_config(self, cfg):
        self._req("PATCH", "/bt_config?id=eq.1", {"abierto": cfg["abierto"], "ganador": cfg["ganador"], "datos": cfg["datos"]},
                  {"Prefer": "return=minimal"})

    def claim_ganador(self, gid):
        r = self._req("PATCH", "/bt_config?id=eq.1&ganador=is.null", {"ganador": gid}, {"Prefer": "return=representation"})
        return bool(r)

    def grupos(self):
        return {r["id"]: r["datos"] for r in self._req("GET", "/bt_grupos?select=id,datos") or []}

    def grupo(self, gid):
        r = self._req("GET", "/bt_grupos?id=eq." + urllib.parse.quote(str(gid), safe="") + "&select=datos")
        return r[0]["datos"] if r else None

    def guardar_grupo(self, g):
        self._req("POST", "/bt_grupos", {"id": g["id"], "nombre": g["nombre"], "sellos": total_sellos(g),
                                         "completado_en": g.get("completado_en"), "datos": g},
                  {"Prefer": "resolution=merge-duplicates,return=minimal"})

    def eliminar(self, gid):
        self._req("DELETE", "/bt_grupos?id=eq." + urllib.parse.quote(str(gid), safe=""), None, {"Prefer": "return=minimal"})

    def resumen(self):
        return self._req("GET", "/bt_grupos?select=id,nombre,sellos,completado_en") or []

    def borrar_todo(self):
        self._req("DELETE", "/bt_grupos?id=neq.__ninguno__", None, {"Prefer": "return=minimal"})
        self.set_config(json.loads(json.dumps(CONFIG_INICIAL)))


class Local:
    """Estado en un archivo JSON (versión de aula sin internet)."""
    LOCK = threading.RLock()

    def __init__(self, carpeta):
        self.carpeta = carpeta
        os.makedirs(carpeta, exist_ok=True)
        self.ruta = os.path.join(carpeta, "estado.json")

    def _leer(self):
        try:
            with open(self.ruta, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"config": json.loads(json.dumps(CONFIG_INICIAL)), "grupos": {}}

    def _escribir(self, e):
        tmp = self.ruta + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(e, f, ensure_ascii=False)
        os.replace(tmp, self.ruta)

    def config(self):
        with self.LOCK:
            c = self._leer()["config"]
            d = dict(CONFIG_INICIAL["datos"])
            d.update(c.get("datos") or {})
            return {"abierto": bool(c.get("abierto")), "ganador": c.get("ganador"), "datos": d}

    def set_config(self, cfg):
        with self.LOCK:
            e = self._leer()
            e["config"] = cfg
            self._escribir(e)

    def claim_ganador(self, gid):
        with self.LOCK:
            e = self._leer()
            if e["config"].get("ganador"):
                return False
            e["config"]["ganador"] = gid
            self._escribir(e)
            return True

    def grupos(self):
        with self.LOCK:
            return self._leer()["grupos"]

    def grupo(self, gid):
        with self.LOCK:
            return self._leer()["grupos"].get(str(gid))

    def guardar_grupo(self, g):
        with self.LOCK:
            e = self._leer()
            e["grupos"][g["id"]] = g
            self._escribir(e)

    def eliminar(self, gid):
        with self.LOCK:
            e = self._leer()
            e["grupos"].pop(str(gid), None)
            self._escribir(e)

    def resumen(self):
        return [{"id": g["id"], "nombre": g["nombre"], "sellos": total_sellos(g), "completado_en": g.get("completado_en")}
                for g in self.grupos().values()]

    def borrar_todo(self):
        with self.LOCK:
            self._escribir({"config": json.loads(json.dumps(CONFIG_INICIAL)), "grupos": {}})


_DB = None
LOCK = threading.Lock()


def get_db():
    global _DB
    if _DB is None:
        if env("SUPABASE_URL") and env("SUPABASE_SERVICE_KEY"):
            _DB = Supabase()
        else:
            _DB = Local(os.environ.get("BT_DATOS") or os.path.join(os.path.dirname(HERE), "datos"))
    return _DB


def secreto_sesion():
    return env("SESSION_SECRET") or os.environ.get("BT_SECRETO_LOCAL", "")


def firmar(gid):
    cuerpo = f"{gid}.{int(time.time()) + DURACION_SESION}"
    sig = hmac.new(secreto_sesion().encode(), cuerpo.encode(), hashlib.sha256).hexdigest()[:40]
    return f"{cuerpo}.{sig}"


def verificar(tok):
    try:
        gid, exp, sig = tok.split(".")
        esperado = hmac.new(secreto_sesion().encode(), f"{gid}.{exp}".encode(), hashlib.sha256).hexdigest()[:40]
        if secreto_sesion() and hmac.compare_digest(sig, esperado) and int(exp) > time.time():
            return gid
    except Exception:
        pass
    return None


# ---------------------------------------------------------------- grupos e ingreso
def nuevo_grupo(nombre, pin, integrantes, orden):
    gid = "g" + secrets.token_hex(3)
    return {
        "id": gid, "nombre": nombre.strip()[:60], "pin": str(pin), "integrantes": integrantes.strip()[:400], "orden": orden,
        "resp": {}, "reto": None, "reto_borrador": None, "exp": {"borrador": {}, "entregado_en": None},
        "rubrica": {}, "manual": {}, "salidas": [], "salidas_cierre": None,
        "cierre": None, "completado_en": None, "ultimo_latido": 0, "creado": time.time(), "fallos": 0, "bloqueo_hasta": 0,
    }


def _sin_tildes(s):
    s = unicodedata.normalize("NFD", str(s))
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def _norm(s):
    return " ".join(_sin_tildes(s).lower().split())


def integrantes_lista(g):
    return [p.strip() for p in str(g.get("integrantes", "")).replace(";", ",").replace("\n", ",").split(",") if p.strip()]


def revolver(nombre, semilla):
    palabras = []
    for w in _sin_tildes(nombre).upper().split():
        letras = list(w)
        r = random.Random(f"{semilla}:{w}")
        for _ in range(12):
            r.shuffle(letras)
            if "".join(letras) != w or len(set(w)) == 1:
                break
        palabras.append("".join(letras))
    return " ".join(palabras)


# Acertijos temáticos de ingreso: uno por grupo (según el orden de creación). Las respuestas quedan en el servidor.
ACERTIJOS = [
    {"pista": "Me ves en un rombo rojo con una llama. Basta una chispa cerca de mis vapores para que todo arda. En el AM 142 soy la letra I del CRTIB.",
     "respuesta": "INFLAMABLE", "acepta": ["INFLAMABLE", "INFLAMABLES"]},
    {"pista": "Quemo la piel y muerdo el metal y el cemento; si tengo pH menor que 2 o mayor que 12,5, ya sabes quién soy. En el AM 142 soy la letra C del CRTIB.",
     "respuesta": "CORROSIVO", "acepta": ["CORROSIVO", "CORROSIVA", "CORROSIVOS", "CORROSIVIDAD"]},
    {"pista": "No necesito fuego para causar problemas: con agua, con aire o con un golpe reacciono con violencia y hasta exploto. En el AM 142 soy la letra R del CRTIB.",
     "respuesta": "REACTIVO", "acepta": ["REACTIVO", "REACTIVA", "REACTIVOS", "REACTIVIDAD"]},
    {"pista": "Una pequeña dosis tragada, respirada o sobre la piel puede enfermarte o matarte; los plaguicidas caducados casi siempre me llevan. En el AM 142 soy la letra T del CRTIB.",
     "respuesta": "TOXICO", "acepta": ["TOXICO", "TOXICA", "TOXICOS", "TOXICIDAD"]},
    {"pista": "Vengo de la sangre, los fluidos y los cultivos de laboratorio; cargo microbios que contagian enfermedades. En el AM 142 soy la letra B del CRTIB.",
     "respuesta": "BIOLOGICO", "acepta": ["BIOLOGICO", "BIOLOGICA", "BIOLOGICOINFECCIOSO", "INFECCIOSO", "BIOPELIGROSO", "BIOLOGICOS"]},
]


def acertijo_de(g):
    return ACERTIJOS[int(g.get("orden", 0)) % len(ACERTIJOS)]


def acertijo(g):
    a = acertijo_de(g)
    return {"pista": a["pista"], "letras": revolver(a["respuesta"], g["id"]), "largo": len(a["respuesta"])}


def respuesta_valida(g, texto):
    t = "".join(c for c in _sin_tildes(texto).upper() if c.isalpha())
    return bool(t) and t in acertijo_de(g)["acepta"]


def intentar_ingreso(g, b):
    ahora = time.time()
    if ahora < g.get("bloqueo_hasta", 0):
        return "bloqueado"
    ok = False
    if str(b.get("respuesta", "")).strip():
        ok = respuesta_valida(g, b["respuesta"])
    if not ok and str(b.get("pin", "")).strip():
        ok = secrets.compare_digest(str(b["pin"]).strip(), str(g["pin"]))
    if ok:
        g["fallos"] = 0
        return "ok"
    g["fallos"] = g.get("fallos", 0) + 1
    if g["fallos"] >= 5:
        g["bloqueo_hasta"], g["fallos"] = ahora + 60, 0
    return "mal"


def responsable(g, i):
    m = integrantes_lista(g)
    return m[i % len(m)] if m else ""


# ---------------------------------------------------------------- tiempo
def tiempo(cfg, ahora=None):
    ahora = ahora or time.time()
    d = cfg["datos"]
    fin = d.get("fin_en")
    if not fin:
        return {"iniciado": False, "restante": d.get("duracion_min", DURACION_DEF) * 60, "agotado": False, "fin_en": None}
    ref = d.get("pausado_en") or ahora
    rest = max(0, fin - ref)
    return {"iniciado": True, "restante": int(rest), "agotado": rest <= 0, "fin_en": fin, "pausado": bool(d.get("pausado_en"))}


def puede_jugar(cfg):
    return cfg["abierto"] and not tiempo(cfg)["agotado"]


# ---------------------------------------------------------------- variantes y vistas
def variante_pool(g):
    return (int(g.get("orden", 0)) + 2) % 5


def variante_exp(g):
    vs = EXP["variantes"]
    return vs[int(g.get("orden", 0)) % len(vs)]


def item_de(g, q):
    """Resuelve un ítem con variantes (pool) para el grupo."""
    if q.get("pool"):
        v = q["variantes"][variante_pool(g) % len(q["variantes"])]
        x = dict(q)
        x.update(v)
        x["variante"] = variante_pool(g) % len(q["variantes"]) + 1
        return x
    return q


POR_ZONA_DEF = int(BANCO.get("por_zona", 5))
TIEMPOS_POR_ZONA = {int(k): int(v) for k, v in BANCO.get("tiempos_por_zona", {}).items()}


def asignar(g, n):
    """Preguntas que le tocan al grupo en cada zona: las fijas (relacionar, completar y minijuego) más otras
    del banco, elegidas al azar de forma estable para ese grupo. Se guardan en el grupo y no cambian después."""
    out = {}
    for t in TEMAS:
        fijas = [q["id"] for q in t["preguntas"] if q.get("fija")]
        resto = [q["id"] for q in t["preguntas"] if not q.get("fija")]
        random.Random(f"{g['id']}:banco:{t['id']}").shuffle(resto)
        nz = (n + int(BANCO.get("ajuste_zona", {}).get(str(t["id"]), 0))) if n < 10 else len(t["preguntas"])   # la zona 4 trae dos hojas largas
        ids = fijas + resto[:max(0, nz - len(fijas))]
        random.Random(f"{g['id']}:orden:{t['id']}").shuffle(ids)
        out[str(t["id"])] = ids
    g["asig"] = out
    g["por_zona"] = n
    g["asig_v"] = BANCO["version"]
    return out


def preguntas_zona(g, tema):
    a = g.get("asig") or asignar(g, POR_ZONA_DEF)
    return a[str(tema)]


def ids_extra(g, tema):
    """Retos extra de la zona: las preguntas del banco que no le tocaron al grupo y los extras propios."""
    asig = set(preguntas_zona(g, tema))
    return [q["id"] for q in TEMA[tema]["preguntas"] if q["id"] not in asig] + [q["id"] for q in TEMA[tema].get("extras", [])]


def vista_pregunta(g, q):
    q = item_de(g, q)
    base = {"id": q["id"], "tipo": q["tipo"], "enunciado": q["enunciado"], "nivel": q.get("nivel", ""),
            "n_correctas": q.get("n_correctas")}
    rnd = random.Random(f"{g['id']}:{q['id']}")
    if q["tipo"] == "match":
        idx = list(range(len(q["derecha"])))
        rnd.shuffle(idx)
        base["izquierda"] = list(q["izquierda"])
        base["derecha"] = [{"k": i, "texto": q["derecha"][i]} for i in idx]
        return base
    if q["tipo"] == "fill":
        idx = list(range(len(q["banco"])))
        rnd.shuffle(idx)
        base["texto"] = q["texto"]
        base["huecos"] = len(q["correcta"])
        base["banco"] = [{"k": i, "texto": q["banco"][i]} for i in idx]
        return base
    if q["tipo"] == "bodega":
        base["tambores"] = q["tambores"]
        base["jaulas"] = q["jaulas"]
        return base
    if q["tipo"] == "fds":
        secs = []
        for i, s in enumerate(q["hoja"]["secciones"]):
            idx = list(range(len(s["opciones"])))
            random.Random(f"{g['id']}:{q['id']}:{i}").shuffle(idx)
            secs.append({"n": s["n"], "titulo": s["titulo"], "texto": s["texto"], "opciones": [{"k": j, "texto": s["opciones"][j]} for j in idx]})
        base["hoja"] = {"producto": q["hoja"]["producto"], "nota": q["hoja"].get("nota", ""), "secciones": secs}
        base["huecos"] = len(secs)
        return base
    if q["tipo"] == "sopa":
        base["grid"] = q["grid"]
        base["n"] = q["n"]
        base["palabras"] = [{"i": i, "largo": len(p["palabra"]), "pista": p["pista"]} for i, p in enumerate(q["palabras"])]
        return base
    if q["tipo"] == "cruci":
        base.update({"filas": q["filas"], "cols": q["cols"], "entradas": [
            {"clave": f"{e['n']}{e['dir']}", "n": e["n"], "dir": e["dir"], "r": e["r"], "c": e["c"], "largo": len(e["respuesta"]), "pista": e["pista"]}
            for e in q["entradas"]]})
        return base
    idx = list(range(len(q["opciones"])))
    rnd.shuffle(idx)
    if q["tipo"] == "order" and idx == list(range(len(idx))):
        idx = idx[1:] + idx[:1]
    base["opciones"] = [{"k": i, "texto": q["opciones"][i]} for i in idx]
    return base


def pares_incompatibles(q):
    t = q["tambores"]
    return [(i, j) for i in range(len(t)) for j in range(i + 1, len(t)) if compat(t[i]["clase"], t[j]["clase"]) == "R"]


def corregir(q, sel):
    """Puntos de 0 a 1. Relacionar, completar, bodega, minijuegos y selección múltiple dan crédito parcial."""
    if q["tipo"] == "cruci":
        if not isinstance(sel, dict):
            return 0.0
        ok = sum(1 for e in q["entradas"] if _pal(sel.get(f"{e['n']}{e['dir']}", "")) == e["respuesta"])
        return ok / len(q["entradas"])
    if not isinstance(sel, list):
        return 0.0
    if q["tipo"] == "sopa":
        objetivo = {p["palabra"] for p in q["palabras"]}
        halladas = set()
        for s in sel[:30]:
            try:
                txt = _linea(q["grid"], *s)
            except Exception:
                continue
            for w in (txt, (txt or "")[::-1]):
                if w in objetivo:
                    halladas.add(w)
        return len(halladas) / len(objetivo)
    try:
        if q["tipo"] == "single":
            return 1.0 if len(sel) == 1 and sel[0] in q["correcta"] else 0.0
        if q["tipo"] == "multi":
            s = set(x for x in sel if isinstance(x, int))
            c = set(q["correcta"])
            return max(0.0, (len(s & c) - len(s - c)) / len(c))
        if q["tipo"] == "order":
            return 1.0 if sel == list(range(len(q["opciones"]))) else 0.0
        if q["tipo"] in ("match", "fill", "fds"):
            n = len(q["correcta"])
            if len(sel) != n:
                return 0.0
            return sum(1 for a, b in zip(sel, q["correcta"]) if a == b) / n
        if q["tipo"] == "bodega":
            nt, nj = len(q["tambores"]), len(q["jaulas"])
            if len(sel) != nt or any(not isinstance(x, int) or not 0 <= x < nj for x in sel):
                return 0.0
            pares = pares_incompatibles(q)
            return sum(1 for i, j in pares if sel[i] != sel[j]) / len(pares)
    except Exception:
        return 0.0
    return 0.0


def texto_correcto(q):
    if q["tipo"] == "order":
        return list(q["opciones"])
    if q["tipo"] == "match":
        return [f"{a}  →  {q['derecha'][c]}" for a, c in zip(q["izquierda"], q["correcta"])]
    if q["tipo"] == "fill":
        return [f"({i + 1}) {q['banco'][c]}" for i, c in enumerate(q["correcta"])]
    if q["tipo"] == "bodega":
        return ["Separar: " + "; ".join(f"{q['tambores'][i]['t']} ({q['tambores'][i]['clase']}) ≠ {q['tambores'][j]['t']} ({q['tambores'][j]['clase']})"
                                        for i, j in pares_incompatibles(q))]
    if q["tipo"] == "fds":
        return [f"Sección {s['n']} · {s['titulo']}: {s['opciones'][c]}" for s, c in zip(q["hoja"]["secciones"], q["correcta"])]
    if q["tipo"] == "sopa":
        return [p["palabra"] for p in q["palabras"]]
    if q["tipo"] == "cruci":
        return [f"{e['n']}{'H' if e['dir'] == 'H' else 'V'}: {e['respuesta']}" for e in q["entradas"]]
    return [q["opciones"][i] for i in q["correcta"]]


def resp_texto(q, sel):
    if sel is None:
        return "(sin respuesta)"
    try:
        if q["tipo"] == "order":
            return " > ".join(q["opciones"][i] for i in sel)
        if q["tipo"] == "match":
            return "; ".join(f"{a} -> {q['derecha'][s] if isinstance(s, int) and 0 <= s < len(q['derecha']) else '(vacío)'}" for a, s in zip(q["izquierda"], sel))
        if q["tipo"] == "fill":
            return "; ".join(f"({i + 1}) {q['banco'][s] if isinstance(s, int) and 0 <= s < len(q['banco']) else '(vacío)'}" for i, s in enumerate(sel))
        if q["tipo"] == "bodega":
            return "; ".join(f"{t['t']} -> {q['jaulas'][s]}" for t, s in zip(q["tambores"], sel))
        if q["tipo"] == "fds":
            return "; ".join(f"S{s['n']}: {s['opciones'][v] if isinstance(v, int) and 0 <= v < len(s['opciones']) else '(vacío)'}" for s, v in zip(q["hoja"]["secciones"], sel))
        if q["tipo"] == "sopa":
            return ", ".join(_linea(q["grid"], *s) or "?" for s in sel) or "(ninguna marcada)"
        if q["tipo"] == "cruci":
            return "; ".join(f"{k}: {v}" for k, v in sel.items() if v) or "(vacío)"
        return "; ".join(q["opciones"][i] for i in sel)
    except Exception:
        return "(sin respuesta)"


# ---------------------------------------------------------------- cálculo del avance
def puntos(r):
    return float(r.get("p", 1.0 if r.get("ok") else 0.0))


def pts_zona(g, tema):
    return sum(puntos(g["resp"][q]) for q in preguntas_zona(g, tema) if q in g["resp"])


def resp_zona(g, tema):
    return sum(1 for q in preguntas_zona(g, tema) if q in g["resp"])


def n_zona(g, tema):
    return len(preguntas_zona(g, tema))


def zona_cerrada(g, tema):
    return resp_zona(g, tema) >= n_zona(g, tema)


def sellos_base(p, total):
    for fr, n in UMBRALES:
        if p >= fr * total - 1e-9:
            return n
    return 0


def regla_sellos(total):
    return [{"min": round(fr * total, 2), "sellos": n} for fr, n in sorted(UMBRALES, key=lambda x: x[1])]


def extras_ok(g, tema):
    return sum(1 for q in ids_extra(g, tema) if g["resp"].get(q, {}).get("ok"))


def sellos_zona(g, tema):
    if not zona_cerrada(g, tema):
        return 0
    return min(SELLOS_POR_ZONA, sellos_base(pts_zona(g, tema), n_zona(g, tema)) + extras_ok(g, tema) + int(g["manual"].get(str(tema), 0)))


def total_sellos(g):
    return sum(sellos_zona(g, t["id"]) for t in TEMAS)


def zonas_completas(g):
    return all(zona_cerrada(g, t["id"]) for t in TEMAS)


def exp_entregado(g):
    return bool((g.get("exp") or {}).get("entregado_en"))


def reto_entregado(g):
    return bool(g.get("reto") and g["reto"].get("entregado_en"))


def reto_frac(g):
    r = g.get("reto")
    if not r or not r.get("entregado_en"):
        return 0.0
    return 0.5 * r["cw_ok"] / max(1, r["cw_total"]) + 0.5 * r["sopa_ok"] / max(1, r["sopa_total"])


def nota_zonas(g):
    return sum(pts_zona(g, t["id"]) / n_zona(g, t["id"]) * PESO_ZONA for t in TEMAS)


def nota_reto(g):
    return PESO_RETO * reto_frac(g)


def nota_docente(g):
    rb = g.get("rubrica") or {}
    if not rb.get("calificado"):
        return None
    return round(min(PESO_DOCENTE, sum(float(rb.get(c["k"], 0) or 0) for c in CRITERIOS)), 2)


def n_salidas(g):
    return len(g["salidas"])


def penalizacion(n):
    return max(0, n - SALIDAS_GRATIS) * DESCUENTO_SALIDA


def salidas_computadas(g):
    return g["salidas_cierre"] if g.get("salidas_cierre") is not None else n_salidas(g)


def notas(g):
    auto = nota_zonas(g) + nota_reto(g)
    doc = nota_docente(g)
    ded = penalizacion(salidas_computadas(g))
    final = max(0.0, min(NOTA_MAX, auto + (doc or 0) - ded))
    return {"zonas": round(nota_zonas(g), 2), "reto": round(nota_reto(g), 2), "auto": round(auto, 2),
            "docente": doc, "deduccion": round(ded, 2), "nota": round(final, 2), "docente_pendiente": doc is None}


def todo_entregado(g):
    return zonas_completas(g) and exp_entregado(g) and reto_entregado(g)


def calificar_reto(g, b, ahora=None):
    cw = RETO["crucigrama"]
    sp = RETO["sopa"]
    dic = b.get("cw") if isinstance(b.get("cw"), dict) else {}
    ok = [f"{e['n']}{e['dir']}" for e in cw["entradas"] if _pal(dic.get(f"{e['n']}{e['dir']}", "")) == e["respuesta"]]
    objetivo = {p["palabra"] for p in sp["palabras"]}
    halladas = set()
    for s in (b.get("sopa") if isinstance(b.get("sopa"), list) else [])[:60]:
        try:
            txt = _linea(sp["grid"], *s)
        except Exception:
            continue
        if txt and txt in objetivo:
            halladas.add(txt)
        elif txt and txt[::-1] in objetivo:
            halladas.add(txt[::-1])
    g["reto"] = {"entregado_en": ahora or time.time(), "cw_ok": len(ok), "cw_total": len(cw["entradas"]), "cw_claves_ok": ok,
                 "sopa_ok": len(halladas), "sopa_total": len(objetivo), "sopa_halladas": sorted(halladas),
                 "cw": {k: _pal(v)[:20] for k, v in list(dic.items())[:20]}}
    return g["reto"]


def _pal(s):
    return "".join(c for c in _sin_tildes(s).upper() if c.isalpha())


def _linea(grid, r1, c1, r2, c2):
    n_ = len(grid)
    if not all(isinstance(x, int) and 0 <= x < n_ for x in (r1, c1, r2, c2)):
        return None
    dr, dc = r2 - r1, c2 - c1
    if not (dr == 0 or dc == 0 or abs(dr) == abs(dc)):
        return None
    n = max(abs(dr), abs(dc))
    sr, sc = (dr > 0) - (dr < 0), (dc > 0) - (dc < 0)
    return "".join(grid[r1 + sr * i][c1 + sc * i] for i in range(n + 1))


def cierre_por_tiempo(g, cfg):
    """Al agotarse el tiempo: el borrador del expediente y del reto final se entregan solos."""
    t = tiempo(cfg)
    if not t["agotado"]:
        return
    fin = cfg["datos"].get("fin_en")
    if not exp_entregado(g):
        g["exp"]["entregado_en"] = fin
        g["exp"]["auto"] = True
    if not reto_entregado(g) and zonas_completas(g):
        calificar_reto(g, g.get("reto_borrador") or {}, fin)
        g["reto"]["auto"] = True
    if g.get("salidas_cierre") is None:
        g["salidas_cierre"] = n_salidas(g)


def asegurar_asignacion(g, cfg):
    n = int(cfg["datos"].get("por_zona") or POR_ZONA_DEF)
    if g.get("asig") is None or ((g.get("por_zona") != n or g.get("asig_v") != BANCO["version"]) and not g["resp"]):
        asignar(g, n)


def revisar_cierre_y_ganador(g, cfg, db):
    asegurar_asignacion(g, cfg)
    ahora = time.time()
    cierre_por_tiempo(g, cfg)
    if g.get("cierre") is None and todo_entregado(g):
        g["cierre"] = ahora
        if g.get("salidas_cierre") is None:
            g["salidas_cierre"] = n_salidas(g)
    if todo_entregado(g) and total_sellos(g) >= TOTAL_SELLOS and reto_frac(g) >= MIN_RETO_GANAR and g.get("completado_en") is None:
        g["completado_en"] = ahora
        if cfg.get("ganador") is None:
            if db.claim_ganador(g["id"]):
                cfg["ganador"] = g["id"]
            else:
                cfg["ganador"] = db.config().get("ganador")


# ---------------------------------------------------------------- vistas de estado
def resumen_temas(g):
    out = []
    for t in TEMAS:
        cerrado = zona_cerrada(g, t["id"])
        out.append({
            "id": t["id"], "nombre": t["nombre"], "zona": t["zona"], "intro": t["intro"],
            "total": n_zona(g, t["id"]), "min": round(sum(PREG[q][0].get("min", 2.5) for q in preguntas_zona(g, t["id"])), 1), "respondidas": resp_zona(g, t["id"]), "puntos": round(pts_zona(g, t["id"]), 2),
            "nota": round(pts_zona(g, t["id"]) / n_zona(g, t["id"]) * PESO_ZONA, 2), "peso": PESO_ZONA,
            "cerrado": cerrado, "sellos": sellos_zona(g, t["id"]), "regla": regla_sellos(n_zona(g, t["id"])),
            "faltan": (SELLOS_POR_ZONA - sellos_zona(g, t["id"])) if cerrado else None,
            "extras_quedan": len([q for q in ids_extra(g, t["id"]) if q not in g["resp"]]),
        })
    return out


def siguiente_de_zona(g, tema):
    for qid in preguntas_zona(g, tema):
        if qid not in g["resp"]:
            return qid
    return None


def siguiente_extra(g, tema):
    for q in ids_extra(g, tema):
        if q not in g["resp"]:
            return q
    return None


def vista_expediente(g, cfg):
    v = variante_exp(g)
    e = g.get("exp") or {}
    rb = g.get("rubrica") or {}
    pub = cfg["datos"].get("publicado") and rb.get("calificado")
    return {"titulo": v["titulo"], "caso": v["caso"], "variante": v["v"], "bodega": EXP["bodega"], "intro": EXP["intro"],
            "criterios": CRITERIOS, "peso": EXP["peso"], "borrador": e.get("borrador") or {}, "entregado": exp_entregado(g),
            "revision": ({c["k"]: rb.get(c["k"]) for c in CRITERIOS} | {"obs": rb.get("obs", ""), "total": nota_docente(g)}) if pub else None}


def vista_reto(g):
    cw = RETO["crucigrama"]
    sp = RETO["sopa"]
    return {
        "peso": PESO_RETO,
        "crucigrama": {"filas": cw["filas"], "cols": cw["cols"], "entradas": [
            {"clave": f"{e['n']}{e['dir']}", "n": e["n"], "dir": e["dir"], "r": e["r"], "c": e["c"],
             "largo": len(e["respuesta"]), "pista": e["pista"], "resp": responsable(g, i)} for i, e in enumerate(cw["entradas"])]},
        "sopa": {"n": sp["n"], "grid": sp["grid"], "palabras": [
            {"i": i, "largo": len(p["palabra"]), "pista": p["pista"], "resp": responsable(g, i + 1)} for i, p in enumerate(sp["palabras"])]},
        "borrador": g.get("reto_borrador") or {},
    }


def tablero(db, actual=None):
    filas = []
    for r in db.resumen():
        if actual and r["id"] == actual["id"]:
            continue
        filas.append({"id": r["id"], "nombre": r["nombre"], "sellos": r.get("sellos") or 0, "completado_en": r.get("completado_en")})
    if actual:
        filas.append({"id": actual["id"], "nombre": actual["nombre"], "sellos": total_sellos(actual), "completado_en": actual.get("completado_en")})
    filas.sort(key=lambda r: (-r["sellos"], r["completado_en"] or 9e18, r["nombre"].lower()))
    return filas


def estado_grupo(g, cfg, db):
    revisar_cierre_y_ganador(g, cfg, db)
    t = tiempo(cfg)
    if not reto_entregado(g):
        fase = "juego"
    else:
        fase = "completo" if total_sellos(g) >= TOTAL_SELLOS else "extras"
    pregs = {}
    if cfg["abierto"] and fase == "juego" and not t["agotado"]:
        for z in TEMAS:
            qid = siguiente_de_zona(g, z["id"])
            if qid:
                pregs[str(z["id"])] = vista_pregunta(g, PREG[qid][0])
    rr = g.get("reto") or {}
    n = salidas_computadas(g)
    tab = tablero(db, g)
    gid = cfg.get("ganador")
    nombre_gan = next((r["nombre"] for r in tab if r["id"] == gid), None) if gid else None
    reto_abierto = zonas_completas(g) and exp_entregado(g) and not reto_entregado(g)
    return {
        "titulo": BANCO["titulo"], "asignatura": BANCO["asignatura"],
        "grupo": {"id": g["id"], "nombre": g["nombre"], "integrantes": g["integrantes"]},
        "miembros": integrantes_lista(g), "turno": responsable(g, len(g["resp"])),
        "abierto": cfg["abierto"], "tiempo": t, "fase": fase, "publicado": bool(cfg["datos"].get("publicado")),
        "temas": resumen_temas(g), "preguntas": pregs,
        "expediente": vista_expediente(g, cfg),
        "reto_abierto": reto_abierto, "vista_reto": vista_reto(g) if reto_abierto and cfg["abierto"] and not t["agotado"] else None,
        "reto": {"peso": PESO_RETO, "entregado": reto_entregado(g), "cw_ok": rr.get("cw_ok", 0), "cw_total": len(RETO["crucigrama"]["entradas"]),
                 "sopa_ok": rr.get("sopa_ok", 0), "sopa_total": len(RETO["sopa"]["palabras"]), "auto": rr.get("auto", False)},
        "min_reto_ganar": MIN_RETO_GANAR, "reto_ok_ganar": reto_frac(g) >= MIN_RETO_GANAR,
        "total_principal": sum(n_zona(g, z["id"]) for z in TEMAS), "respondidas_principal": sum(resp_zona(g, z["id"]) for z in TEMAS),
        "piezas": [[i < sellos_zona(g, z["id"]) for i in range(SELLOS_POR_ZONA)] for z in TEMAS],
        "total_sellos": total_sellos(g), "max_sellos": TOTAL_SELLOS,
        "salidas": n, "salidas_gratis": SALIDAS_GRATIS, "descuento": DESCUENTO_SALIDA, "penalizacion_actual": penalizacion(n),
        "notas": notas(g), "pesos": {"zonas": PESO_ZONAS, "reto": PESO_RETO, "docente": PESO_DOCENTE},
        "informe_disponible": informe_disponible(g, cfg),
        "ganador": nombre_gan, "yo_gano": gid == g["id"], "tablero": tab,
    }


def informe_disponible(g, cfg):
    return reto_entregado(g) or tiempo(cfg)["agotado"] or bool(cfg["datos"].get("publicado"))


def dificiles(grupos, limite=10):
    est = {}
    for g in grupos:
        for qid, r in g["resp"].items():
            if qid in PREG and qid in preguntas_zona(g, PREG[qid][1]):
                s = est.setdefault(qid, [0, 0.0])
                s[0] += 1
                s[1] += puntos(r)
    filas = [{"id": qid, "tema": PREG[qid][1], "extra": PREG[qid][2], "texto": (PREG[qid][0].get("enunciado") or "Relacionar nombres genéricos de residuos con su nombre oficial y código del AM 142 (un lugar distinto por grupo)")[:140],
              "n": n, "aciertos": round(a, 1), "pct": round(100 * a / n)} for qid, (n, a) in est.items()]
    filas.sort(key=lambda r: (r["pct"], -r["n"], r["id"]))
    return filas[:limite]


def sugerencia_exp(g):
    """Comparación automática (solo orientativa) del expediente con la clave, para agilizar la revisión docente."""
    v = variante_exp(g)
    k = v["clave"]
    b = (g.get("exp") or {}).get("borrador") or {}
    pics = set(b.get("c3") or [])
    s = {
        "c1": _norm(k["c1"].split("·")[0]) in _norm(b.get("c1", "")),
        "c2": str(b.get("c2", "")).strip() == k.get("c2_cod"),
        "c3": set(k["c3_min"]).issubset(pics) and pics.issubset(set(k["c3"])),
        "c4": any(x.strip() == str(b.get("c4", "")).strip() for x in k["c4"].replace("o", ",").split(",")),
    }
    return {"clave": k, "auto": s, "variante": v["v"], "titulo": v["titulo"], "caso": v["caso"]}


def panel(cfg, grupos):
    filas = []
    ahora = time.time()
    db = get_db()
    for g in grupos.values():
        revisar_cierre_y_ganador(g, cfg, db)
        n = salidas_computadas(g)
        fuera = bool(g["salidas"]) and g["salidas"][-1].get("fin") is None
        filas.append({
            "id": g["id"], "nombre": g["nombre"], "pin": g["pin"], "integrantes": g["integrantes"], "orden": g.get("orden", 0),
            "en_linea": ahora - g.get("ultimo_latido", 0) < 25, "fuera_ahora": fuera and ahora - g.get("ultimo_latido", 0) < 40,
            "salidas": n, "penalizacion": penalizacion(n),
            "respondidas": sum(resp_zona(g, t["id"]) for t in TEMAS), "total": sum(n_zona(g, t["id"]) for t in TEMAS),
            "notas": notas(g), "cerrado": g.get("cierre") is not None,
            "reto": {"entregado": reto_entregado(g), "cw_ok": (g.get("reto") or {}).get("cw_ok", 0), "cw_total": len(RETO["crucigrama"]["entradas"]),
                     "sopa_ok": (g.get("reto") or {}).get("sopa_ok", 0), "sopa_total": len(RETO["sopa"]["palabras"]), "auto": (g.get("reto") or {}).get("auto", False)},
            "exp": {"entregado": exp_entregado(g), "auto": (g.get("exp") or {}).get("auto", False), "borrador": (g.get("exp") or {}).get("borrador") or {}},
            "sugerencia": sugerencia_exp(g), "rubrica": g.get("rubrica") or {},
            "sellos": total_sellos(g), "temas": resumen_temas(g), "variante_pool": variante_pool(g) + 1,
            "extras_resp": sum(1 for q in g["resp"] if q in PREG and q not in preguntas_zona(g, PREG[q][1])),
            "completado_en": g.get("completado_en"),
            "salidas_detalle": [{"ini": s["ini"], "fin": s["fin"]} for s in g["salidas"]],
        })
    filas.sort(key=lambda r: (-r["sellos"], r["completado_en"] or 9e18, r["nombre"].lower()))
    gan = grupos.get(cfg.get("ganador") or "")
    return {"abierto": cfg["abierto"], "tiempo": tiempo(cfg), "datos": cfg["datos"], "max_sellos": TOTAL_SELLOS,
            "ganador": gan["nombre"] if gan else None, "grupos": filas, "ahora": ahora, "preguntas": dificiles(grupos.values()),
            "criterios": CRITERIOS, "pesos": {"zonas": PESO_ZONAS, "reto": PESO_RETO, "docente": PESO_DOCENTE},
            "reglas": {"gratis": SALIDAS_GRATIS, "descuento": DESCUENTO_SALIDA}, "version": BANCO["version"],
            "modo": "supabase" if isinstance(db, Supabase) else "local"}


# ---------------------------------------------------------------- PDF (generador mínimo, sin dependencias)
_LOGO = None


def _logo():
    global _LOGO
    if _LOGO is None:
        try:
            with open(os.path.join(HERE, "logo.jpg"), "rb") as f:
                data = f.read()
            i = 2
            w = h = 0
            while i < len(data):
                if data[i] != 0xFF:
                    i += 1
                    continue
                m = data[i + 1]
                if m in (0xC0, 0xC1, 0xC2):
                    h = int.from_bytes(data[i + 5:i + 7], "big")
                    w = int.from_bytes(data[i + 7:i + 9], "big")
                    break
                i += 2 + int.from_bytes(data[i + 2:i + 4], "big")
            _LOGO = (data, w, h) if w and h else False
        except Exception:
            _LOGO = False
    return _LOGO


def _t(s):
    s = str(s)
    for a, b in (("→", "->"), ("—", "-"), ("–", "-"), ("−", "-"), ("“", '"'), ("”", '"'), ("’", "'"), ("‘", "'"), ("✓", "OK"),
                 ("✗", "X"), ("•", "-"), ("≠", "<>"), ("₂", "2"), ("…", "..."), ("≤", "<="), ("≥", ">="), ("·", "-")):
        s = s.replace(a, b)
    return s.encode("cp1252", "replace")


def _esc(b):
    return b.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def pdf_bytes(lineas, pie, titulo):
    """lineas: (texto, estilo) con estilo n normal, b negrita, h título, s subtítulo, m monoespaciado, r regla."""
    ALTO, MARGEN = 842, 56
    paginas, y = [[]], 742
    for texto, est in lineas:
        size = {"h": 15, "s": 11.5, "m": 8.6}.get(est, 9.6)
        lh = size * 1.42 if est != "r" else 8
        if y - lh < MARGEN:
            paginas.append([])
            y = 790
        y -= lh
        paginas[-1].append((y, texto, est, size))
    logo = _logo()
    objs = {1: b"<< /Type /Catalog /Pages 2 0 R >>",
            3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
            4: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
            5: b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier /Encoding /WinAnsiEncoding >>"}
    if logo:
        data, w, h = logo
        objs[6] = (f"<< /Type /XObject /Subtype /Image /Width {w} /Height {h} /ColorSpace /DeviceRGB /BitsPerComponent 8 "
                   f"/Filter /DCTDecode /Length {len(data)} >>\nstream\n").encode() + data + b"\nendstream"
    kids = []
    for i, pg in enumerate(paginas):
        po, co = 10 + 2 * i, 11 + 2 * i
        kids.append(f"{po} 0 R")
        partes = []
        if i == 0:
            partes.append(b"0.11 0.33 0.20 rg 40 772 515 3 re f 0 0 0 rg")
            if logo:
                _, w, h = logo
                ah = 46
                aw = ah * w / h
                partes.append(f"q {aw:.1f} 0 0 {ah} {555 - aw:.1f} 780 cm /Im1 Do Q".encode())
            partes.append(b"BT /F2 13 Tf 40 806 Td (" + _esc(_t("Universidad Técnica Estatal de Quevedo")) + b") Tj ET")
            partes.append(b"BT /F1 9 Tf 40 792 Td (" + _esc(_t(BANCO["carrera"])) + b") Tj ET")
            partes.append(b"BT /F1 9 Tf 40 780 Td (" + _esc(_t(BANCO["asignatura"] + " - " + BANCO["semana"])) + b") Tj ET")
        for yy, texto, est, size in pg:
            if est == "r":
                partes.append(f"0.7 g 40 {yy + 3:.1f} 515 0.6 re f 0 g".encode())
                continue
            fuente = {"b": "F2", "h": "F2", "s": "F2", "m": "F3"}.get(est, "F1")
            color = b"0.11 0.33 0.20 rg " if est in ("h", "s") else b""
            partes.append(b"BT " + color + b"/" + fuente.encode() + f" {size} Tf 40 {yy:.1f} Td (".encode() + _esc(_t(texto)) + b") Tj ET 0 g")
        partes.append(b"BT /F1 7.5 Tf 40 30 Td (" + _esc(_t(f"{pie}  -  {BANCO['version']}  -  página {i + 1} de {len(paginas)}")) + b") Tj ET")
        stream = b"\n".join(partes)
        objs[co] = b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"
        res = "/Font << /F1 3 0 R /F2 4 0 R /F3 5 0 R >>" + (" /XObject << /Im1 6 0 R >>" if logo else "")
        objs[po] = f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 {ALTO}] /Contents {co} 0 R /Resources << {res} >> >>".encode()
    objs[2] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>".encode()
    objs[7] = b"<< /Title (" + _esc(_t(titulo)) + b") /Producer (Bodega Peligrosa) >>"
    out, offs = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"), {}
    nums = sorted(objs)
    for n in nums:
        offs[n] = len(out)
        out += f"{n} 0 obj\n".encode() + objs[n] + b"\nendobj\n"
    xref = len(out)
    mx = max(nums)
    out += f"xref\n0 {mx + 1}\n0000000000 65535 f \n".encode()
    for n in range(1, mx + 1):
        out += (f"{offs[n]:010d} 00000 n \n" if n in offs else "0000000000 65535 f \n").encode()
    out += f"trailer\n<< /Size {mx + 1} /Root 1 0 R /Info 7 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(out)


def _env(texto, ancho=100, sangria=""):
    return [sangria + l for l in textwrap.wrap(str(texto), ancho - len(sangria))] or [sangria]


def _hora(t):
    return time.strftime("%H:%M:%S", time.localtime(t)) if t else "-"


def _f2(x):
    return f"{x:.2f}".replace(".", ",")


def _limpio(s):
    """Quita las marcas de imagen {{pic:..}} {{rot:..}} para el PDF."""
    import re
    nombres = {"GHS01": "bomba explotando", "GHS02": "llama", "GHS03": "llama sobre círculo", "GHS04": "botella de gas",
               "GHS05": "corrosión", "GHS06": "calavera y tibias", "GHS07": "signo de exclamación", "GHS08": "peligro para la salud",
               "GHS09": "medio ambiente"}
    s = re.sub(r"\{\{pic:(\w+)\}\}", lambda m: f"[pictograma {nombres.get(m.group(1), m.group(1))}]", str(s))
    s = re.sub(r"\{\{rot:([\d.]+)\}\}", lambda m: f"[rótulo clase {m.group(1)}]", s)
    return re.sub(r"\{\{nfpa:([0-4])-([0-4])-([0-4])-?([A-Z]*)\}\}", lambda m: f"[rombo NFPA 704: salud {m.group(1)}, inflamabilidad {m.group(2)}, inestabilidad {m.group(3)}{', especial ' + m.group(4) if m.group(4) else ''}]", s)


def bloque_resultado(g, cfg, L, docente=False):
    nt = notas(g)
    pub = bool(cfg["datos"].get("publicado"))
    n = salidas_computadas(g)
    final = pub and not nt["docente_pendiente"]
    L += [("RESULTADO" + (" FINAL" if final else " PROVISIONAL"), "s"), ("", "r")]
    L.append((f"Zonas 1 a 4 (automático, {PESO_ZONAS:.0f} pts) ............ {_f2(nt['zonas'])}", "m"))
    for t in TEMAS:
        L.append((f"   Zona {t['id']} - {t['zona']:<26} {pts_zona(g, t['id']):.2f}/{n_zona(g, t['id'])} ítems -> {_f2(pts_zona(g, t['id']) / n_zona(g, t['id']) * PESO_ZONA)} / {_f2(PESO_ZONA)}", "m"))
    r = g.get("reto") or {}
    L.append((f"Reto final (crucigrama + sopa, {PESO_RETO:.0f} pt) ........ {_f2(nt['reto'])}" +
              (f"   [crucigrama {r.get('cw_ok', 0)}/{r.get('cw_total', 0)}, sopa {r.get('sopa_ok', 0)}/{r.get('sopa_total', 0)}]" if reto_entregado(g) else "   [sin entregar]"), "m"))
    doc_vis = nt["docente"] if (pub or docente) and nt["docente"] is not None else None
    L.append((f"Expediente de contención (docente, {PESO_DOCENTE:.0f} pts) ... " + (_f2(doc_vis) if doc_vis is not None else "pendiente de revisión"), "m"))
    L.append((f"Salidas de pantalla: {n} (2 sin descuento) ......... -{_f2(nt['deduccion'])}", "m"))
    total = nt["auto"] + (doc_vis or 0) - nt["deduccion"]
    L.append(("", "n"))
    L.append((f"NOTA DEL GRUPO: {_f2(max(0, min(10, total)))} / 10" + ("" if doc_vis is not None else "   (sin la parte docente)"), "h"))
    L.append((f"Sellos de contención: {total_sellos(g)} de {TOTAL_SELLOS}" + (f" - completó a las {_hora(g['completado_en'])}" if g.get("completado_en") else ""), "n"))
    if cfg.get("ganador") == g["id"]:
        L.append(("GRUPO GANADOR: primero en contener la bodega (+1 punto directo).", "b"))
    L.append(("", "n"))


def informe_grupo(g, cfg, docente=False):
    revisar_cierre_y_ganador(g, cfg, get_db())
    L = [("INFORME DEL GRUPO - " + BANCO["titulo"].upper(), "h"), ("", "n")]
    L += [(f"Grupo: {g['nombre']}", "b")] + [(l, "n") for l in _env("Integrantes: " + (g["integrantes"] or "-"))]
    L += [(f"Fecha del informe: {time.strftime('%d/%m/%Y %H:%M')}", "n"), ("", "n")]
    bloque_resultado(g, cfg, L, docente)
    pub = bool(cfg["datos"].get("publicado"))
    rb = g.get("rubrica") or {}
    v = variante_exp(g)
    L += [("EXPEDIENTE DE CONTENCIÓN", "s"), ("", "r")]
    L += [(l, "n") for l in _env(f"Caso {v['v']} - {v['titulo']}: {v['caso']}")]
    if (pub or docente) and rb.get("calificado"):
        for c in CRITERIOS:
            L.append((f"   {c['nombre']:<48} {_f2(float(rb.get(c['k'], 0) or 0))} / {_f2(c['max'])}", "m"))
        if rb.get("obs"):
            L += [(l, "n") for l in _env("Observación del docente: " + rb["obs"], sangria="   ")]
    else:
        L.append(("   La revisión docente se mostrará cuando el profesor publique los resultados.", "n"))
    if docente or pub:
        b = (g.get("exp") or {}).get("borrador") or {}
        L.append(("   Respuesta del grupo:", "b"))
        for k, et in (("c1", "AM 142"), ("c2", "Clase INEN"), ("c3", "Pictogramas"), ("c4", "Sección FDS"), ("c5j", "Jaula"), ("c5", "Justificación")):
            val = b.get(k)
            if isinstance(val, list):
                val = ", ".join(val)
            L += [(l, "n") for l in _env(f"{et}: {val or '-'}", sangria="     ")]
    L.append(("", "n"))
    if pub or docente:
        L += [("DETALLE DE LAS ZONAS", "s"), ("", "r"), ("OK = correcta · PARCIAL = algunas partes bien · X = incorrecta", "n"), ("", "n")]
        for t in TEMAS:
            L += [(f"Zona {t['id']}: {t['zona']}", "b")]
            for i, q0 in enumerate([PREG[x][0] for x in preguntas_zona(g, t["id"])], 1):
                q = item_de(g, q0)
                r = g["resp"].get(q["id"])
                p = puntos(r) if r else 0.0
                marca = "OK" if p >= 0.999 else (f"PARCIAL {p:.2f}" if p > 0 else ("X" if r else "SIN RESPONDER"))
                L += [(l, "n") for l in _env(f"{i}. [{marca}] {_limpio(q['enunciado'])}")]
                if r and p < 0.999:
                    L += [(l, "n") for l in _env("Respondieron: " + _limpio(resp_texto(q, r['sel'])), sangria="     ")]
                if p < 0.999:
                    L += [(l, "b") for l in _env("Correcta: " + _limpio("; ".join(texto_correcto(q))), sangria="     ")]
                L += [(l, "n") for l in _env("Por qué: " + q["explicacion"], sangria="     ")]
                L.append(("", "n"))
    else:
        L += [("El detalle de cada pregunta con su explicación se incluirá cuando el docente publique los resultados.", "n")]
    L += [("", "n"), ("Documento generado automáticamente por Bodega Peligrosa.", "n")]
    return pdf_bytes(L, f"Informe del grupo {g['nombre']}", f"Informe {g['nombre']}")


def informe_docente(cfg, grupos):
    p = panel(cfg, grupos)
    L = [("INFORME DEL DOCENTE - " + BANCO["titulo"].upper(), "h"), ("", "n"),
         (f"Generado: {time.strftime('%d/%m/%Y %H:%M')} - Grupos: {len(p['grupos'])} - Resultados {'publicados' if cfg['datos'].get('publicado') else 'sin publicar'}", "n"),
         ((f"GANADOR: {p['ganador']} (+1 punto directo)" if p["ganador"] else "Ganador: aún no hay"), "b"),
         ("", "n")]
    L += [(l, "n") for l in _env(f"Nota sobre 10 = zonas 1-4 ({PESO_ZONAS:.0f} pts, automático) + reto final ({PESO_RETO:.0f} pt, automático) + expediente ({PESO_DOCENTE:.0f} pts, rúbrica docente) - 0,50 por cada salida desde la 3.ª.")]
    L += [("", "n"), ("RESUMEN", "s"), ("", "r"),
          ("Grupo               Zonas  Reto  Exped.  Salid. Desc.  NOTA   Sellos  Completo", "m")]
    for r in p["grupos"]:
        nt = r["notas"]
        L.append((f"{r['nombre'][:19]:<19} {_f2(nt['zonas']):>5} {_f2(nt['reto']):>5} {(_f2(nt['docente']) if nt['docente'] is not None else 'pend.'):>6} "
                  f"{r['salidas']:>6} {_f2(nt['deduccion']):>5} {_f2(nt['nota']):>6} {r['sellos']:>3}/{TOTAL_SELLOS:<3} {_hora(r['completado_en'])}", "m"))
    if p.get("preguntas"):
        L += [("", "n"), ("PREGUNTAS CON MÁS FALLOS (para repasar)", "s"), ("", "r")]
        for q in p["preguntas"]:
            L += [(l, "n") for l in _env(f"{q['id']} - {q['aciertos']}/{q['n']} grupos ({q['pct']} %): {_limpio(q['texto'])}", sangria="  ")]
    L += [("", "n"), ("DETALLE POR GRUPO", "s"), ("", "r")]
    for r in p["grupos"]:
        g = grupos[r["id"]]
        L += [(f"{r['nombre']}" + ("   [GANADOR]" if p["ganador"] == r["nombre"] else ""), "b")]
        L += [(l, "n") for l in _env("Integrantes: " + (r["integrantes"] or "-"), sangria="  ")]
        L += [(f"  Zona {t['id']}: {t['puntos']:.2f}/{t['total']} ítems, {t['sellos']} sellos" + ("" if t["cerrado"] else " (sin terminar)"), "n") for t in r["temas"]]
        L.append(("  Reto final: " + (f"crucigrama {r['reto']['cw_ok']}/{r['reto']['cw_total']}, sopa {r['reto']['sopa_ok']}/{r['reto']['sopa_total']}" if r["reto"]["entregado"] else "sin entregar"), "n"))
        su = r["sugerencia"]
        L.append((f"  Expediente: caso {su['variante']} ({su['titulo']}) - " + ("entregado" if r["exp"]["entregado"] else "sin entregar") +
                  (f" - rúbrica {_f2(r['notas']['docente'])}/2" if r["notas"]["docente"] is not None else " - rúbrica pendiente"), "n"))
        rb = r["rubrica"]
        if rb.get("obs"):
            L += [(l, "n") for l in _env("Observación: " + rb["obs"], sangria="    ")]
        if r["salidas_detalle"]:
            for k, s in enumerate(r["salidas_detalle"], 1):
                d = f"{int(round((s['fin'] or p['ahora']) - s['ini']))} s" + ("" if s["fin"] else " (sigue fuera)")
                L.append((f"  Salida {k}: {_hora(s['ini'])} - duración {d}", "n"))
        else:
            L.append(("  Sin salidas registradas.", "n"))
        L.append((f"  NOTA: {_f2(r['notas']['nota'])}/10" + (" (falta la rúbrica)" if r["notas"]["docente_pendiente"] else ""), "b"))
        L.append(("", "n"))
    return pdf_bytes(L, "Informe del docente - Bodega Peligrosa", "Informe docente Bodega Peligrosa")


# ---------------------------------------------------------------- HTTP
class handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _pdf(self, data, nombre):
        self.send_response(200)
        self.send_header("Content-Type", "application/pdf")
        self.send_header("Content-Disposition", f'attachment; filename="{nombre}"')
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > 100_000:
            return {}
        try:
            b = json.loads(self.rfile.read(n) or b"{}")
            return b if isinstance(b, dict) else {}
        except Exception:
            return {}

    def _grupo(self):
        auth = self.headers.get("Authorization", "")
        gid = verificar(auth[7:]) if auth.startswith("Bearer ") else None
        return get_db().grupo(gid) if gid else None

    def _docente(self):
        c = env("DOCENTE_CLAVE") or os.environ.get("BT_CLAVE_LOCAL", "")
        return bool(c) and secrets.compare_digest(self.headers.get("X-Docente-Clave", "").encode(), c.encode())

    def _ruta(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        if "ruta" in q:
            return "/api/" + q["ruta"][0].strip("/"), q
        return u.path.rstrip("/"), q

    def do_GET(self):
        self._despachar("GET")

    def do_POST(self):
        self._despachar("POST")

    def _despachar(self, metodo):
        try:
            ruta, q = self._ruta()
            if isinstance(get_db(), Local) is False and (not env("SESSION_SECRET") or not env("DOCENTE_CLAVE")):
                return self._json({"error": "Servidor sin configurar (faltan variables de entorno)"}, 503)
            body = self._body() if metodo == "POST" else None
            with LOCK:
                cfg = get_db().config()
                if metodo == "GET":
                    return self._get(ruta, q, cfg)
                return self._post(ruta, body, cfg)
        except ErrorBD:
            return self._json({"error": "Error temporal de base de datos. Intenten de nuevo."}, 503)
        except Exception:
            traceback.print_exc(file=sys.stderr)
            return self._json({"error": "Error interno"}, 500)

    # ------------------------------------------------------------ GET
    def _get(self, ruta, q, cfg):
        db = get_db()
        if ruta == "/api/grupos-publicos":
            gs = sorted(db.grupos().values(), key=lambda g: (g.get("orden", 0), g["nombre"]))
            return self._json([{"id": g["id"], "nombre": g["nombre"]} for g in gs])
        if ruta == "/api/acertijo":
            g = db.grupo(q.get("id", [""])[0])
            if not g:
                return self._json({"error": "grupo"}, 404)
            return self._json({"nombre": g["nombre"], **acertijo(g)})
        if ruta == "/api/estado":
            g = self._grupo()
            if not g:
                return self._json({"error": "sesion"}, 401)
            ahora = time.time()
            cambio = ahora - g.get("ultimo_latido", 0) > 8
            if cambio:
                g["ultimo_latido"] = ahora
            antes = json.dumps(g, sort_keys=True)
            gan_antes = cfg.get("ganador")
            r = estado_grupo(g, cfg, db)
            if cambio or json.dumps(g, sort_keys=True) != antes:
                db.guardar_grupo(g)
            return self._json(r)
        if ruta == "/api/pregunta-extra":
            g = self._grupo()
            if not g:
                return self._json({"error": "sesion"}, 401)
            try:
                tema = int(q.get("tema", ["0"])[0])
            except ValueError:
                tema = 0
            if not puede_jugar(cfg) or not reto_entregado(g) or total_sellos(g) >= TOTAL_SELLOS:
                return self._json({"error": "no_disponible"}, 403)
            if tema not in TEMA or not zona_cerrada(g, tema) or sellos_zona(g, tema) >= SELLOS_POR_ZONA:
                return self._json({"pregunta": None})
            qid = siguiente_extra(g, tema)
            return self._json({"pregunta": vista_pregunta(g, PREG[qid][0]) if qid else None})
        if ruta == "/api/informe-pdf":
            g = self._grupo()
            if not g:
                return self._json({"error": "sesion"}, 401)
            cierre_por_tiempo(g, cfg)
            if not informe_disponible(g, cfg):
                return self._json({"error": "El informe se habilita al entregar el reto final o al terminar el tiempo."}, 403)
            return self._pdf(informe_grupo(g, cfg), "informe_" + "".join(c if c.isalnum() else "_" for c in g["nombre"]) + ".pdf")
        if ruta == "/api/docente/panel":
            if not self._docente():
                return self._json({"error": "clave"}, 401)
            gs = db.grupos()
            p = panel(cfg, gs)
            return self._json(p)
        if ruta == "/api/docente/informe-pdf":
            if not self._docente():
                return self._json({"error": "clave"}, 401)
            return self._pdf(informe_docente(cfg, db.grupos()), "informe_docente_bodega_peligrosa.pdf")
        if ruta == "/api/docente/informe-grupo-pdf":
            if not self._docente():
                return self._json({"error": "clave"}, 401)
            g = db.grupo(q.get("gid", [""])[0])
            if not g:
                return self._json({"error": "grupo"}, 404)
            return self._pdf(informe_grupo(g, cfg, docente=True), "informe_docente_" + "".join(c if c.isalnum() else "_" for c in g["nombre"]) + ".pdf")
        return self._json({"error": "ruta"}, 404)

    # ------------------------------------------------------------ POST
    def _post(self, ruta, b, cfg):
        db = get_db()
        if ruta == "/api/login":
            g = db.grupo(str(b.get("id", "")))
            if not g:
                return self._json({"error": "Grupo no encontrado"}, 401)
            antes = g.get("fallos", 0)
            codigo = intentar_ingreso(g, b)
            if codigo != "bloqueado" and (codigo == "mal" or antes):
                db.guardar_grupo(g)
            if codigo == "bloqueado":
                return self._json({"error": "Demasiados intentos. Esperen un minuto."}, 429)
            if codigo != "ok":
                return self._json({"error": "Esos nombres no abren la bodega. Descifren mejor las letras."}, 401)
            return self._json({"token": firmar(g["id"])})
        if ruta.startswith("/api/docente/"):
            if not self._docente():
                return self._json({"error": "clave"}, 401)
            return self._docente_post(ruta, b, cfg)
        g = self._grupo()
        if not g:
            return self._json({"error": "sesion"}, 401)
        if ruta == "/api/salida":
            return self._salida(g, b, cfg)
        if not cfg["abierto"]:
            return self._json({"error": "La bodega está cerrada: esperen al docente."}, 403)
        if tiempo(cfg)["agotado"]:
            return self._json({"error": "tiempo", "estado": estado_grupo(g, cfg, db)}, 409)
        if ruta == "/api/responder":
            return self._responder(g, b, cfg)
        if ruta == "/api/expediente":
            return self._expediente(g, b, cfg)
        if ruta == "/api/reto":
            return self._reto(g, b, cfg)
        return self._json({"error": "ruta"}, 404)

    def _responder(self, g, b, cfg):
        db = get_db()
        qid = b.get("qid")
        if qid not in PREG:
            return self._json({"error": "pregunta"}, 400)
        q0, tema, _ = PREG[qid]
        es_extra = qid not in preguntas_zona(g, tema)
        q = item_de(g, q0)
        if qid not in g["resp"]:
            if es_extra:
                if not reto_entregado(g) or sellos_zona(g, tema) >= SELLOS_POR_ZONA:
                    return self._json({"error": "no_disponible"}, 403)
            elif siguiente_de_zona(g, tema) != qid:
                return self._json({"error": "fuera_de_orden"}, 409)
            p = corregir(q, b.get("sel"))
            g["resp"][qid] = {"sel": b.get("sel"), "ok": p >= 0.999, "p": round(p, 4), "t": time.time(), "turno": responsable(g, len(g["resp"]))}
            revisar_cierre_y_ganador(g, cfg, db)
            db.guardar_grupo(g)
        r = g["resp"][qid]
        p = puntos(r)
        return self._json({"ok": p >= 0.999, "puntos": p, "parcial": 0 < p < 0.999, "correcta": texto_correcto(q),
                           "explicacion": q["explicacion"], "tipo": q["tipo"], "tema": tema, "estado": estado_grupo(g, cfg, db)})

    def _expediente(self, g, b, cfg):
        db = get_db()
        if exp_entregado(g):
            return self._json({"error": "El expediente ya fue entregado."}, 409)
        c = b.get("campos") if isinstance(b.get("campos"), dict) else {}
        limpio = {}
        for k in ("c1", "c2", "c4", "c5j"):
            limpio[k] = str(c.get(k, ""))[:300]
        limpio["c5"] = str(c.get("c5", ""))[:2500]
        limpio["c3"] = [x for x in (c.get("c3") or []) if isinstance(x, str) and x.startswith("GHS")][:9]
        g["exp"]["borrador"] = limpio
        g["exp"]["guardado_en"] = time.time()
        if b.get("entregar"):
            g["exp"]["entregado_en"] = time.time()
        revisar_cierre_y_ganador(g, cfg, db)
        db.guardar_grupo(g)
        return self._json({"ok": True, "estado": estado_grupo(g, cfg, db) if b.get("entregar") else None})

    def _reto(self, g, b, cfg):
        db = get_db()
        if not (zonas_completas(g) and exp_entregado(g)):
            return self._json({"error": "Primero terminen las 4 zonas y entreguen el expediente."}, 403)
        if reto_entregado(g):
            return self._json({"estado": estado_grupo(g, cfg, db)})
        cw = b.get("cw") if isinstance(b.get("cw"), dict) else {}
        sp = b.get("sopa") if isinstance(b.get("sopa"), list) else []
        g["reto_borrador"] = {"cw": {str(k)[:6]: str(v)[:20] for k, v in list(cw.items())[:30]}, "sopa": sp[:40],
                              "letras": b.get("letras") if isinstance(b.get("letras"), dict) and len(json.dumps(b.get("letras"))) < 4000 else {}}
        if b.get("entregar"):
            calificar_reto(g, g["reto_borrador"])
            revisar_cierre_y_ganador(g, cfg, db)
        db.guardar_grupo(g)
        return self._json({"ok": True, "estado": estado_grupo(g, cfg, db) if b.get("entregar") else None})

    def _salida(self, g, b, cfg):
        ahora = time.time()
        cerrado = g.get("salidas_cierre") is not None or not cfg["abierto"] or tiempo(cfg)["agotado"]
        if b.get("tipo") == "salida" and not cerrado:
            if not g["salidas"] or g["salidas"][-1].get("fin") is not None:
                g["salidas"].append({"ini": ahora, "fin": None})
        elif b.get("tipo") == "regreso":
            if g["salidas"] and g["salidas"][-1].get("fin") is None:
                g["salidas"][-1]["fin"] = ahora
        g["ultimo_latido"] = ahora
        get_db().guardar_grupo(g)
        n = salidas_computadas(g)
        return self._json({"salidas": n, "penalizacion": penalizacion(n), "contada": b.get("tipo") == "salida" and not cerrado})

    def _docente_post(self, ruta, b, cfg):
        db = get_db()
        d = cfg["datos"]
        ahora = time.time()
        if ruta == "/api/docente/abrir":
            abierto = bool(b.get("abierto"))
            if abierto and not cfg["abierto"]:
                if not d.get("fin_en"):
                    d["iniciado_en"] = ahora
                    d["fin_en"] = ahora + int(d.get("duracion_min") or DURACION_DEF) * 60
                elif d.get("pausado_en"):
                    d["fin_en"] += ahora - d["pausado_en"]
                d["pausado_en"] = None
            elif not abierto and cfg["abierto"] and d.get("fin_en") and not d.get("pausado_en"):
                d["pausado_en"] = ahora
            cfg["abierto"] = abierto
            db.set_config(cfg)
        elif ruta == "/api/docente/tiempo":
            try:
                m = max(-60, min(120, int(b.get("min", 5))))
            except Exception:
                m = 5
            if d.get("fin_en"):
                base = max(d["fin_en"], d.get("pausado_en") or ahora) if m > 0 else d["fin_en"]
                d["fin_en"] = base + m * 60
            else:
                d["duracion_min"] = max(10, int(d.get("duracion_min") or DURACION_DEF) + m)
            db.set_config(cfg)
        elif ruta == "/api/docente/duracion":
            if not d.get("fin_en"):
                try:
                    d["duracion_min"] = max(10, min(240, int(b.get("min"))))
                except Exception:
                    pass
                db.set_config(cfg)
        elif ruta == "/api/docente/porzona":
            # solo antes de iniciar: cambia cuántas preguntas del banco responde cada grupo y la duración sugerida
            if not d.get("fin_en"):
                try:
                    n = max(4, min(10, int(b.get("n"))))
                except Exception:
                    n = POR_ZONA_DEF
                d["por_zona"] = n
                d["duracion_min"] = TIEMPOS_POR_ZONA.get(n, 85 + (n - 5) * 10)
                db.set_config(cfg)
                for g in db.grupos().values():
                    if not g["resp"]:
                        asignar(g, n)
                        db.guardar_grupo(g)
        elif ruta == "/api/docente/publicar":
            d["publicado"] = bool(b.get("publicado"))
            db.set_config(cfg)
        elif ruta == "/api/docente/grupos-lote":
            existentes = db.grupos()
            orden = max([x.get("orden", -1) for x in existentes.values()] + [-1]) + 1
            nombres = {x["nombre"].lower() for x in existentes.values()}
            for linea in (b.get("texto") or "").splitlines():
                partes = [p.strip() for p in linea.split(";")]
                if not partes or not partes[0] or partes[0].startswith("#") or partes[0].lower() in nombres:
                    continue        # se ignoran líneas vacías, comentarios (#) y nombres repetidos
                pin = partes[1] if len(partes) > 1 and partes[1] else "".join(secrets.choice("0123456789") for _ in range(4))
                db.guardar_grupo(nuevo_grupo(partes[0], pin, partes[2] if len(partes) > 2 else "", orden))
                nombres.add(partes[0].lower())
                orden += 1
        elif ruta == "/api/docente/rubrica":
            g = db.grupo(str(b.get("gid", "")))
            if g:
                rb = {}
                for c in CRITERIOS:
                    try:
                        v = float(str(b.get(c["k"], 0)).replace(",", "."))
                    except Exception:
                        v = 0.0
                    rb[c["k"]] = round(max(0.0, min(c["max"], v)), 2)
                rb["obs"] = str(b.get("obs", ""))[:800]
                rb["calificado"] = True
                rb["en"] = ahora
                g["rubrica"] = rb
                db.guardar_grupo(g)
        elif ruta == "/api/docente/ficha":
            g = db.grupo(str(b.get("gid", "")))
            tema = str(b.get("tema"))
            if g and tema.isdigit() and int(tema) in TEMA and zona_cerrada(g, int(tema)) and sellos_zona(g, int(tema)) < SELLOS_POR_ZONA:
                g["manual"][tema] = int(g["manual"].get(tema, 0)) + 1
                revisar_cierre_y_ganador(g, cfg, db)
                db.guardar_grupo(g)
        elif ruta == "/api/docente/salida-ajuste":
            g = db.grupo(str(b.get("gid", "")))
            if g and g["salidas"]:
                g["salidas"].pop()
                if g.get("salidas_cierre") is not None:
                    g["salidas_cierre"] = max(0, g["salidas_cierre"] - 1)
                g.setdefault("ajustes", []).append({"en": ahora, "motivo": str(b.get("motivo", ""))[:200]})
                db.guardar_grupo(g)
        elif ruta == "/api/docente/reiniciar":
            g = db.grupo(str(b.get("gid", "")))
            if g:
                n = nuevo_grupo(g["nombre"], g["pin"], g["integrantes"], g.get("orden", 0))
                n["id"] = g["id"]
                db.guardar_grupo(n)
                if cfg.get("ganador") == g["id"]:
                    cfg["ganador"] = None
                    db.set_config(cfg)
        elif ruta == "/api/docente/eliminar":
            gid = str(b.get("gid", ""))
            db.eliminar(gid)
            if cfg.get("ganador") == gid:
                cfg["ganador"] = None
                db.set_config(cfg)
        elif ruta == "/api/docente/reiniciar-todo":
            if b.get("confirmar") == "BORRAR":
                db.borrar_todo()
        else:
            return self._json({"error": "ruta"}, 404)
        cfg = db.config()
        return self._json(panel(cfg, db.grupos()))
