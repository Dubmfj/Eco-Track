import discord
import os
import random
import aiohttp
import json
import asyncio
import html
import datetime
import time
import aiosqlite
from discord.ext import commands, tasks
from dotenv import load_dotenv
from deep_translator import GoogleTranslator

# ============================================================
# 1. CARGAR CONFIGURACIÓN
# ============================================================
load_dotenv()
TOKEN           = os.getenv('DISCORD_TOKEN')
WEATHER_KEY     = os.getenv('WEATHER_API_KEY')
GROQ_API_KEY     = os.getenv('GROQ_API_KEY')
CANAL_EVENTOS_ID = int(os.getenv('CANAL_EVENTOS_ID', '0'))
DB_PATH         = "usuarios.db"

TOKEN_TRIVIA = ""

# --- CONFIGURACIÓN DE LA TIENDA ---
TIENDA_ITEMS = {
    "1": {"nombre": "🌱 Eco-Aprendiz",      "precio":  1000,  "rol_id": 1480749815016194119},
    "2": {"nombre": "💻 Junior Dev",         "precio":  5000,  "rol_id": 1480750401715437649},
    "3": {"nombre": "⚡ Senior Architect",   "precio": 15000,  "rol_id": 1480750694020415660},
    "4": {"nombre": "👑 Scroll CEO",         "precio": 50000,  "rol_id": 1480750975953145926},
}

# ============================================================
# 2. CONFIGURACIÓN DE INTENTS Y BOT
# ============================================================
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

# ============================================================
# 3. BASE DE DATOS  (aiosqlite — sin condiciones de carrera)
# ============================================================

async def init_db():
    """Crea la tabla si no existe."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                user_id         TEXT PRIMARY KEY,
                xp              INTEGER DEFAULT 0,
                nivel           INTEGER DEFAULT 1,
                planta          TEXT DEFAULT NULL,
                robos_exitosos  INTEGER DEFAULT 0,
                last_rob_time   REAL    DEFAULT 0,
                rob_cooldown    REAL    DEFAULT 0
            )
        """)
        await db.commit()


async def cargar_usuario(user_id: str) -> dict:
    """Devuelve los datos del usuario. Si no existe, lo crea."""
    uid = str(user_id)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM usuarios WHERE user_id = ?", (uid,)) as cur:
            row = await cur.fetchone()
        if row is None:
            await db.execute(
                "INSERT INTO usuarios (user_id) VALUES (?)", (uid,)
            )
            await db.commit()
            return {
                "user_id": uid, "xp": 0, "nivel": 1,
                "planta": None, "robos_exitosos": 0,
                "last_rob_time": 0.0, "rob_cooldown": 0.0,
            }
        d = dict(row)
        d["planta"] = json.loads(d["planta"]) if d["planta"] else None
        return d


async def guardar_usuario(user: dict):
    """Guarda todos los campos del usuario."""
    planta_json = json.dumps(user["planta"]) if user["planta"] else None
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO usuarios
                (user_id, xp, nivel, planta, robos_exitosos, last_rob_time, rob_cooldown)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                xp             = excluded.xp,
                nivel          = excluded.nivel,
                planta         = excluded.planta,
                robos_exitosos = excluded.robos_exitosos,
                last_rob_time  = excluded.last_rob_time,
                rob_cooldown   = excluded.rob_cooldown
        """, (
            user["user_id"], user["xp"], user["nivel"], planta_json,
            user["robos_exitosos"], user["last_rob_time"], user["rob_cooldown"],
        ))
        await db.commit()


async def cargar_todos() -> list[dict]:
    """Devuelve todos los usuarios (para el ranking)."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM usuarios ORDER BY xp DESC") as cur:
            rows = await cur.fetchall()
    resultado = []
    for row in rows:
        d = dict(row)
        d["planta"] = json.loads(d["planta"]) if d["planta"] else None
        resultado.append(d)
    return resultado

