# 🌿 EcoTrack Pro — Bot de Discord

> Bot oficial de **Scroll Studio** — Economía, Eco-Grow, IA y más.

![Python](https://img.shields.io/badge/Python-3.14-blue?style=flat-square&logo=python)
![Discord.py](https://img.shields.io/badge/discord.py-2.x-5865F2?style=flat-square&logo=discord)
![SQLite](https://img.shields.io/badge/SQLite-aiosqlite-003B57?style=flat-square&logo=sqlite)
![Groq](https://img.shields.io/badge/IA-Groq%20LLaMA-orange?style=flat-square)
![License](https://img.shields.io/badge/Proyecto-Kodland%20Python%20Pro-green?style=flat-square)

---

## 📖 Descripción

EcoTrack Pro es un bot de Discord que combina un sistema de economía virtual basado en XP, minijuegos interactivos, una mecánica de cultivo de plantas y una IA conversacional integrada. Su objetivo es fomentar la participación de la comunidad y la conciencia medioambiental.

---

## ⚙️ Tecnologías

| Librería | Uso |
|---|---|
| `discord.py` | Framework principal del bot |
| `aiosqlite` | Base de datos asíncrona (SQLite) |
| `aiohttp` | Llamadas HTTP asíncronas a APIs |
| `deep_translator` | Traducción de preguntas de trivia |
| `python-dotenv` | Carga de variables de entorno |

### APIs externas
- **OpenWeatherMap** — Clima en tiempo real
- **Open Trivia DB** — Preguntas de ciencias/ecología
- **ip-api.com** — Geolocalización (comando `!rob`)
- **Groq API** — IA conversacional con LLaMA 3.3

---

## 🚀 Instalación

### 1. Clona el repositorio
```bash
git clone https://github.com/Dubmfj/Eco-Track.git
cd Eco-Track
```

### 2. Instala las dependencias
```bash
pip install discord.py aiosqlite aiohttp deep-translator python-dotenv
```

### 3. Crea tu archivo `.env`
```env
DISCORD_TOKEN=tu_token_de_discord
WEATHER_API_KEY=tu_key_de_openweathermap
GROQ_API_KEY=tu_key_de_groq
CANAL_EVENTOS_ID=id_del_canal_de_discord
```

### 4. Ejecuta el bot
```bash
python main.py
```

---

## 🎮 Comandos

### 🛠️ Productividad
| Comando | Descripción | Cooldown |
|---|---|---|
| `!work` | Realiza un trabajo ecológico y gana XP | 30s |
| `!daily` | Recoge tu recompensa diaria de 500 XP | 24h |
| `!trivia` | Responde preguntas de ecología y gana 100 XP | — |
| `!clima [ciudad]` | Muestra el clima actual de cualquier ciudad | — |
| `!transfer [@user] [xp]` | Transfiere XP a otro usuario | — |

### 🌿 Eco-Grow
| Comando | Descripción |
|---|---|
| `!plantar` | Planta tu semilla virtual |
| `!regar` | Riega tu planta (contador se resetea cada hora) |
| `!status_planta` | Ver estado y tiempo de reset de tu planta |

### 🎲 Economía
| Comando | Descripción | Cooldown |
|---|---|---|
| `!invest [cantidad]` | Invierte XP con multiplicadores aleatorios | 60s |
| `!rob [@user]` | Mini-juego de hackeo para robar XP | Variable |
| `!tacho [objeto]` | Guía de reciclaje por colores | — |

### 🤖 IA
| Comando | Descripción | Cooldown |
|---|---|---|
| `!ask [pregunta]` | Pregúntale algo a EcoBot (powered by Groq) | 15s |

### 📈 Administración
| Comando | Descripción |
|---|---|
| `!perfil [@user]` | Ver nivel, XP y barra de progreso |
| `!shop` | Ver roles disponibles en la tienda |
| `!buy [id]` | Comprar un rol con XP |
| `!top` | Ranking global de los 5 mejores |
| `!addxp [cantidad] [@user]` | Solo admins: añadir XP |

---

## 🌟 Eventos Automáticos

El bot detecta automáticamente eventos según el día y la hora:

- 🔥 **XP Doble** — Activo todos los fines de semana
- 📈 **Happy Hour** — Entre las 20:00 y 22:00h (inversiones seguras)
- 🛡️ **Eco Night** — Entre las 00:00 y 05:00h (planta protegida)

---

## 🛒 Tienda de Roles

| Rol | Precio |
|---|---|
| 🌱 Eco-Aprendiz | 1,000 XP |
| 💻 Junior Dev | 5,000 XP |
| ⚡ Senior Architect | 15,000 XP |
| 👑 Scroll CEO | 50,000 XP |

---

## 👨‍💻 Autor

**Daniel Pachas**
Proyecto Final — Python Pro · Kodland · 2026

[![GitHub](https://img.shields.io/badge/GitHub-Dubmfj-181717?style=flat-square&logo=github)](https://github.com/Dubmfj)