# ============================================================
# 4. MOTOR DE EVENTOS
# ============================================================

def estado_eventos() -> dict:
    ahora = datetime.datetime.now()
    dia   = ahora.weekday()
    hora  = ahora.hour
    return {
        "xp_doble":   dia >= 5,
        "happy_hour": 20 <= hora <= 22,
        "eco_night":  0  <= hora <= 5,
        "es_finde":   dia >= 5,
    }


@tasks.loop(minutes=60)
async def anunciar_eventos():
    canal = bot.get_channel(CANAL_EVENTOS_ID)
    if not canal:
        return
    ev    = estado_eventos()
    ahora = datetime.datetime.now()
    if ev["xp_doble"] and ahora.hour == 9:
        emb = discord.Embed(
            title="🔥 FIN DE SEMANA SCROLL",
            description="¡Todo el trabajo da **XP DOBLE** hoy!",
            color=0xff4757,
        )
        await canal.send(embed=emb)
    if ev["happy_hour"] and ahora.hour == 20:
        emb = discord.Embed(
            title="📈 HAPPY HOUR ACTIVADO",
            description="Inversiones seguras en `!invest` (x0 eliminado).",
            color=0x2ed573,
        )
        await canal.send(embed=emb)

# ============================================================
# 5. SISTEMA DE NIVELES
# ============================================================

def calcular_xp_necesaria(nivel: int) -> int:
    return 100 * (nivel ** 2)


def actualizar_nivel(user: dict) -> tuple[bool, int]:
    """Sube de nivel si corresponde. NO baja de nivel (experiencia UX mejorada)."""
    nivel_inicial = user["nivel"]
    while user["xp"] >= calcular_xp_necesaria(user["nivel"]):
        user["nivel"] += 1
    cambio = user["nivel"] != nivel_inicial
    return cambio, user["nivel"]

# ============================================================
# 6. LÓGICA DE TRIVIA  (aiohttp)
# ============================================================

async def obtener_token_trivia():
    global TOKEN_TRIVIA
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://opentdb.com/api_token.php?command=request") as r:
                res = await r.json(content_type=None)
        if res["response_code"] == 0:
            TOKEN_TRIVIA = res["token"]
            print(f"✅ Token de Trivia renovado: {TOKEN_TRIVIA}")
    except Exception as e:
        print(f"❌ Error al obtener token: {e}")


async def obtener_pregunta_api() -> dict | None:
    global TOKEN_TRIVIA
    eco_keywords = [
        "agua", "tierra", "planta", "animal", "oceano", "bosque", "selva",
        "reciclaje", "contaminacion", "clima", "atmosfera", "especie",
        "naturaleza", "ecologia", "verde", "solar", "energia", "bio",
        "planeta", "arbol", "mar", "rio", "basura", "ozono", "ambiental",
    ]
    intentos = 0
    async with aiohttp.ClientSession() as session:
        while intentos < 10:
            url = f"https://opentdb.com/api.php?amount=1&category=17&type=multiple&token={TOKEN_TRIVIA}"
            try:
                async with session.get(url) as r:
                    res = await r.json(content_type=None)
                if res["response_code"] in [3, 4]:
                    await obtener_token_trivia()
                    continue
                if res["response_code"] == 0:
                    item      = res["results"][0]
                    traductor = GoogleTranslator(source="en", target="es")
                    preg_es   = traductor.translate(html.unescape(item["question"]))
                    if any(w in preg_es.lower() for w in eco_keywords):
                        corr_es   = traductor.translate(html.unescape(item["correct_answer"]))
                        incorr_es = [traductor.translate(html.unescape(a)) for a in item["incorrect_answers"]]
                        opciones  = incorr_es + [corr_es]
                        random.shuffle(opciones)
                        return {
                            "pregunta":   preg_es,
                            "correcta":   corr_es,
                            "opciones":   opciones,
                            "dificultad": item["difficulty"],
                        }
                    else:
                        intentos += 1
            except Exception as e:
                print(f"❌ Error trivia: {e}")
                break
    return None

# ============================================================
# 7. COMANDOS
# ============================================================

@bot.command()
async def help(ctx):
    ev    = estado_eventos()
    color = 0xff4757 if ev["xp_doble"] else 0x2ecc71
    embed = discord.Embed(
        title="🌿 EcoTrack Pro | Panel de Control",
        description="Bot oficial de **Scroll Studio**.",
        color=color,
    )
    event_status = []
    if ev["xp_doble"]:   event_status.append("🔥 **XP Doble Activo**")
    if ev["happy_hour"]: event_status.append("📈 **Happy Hour Inversión**")
    if ev["eco_night"]:  event_status.append("🛡️ **Riego Nocturno Seguro**")
    if event_status:
        embed.add_field(name="📢 EVENTOS ACTUALES", value="\n".join(event_status), inline=False)

    embed.add_field(name="🛠️ Productividad",  value="`!work`, `!daily`, `!trivia`, `!clima`, `!transfer`", inline=False)
    embed.add_field(name="🤖 IA",              value="`!ask [pregunta]`",                                              inline=False)
    embed.add_field(name="🌿 Eco-Grow",        value="`!plantar`, `!regar`, `!status_planta`",              inline=False)
    embed.add_field(name="🎲 Economía",        value="`!invest`, `!rob`, `!tacho`",                         inline=False)
    embed.add_field(name="📈 Admin",           value="`!perfil`, `!shop`, `!buy`, `!top`, `!addxp`",        inline=False)
    embed.set_footer(
        text="Scroll Studio 2026",
        icon_url=ctx.author.avatar.url if ctx.author.avatar else "",
    )
    await ctx.send(embed=embed)


@bot.command()
async def clima(ctx, *, ciudad: str = None):
    if not ciudad:
        return await ctx.send("🌍 Uso: `!clima [ciudad]`")
    url = (
        f"http://api.openweathermap.org/data/2.5/weather"
        f"?q={ciudad}&appid={WEATHER_KEY}&units=metric&lang=es"
    )
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as r:
                response = await r.json(content_type=None)
        if response["cod"] == 200:
            temp     = response["main"]["temp"]
            desc     = response["weather"][0]["description"].capitalize()
            icon_url = f"http://openweathermap.org/img/wn/{response['weather'][0]['icon']}@2x.png"
            embed    = discord.Embed(
                title=f"🌡️ Clima en {response['name']}",
                description=f"**{desc}**",
                color=0x3498db,
            )
            embed.set_thumbnail(url=icon_url)
            embed.add_field(name="Temperatura", value=f"{temp}°C",                         inline=True)
            embed.add_field(name="Humedad",      value=f"{response['main']['humidity']}%",  inline=True)
            await ctx.send(embed=embed)
        else:
            await ctx.send("❌ Ciudad no encontrada.")
    except Exception as e:
        print(f"❌ Error clima: {e}")
        await ctx.send("📡 Error de conexión.")


@bot.command()
async def plantar(ctx):
    user = await cargar_usuario(ctx.author.id)
    if user.get("planta"):
        return await ctx.send("🌱 Ya tienes una planta activa.")
    user["planta"] = {
        "estado":          "Semilla",
        "nivel_planta":    1,
        "regadas_sesion":  0,
        "progreso_nivel":  0,
        "limite_muerte":   random.randint(6, 10),
        "ultima_sesion":   time.time(),   # marca de cuándo empezó la sesión actual
    }
    await guardar_usuario(user)
    await ctx.send("🌱 **¡Plantada!** 1-5 regadas seguras, 6-10 riesgo de ahogo.")


@bot.command()
async def regar(ctx):
    user = await cargar_usuario(ctx.author.id)
    if not user.get("planta"):
        return await ctx.send("❌ No tienes planta.")

    ev, p = estado_eventos(), user["planta"]

    # ── Reset de sesión cada hora ──────────────────────────────────────────
    ahora_ts = time.time()
    if "ultima_sesion" not in p:
        p["ultima_sesion"] = ahora_ts          # compatibilidad con plantas viejas

    if ahora_ts - p["ultima_sesion"] >= 3600:
        p["regadas_sesion"] = 0
        p["ultima_sesion"]  = ahora_ts
        p["limite_muerte"]  = random.randint(6, 10)
        await ctx.send("🌊 **Nueva sesión de riego iniciada.** El contador volvió a 0.")
    # ──────────────────────────────────────────────────────────────────────

    p["regadas_sesion"] += 1
    p["progreso_nivel"]  += 1

    if p["regadas_sesion"] >= p["limite_muerte"] and not ev["eco_night"]:
        await ctx.send(f"💀 **¡AHOGADA!** Tu planta murió en la regada {p['regadas_sesion']}.")
        user["planta"] = None
        await guardar_usuario(user)
        return

    user["xp"] += 100 * p["nivel_planta"]
    msg_evo = ""
    if p["progreso_nivel"] >= 10:
        p["nivel_planta"]   += 1
        p["progreso_nivel"]  = 0
        estados  = ["Brote 🌿", "Arbolito 🌳", "Árbol Sagrado ✨"]
        p["estado"] = estados[min(p["nivel_planta"] - 2, 2)] if p["nivel_planta"] > 1 else "Semilla"
        msg_evo = f"🌟 **¡EVOLUCIONÓ A {p['estado']}!**\n"

    if p["regadas_sesion"] >= 10:
        p["regadas_sesion"]  = 0
        p["limite_muerte"]   = random.randint(6, 10)
        user["xp"]          += 500
        await guardar_usuario(user)
        return await ctx.send("🏆 **¡RETORNO TRIUNFAL!** 10 regadas exitosas. +500 XP.")

    subio, nuevo_lv = actualizar_nivel(user)
    await guardar_usuario(user)

    color = 0x2ecc71 if p["regadas_sesion"] <= 5 else 0xe74c3c
    embed = discord.Embed(title="💦 Riego Exitoso", description=msg_evo, color=color)
    embed.add_field(name="Sesión Actual", value=f"{p['regadas_sesion']}/10", inline=True)
    if subio:
        embed.add_field(name="🎉 ¡NIVEL UP!", value=f"Ahora eres nivel **{nuevo_lv}**", inline=False)
    await ctx.send(embed=embed)


@bot.command()
async def status_planta(ctx):
    user = await cargar_usuario(ctx.author.id)
    if not user.get("planta"):
        return await ctx.send("🏜️ No tienes planta.")
    p = user["planta"]

    # Tiempo restante para el reset de sesión
    ultima = p.get("ultima_sesion", time.time())
    restante_s = max(0, 3600 - (time.time() - ultima))
    minutos    = int(restante_s // 60)
    segundos   = int(restante_s % 60)

    embed = discord.Embed(title="🌿 Estado del Árbol", color=0x2ecc71)
    embed.add_field(name="Fase",          value=p["estado"],                    inline=True)
    embed.add_field(name="Nivel",         value=p["nivel_planta"],               inline=True)
    embed.add_field(name="Riesgo Sesión", value=f"🔥 {p['regadas_sesion']}/10",  inline=False)
    embed.add_field(name="⏱️ Reset en",   value=f"{minutos}m {segundos}s",       inline=False)
    await ctx.send(embed=embed)


@bot.command()
@commands.cooldown(1, 30, commands.BucketType.user)
async def work(ctx):
    user     = await cargar_usuario(ctx.author.id)
    ev       = estado_eventos()
    ganancia = random.randint(40, 130)
    if ev["xp_doble"]:
        ganancia *= 2
    user["xp"] += ganancia
    subio, nuevo_lv = actualizar_nivel(user)
    await guardar_usuario(user)

    TRABAJOS = [
        {"titulo": "🐢 Rescate marino",
         "desc":   "Desenredaste una tortuga atrapada en plástico en la costa. La liberaste con éxito.",
         "color":  0x1abc9c},
        {"titulo": "💻 API ecológica",
         "desc":   "Desarrollaste una API para monitorear la calidad del aire en tiempo real en tu ciudad.",
         "color":  0x3498db},
        {"titulo": "🌳 Reforestación",
         "desc":   "Plantaste 15 árboles nativos en una zona deforestada junto a voluntarios de Scroll Studio.",
         "color":  0x2ecc71},
        {"titulo": "♻️ Campaña de reciclaje",
         "desc":   "Organizaste una campaña de reciclaje en tu barrio. Se recolectaron 200kg de residuos.",
         "color":  0xf39c12},
        {"titulo": "🌊 Limpieza de playa",
         "desc":   "Participaste en una limpieza de playa y retiraste bolsas, botellas y microplásticos.",
         "color":  0x2980b9},
        {"titulo": "☀️ Panel solar instalado",
         "desc":   "Instalaste paneles solares en una escuela rural. Ahora funciona con energía limpia.",
         "color":  0xf1c40f},
        {"titulo": "🐝 Santuario de abejas",
         "desc":   "Construiste y registraste un santuario de abejas para proteger a los polinizadores locales.",
         "color":  0xe67e22},
        {"titulo": "📊 Análisis de huella de carbono",
         "desc":   "Calculaste la huella de carbono de una empresa local y propusiste un plan de reducción.",
         "color":  0x9b59b6},
        {"titulo": "🚲 Ruta ciclista verde",
         "desc":   "Diseñaste una ruta ciclista en la ciudad para reducir el uso de autos y las emisiones de CO₂.",
         "color":  0x27ae60},
        {"titulo": "🧪 Sensor de contaminación",
         "desc":   "Programaste un sensor IoT para detectar contaminación en ríos y enviarlo a una base de datos.",
         "color":  0xe74c3c},
    ]

    trabajo = random.choice(TRABAJOS)
    embed = discord.Embed(
        title=f"{trabajo['titulo']} — +{ganancia} XP",
        description=trabajo["desc"],
        color=trabajo["color"],
    )
    if ev["xp_doble"]:
        embed.set_footer(text="🔥 XP DOBLE ACTIVO — Fin de semana Scroll")
    await ctx.send(embed=embed)
    if subio:
        await ctx.send(f"🎊 ¡Felicidades {ctx.author.mention}! Has ascendido al nivel **{nuevo_lv}**.")


@bot.command()
@commands.cooldown(1, 60, commands.BucketType.user)
async def invest(ctx, cantidad: int):
    user = await cargar_usuario(ctx.author.id)
    if cantidad > user["xp"] or cantidad <= 0:
        return await ctx.send("❌ Fondos insuficientes.")
    ev = estado_eventos()
    user["xp"] -= cantidad
    msg = await ctx.send(f"📈 Invirtiendo... {'🟢 **HAPPY HOUR**' if ev['happy_hour'] else ''}")
    await asyncio.sleep(3)
    pool = [0.5, 1.5, 2.0, 5.0] if ev["happy_hour"] else [0, 0.5, 1.5, 2.0, 5.0]
    mult = random.choice(pool)
    user["xp"] += int(cantidad * mult)
    subio, nuevo_lv = actualizar_nivel(user)
    await guardar_usuario(user)
    await msg.edit(content=f"📊 Resultado: x{mult}. Tienes **{user['xp']} XP**.")
    if subio:
        await ctx.send(f"🎊 ¡Nivel **{nuevo_lv}** alcanzado!")


@bot.command()
async def rob(ctx, victima: discord.Member):
    if victima.id == ctx.author.id:
        return await ctx.send("❌ No puedes hackearte a ti mismo.")
    if victima.bot:
        return await ctx.send("🤖 Mis firewalls son de titanio.")

    ladron = await cargar_usuario(ctx.author.id)
    pobre  = await cargar_usuario(victima.id)
    ahora  = time.time()

    if ahora - ladron.get("last_rob_time", 0) < ladron.get("rob_cooldown", 0):
        restante = int(ladron["rob_cooldown"] - (ahora - ladron.get("last_rob_time", 0)))
        return await ctx.send(f"⏳ Espera **{restante // 60}m {restante % 60}s**.")

    if pobre["xp"] < 100 or ladron["xp"] < 50:
        return await ctx.send("⚠️ Condiciones de XP no cumplidas.")

    fake_ip = f"{random.randint(1,255)}.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"http://ip-api.com/json/{fake_ip}?fields=status,country,city,isp",
                timeout=aiohttp.ClientTimeout(total=5),
            ) as r:
                ip_data = await r.json(content_type=None)
        loc_info = (
            f"📍 Nodo: **{ip_data['city']}, {ip_data['country']}**\n🌐 ISP: `{ip_data['isp']}`"
            if ip_data["status"] == "success"
            else "📍 Nodo: Desconocido"
        )
    except Exception:
        loc_info = "📍 Nodo: Cifrado"

    embed = discord.Embed(
        title="🕵️ Escaneando...",
        description=(
            f"**Objetivo:** {victima.name}\nIP: `{fake_ip}`\n{loc_info}\n\n"
            "1️⃣ Phishing | 2️⃣ SQL Injection | 3️⃣ Brute Force"
        ),
        color=0x2c3e50,
    )
    msg_panel = await ctx.send(embed=embed)
    correcta  = str(random.randint(1, 3))

    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel and m.content in ["1", "2", "3"]

    try:
        res = await bot.wait_for("message", check=check, timeout=20.0)
        await res.delete()
        if res.content == correcta:
            prob = random.random()
            if   prob < 0.01: por, txt = 0.50, "🌟 **ZERO-DAY!**"
            elif prob < 0.21: por, txt = 0.10, "⚡ **ACCESO PROFUNDO**"
            elif prob < 0.51: por, txt = 0.05, "✅ **EXITO**"
            else:             por, txt = 0,    "⚠️ **FALLO**"

            if por > 0:
                botin         = int(pobre["xp"] * por)
                pobre["xp"] -= botin
                ladron["xp"] += botin
                ladron["robos_exitosos"] = ladron.get("robos_exitosos", 0) + 1
                await msg_panel.edit(content=f"{txt}\nRobaste **{botin} XP**.", embed=None)
            else:
                await msg_panel.edit(content=txt, embed=None)
            ladron["last_rob_time"] = ahora
            ladron["rob_cooldown"]  = 600
        else:
            multa         = int(ladron["xp"] * 0.10)
            ladron["xp"] -= multa
            ladron["last_rob_time"] = ahora
            ladron["rob_cooldown"]  = 60
            await msg_panel.edit(content=f"🚨 **FIREWALL ACTIVADO!** Perdiste **{multa} XP**.", embed=None)

        await guardar_usuario(ladron)
        await guardar_usuario(pobre)
    except asyncio.TimeoutError:
        await msg_panel.edit(content="⏰ Conexión cerrada.", embed=None)


@bot.command()
@commands.cooldown(1, 86400, commands.BucketType.user)
async def daily(ctx):
    user = await cargar_usuario(ctx.author.id)
    user["xp"] += 500
    subio, nuevo_lv = actualizar_nivel(user)
    await guardar_usuario(user)
    await ctx.send(embed=discord.Embed(
        title="🎁 Daily",
        description="Recibiste **500 XP**.",
        color=0x9b59b6,
    ))
    if subio:
        await ctx.send(f"🎉 ¡Subiste al nivel **{nuevo_lv}**!")


@bot.command()
async def shop(ctx):
    embed = discord.Embed(title="🛒 Scroll Store", color=0x2ecc71)
    for k, v in TIENDA_ITEMS.items():
        embed.add_field(name=f"{k}. {v['nombre']}", value=f"Precio: **{v['precio']} XP**", inline=False)
    await ctx.send(embed=embed)


@bot.command()
async def buy(ctx, item_id: str):
    if item_id not in TIENDA_ITEMS:
        return await ctx.send("❌ ID inválido.")
    item = TIENDA_ITEMS[item_id]
    user = await cargar_usuario(ctx.author.id)
    if user["xp"] < item["precio"]:
        return await ctx.send("❌ XP insuficiente.")
    rol = ctx.guild.get_role(int(item["rol_id"]))
    if rol:
        try:
            user["xp"] -= item["precio"]
            await ctx.author.add_roles(rol)
            await guardar_usuario(user)
            await ctx.send(f"✅ ¡Rango **{item['nombre']}** obtenido!")
        except Exception:
            await ctx.send("❌ Error de permisos.")
    else:
        await ctx.send("❌ Rol no encontrado.")


@bot.command()
async def perfil(ctx, usuario: discord.Member = None):
    usuario  = usuario or ctx.author
    user     = await cargar_usuario(usuario.id)
    xp_prox  = calcular_xp_necesaria(user["nivel"])
    xp_ant   = calcular_xp_necesaria(user["nivel"] - 1) if user["nivel"] > 1 else 0
    por      = max(0, min((user["xp"] - xp_ant) / (xp_prox - xp_ant), 1.0))
    barra    = "🟩" * int(por * 15) + "⬜" * (15 - int(por * 15))
    embed    = discord.Embed(title=f"📊 Perfil de {usuario.name}", color=0x3498db)
    embed.add_field(name="Nivel",    value=f"✨ {user['nivel']}", inline=True)
    embed.add_field(name="XP",       value=f"⭐ {user['xp']}",   inline=True)
    embed.add_field(name="Progreso", value=f"{barra}\n({user['xp']}/{xp_prox})", inline=False)
    await ctx.send(embed=embed)


@bot.command()
async def trivia(ctx):
    data = await obtener_pregunta_api()
    if not data:
        return await ctx.send("📡 Error API.")
    opc   = "\n".join([f"🔹 {o}" for o in data["opciones"]])
    embed = discord.Embed(
        title="🌍 Trivia Eco",
        description=f"**{data['pregunta']}**\n\n{opc}",
        color=0x2ecc71,
    )
    await ctx.send(embed=embed)

    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel

    try:
        msg = await bot.wait_for("message", check=check, timeout=30.0)
        if msg.content.lower().strip() == data["correcta"].lower():
            user = await cargar_usuario(ctx.author.id)
            user["xp"] += 100
            subio, nuevo_lv = actualizar_nivel(user)
            await guardar_usuario(user)
            await ctx.send("✅ ¡Correcto! +100 XP.")
            if subio:
                await ctx.send(f"🌟 ¡Ascendiste al nivel **{nuevo_lv}**!")
        else:
            await ctx.send(f"❌ Era: **{data['correcta']}**")
    except asyncio.TimeoutError:
        await ctx.send("⏰ Tiempo agotado.")


@bot.command()
async def transfer(ctx, victima: discord.Member, cantidad: int):
    if victima.id == ctx.author.id:
        return await ctx.send("❌ No puedes enviarte XP a ti mismo.")
    if cantidad <= 0:
        return await ctx.send("❌ Cantidad inválida.")

    remitente = await cargar_usuario(ctx.author.id)
    receptor  = await cargar_usuario(victima.id)

    if remitente["xp"] < cantidad:
        return await ctx.send("❌ No tienes suficiente XP.")

    remitente["xp"] -= cantidad
    receptor["xp"]  += cantidad
    actualizar_nivel(remitente)
    subio_r, lv_r = actualizar_nivel(receptor)

    await guardar_usuario(remitente)
    await guardar_usuario(receptor)

    await ctx.send(f"💸 **Transferencia Exitosa:** Has enviado **{cantidad} XP** a {victima.mention}.")
    if subio_r:
        await ctx.send(f"🎉 ¡{victima.name} ha subido al nivel **{lv_r}** gracias a tu regalo!")


@bot.command()
async def tacho(ctx, *, objeto: str = None):
    guia = {
        "botella": "Amarillo 🟡",
        "papel":   "Azul 🔵",
        "vidrio":  "Verde 🟢",
        "manzana": "Marrón 🟤",
    }
    res = next((v for k, v in guia.items() if k in (objeto or "").lower()), "Negro ⚫")
    await ctx.send(f"♻️ Destino: **{res}**")


@bot.command()
@commands.has_permissions(administrator=True)
async def addxp(ctx, cantidad: int, usuario: discord.Member = None):
    usuario = usuario or ctx.author
    user    = await cargar_usuario(usuario.id)
    user["xp"] += cantidad
    actualizar_nivel(user)
    await guardar_usuario(user)
    await ctx.send(f"💉 Añadidos **{cantidad} XP** a {usuario.name}.")


@bot.command()
async def top(ctx):
    todos = await cargar_todos()
    embed = discord.Embed(title="🏆 Ranking Global Scroll Studio", color=0xf1c40f)
    desc  = ""
    for i, d in enumerate(todos[:5], 1):
        try:
            u      = await bot.fetch_user(int(d["user_id"]))
            nombre = u.name
        except Exception:
            nombre = "Desconocido"
        desc += f"**{i}. {nombre}** - Nivel {d['nivel']} ({d['xp']} XP)\n"
    embed.description = desc
    await ctx.send(embed=embed)


@bot.command()
@commands.cooldown(1, 15, commands.BucketType.user)
async def ask(ctx, *, pregunta: str = None):
    if not pregunta:
        return await ctx.send("🤖 Uso: `!ask [tu pregunta]`")
    if not GROQ_API_KEY:
        return await ctx.send("❌ La IA no está configurada.")

    pensando = await ctx.send("🤔 Pensando...")

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type":  "application/json",
    }
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {
                "role":    "system",
                "content": (
                    "Eres EcoBot, el asistente inteligente de Scroll Studio. "
                    "Eres amigable, directo y respondes en español. "
                    "Tus respuestas son cortas y útiles, máximo 3 párrafos."
                ),
            },
            {"role": "user", "content": pregunta},
        ],
        "max_tokens": 512,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as r:
                data = await r.json(content_type=None)

        respuesta = data["choices"][0]["message"]["content"].strip()

        embed = discord.Embed(
            title="🤖 EcoBot responde",
            description=respuesta,
            color=0x7c5cbf,
        )
        embed.set_footer(text=f"Pregunta de {ctx.author.name} • Powered by Groq")
        await pensando.delete()
        await ctx.send(embed=embed)

    except KeyError:
        await pensando.edit(content="❌ Error al procesar la respuesta de la IA.")
    except Exception as e:
        print(f"❌ Error !ask: {e}")
        await pensando.edit(content=f"📡 Error: {e}")

# ============================================================
# 8. EVENTOS DEL BOT
# ============================================================

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"⏳ Calma... espera **{round(error.retry_after)}s**.", delete_after=5)


@bot.event
async def on_ready():
    await init_db()
    await obtener_token_trivia()
    anunciar_eventos.start()
    print(f"✅ EcoTrack ONLINE: {bot.user}")

# ============================================================
# 9. ARRANQUE
# ============================================================
if TOKEN:
    bot.run(TOKEN)