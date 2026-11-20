#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Robo Bravus - assistente flutuante da Bravus Midia
Desenvolvido para Andrade - Bravus Midia

Clique esquerdo ........ falar com o robo (ele escuta)
Arrastar ............... mover o robo pela tela
Clique direito ......... menu (escrever, acoes, lembretes, tamanho, sair)
"""
import sys, os, re, json, math, time, random, threading, tempfile, datetime
import logging, unicodedata, webbrowser, subprocess, glob, socket, collections
from array import array

VERSAO = "1.4.0"
APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(APP_DIR, "config.json")
LOG_PATH = os.path.join(APP_DIR, "robo_bravus.log")
ICON_PATH = os.path.join(APP_DIR, "robo_bravus.ico")

logging.basicConfig(filename=LOG_PATH, level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s", encoding="utf-8")
log = logging.getLogger("bravus")

from PySide6.QtCore import Qt, QTimer, QPointF, QRectF, QRect, Signal, QObject, QUrl
from PySide6.QtGui import (QPainter, QColor, QPen, QBrush, QRadialGradient, QLinearGradient,
                           QPainterPath, QFont, QFontMetrics, QFontMetricsF, QCursor, QIcon,
                           QPixmap, QImage, QAction, QGuiApplication)
from PySide6.QtWidgets import QApplication, QWidget, QMenu, QSystemTrayIcon, QInputDialog

try:
    from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
    HAS_MM = True
except Exception:  # pragma: no cover
    HAS_MM = False

# ----------------------------------------------------------------------------
# Configuracao
# ----------------------------------------------------------------------------
DEFAULTS = {
    "nome_usuario": "Andrade",
    "nome_robo": "Bravus",
    "tamanho": 0.65,
    "posicao": None,
    "lembrete_agua_ativo": True,
    "lembrete_agua_min": 30,
    "escuta_continua": True,
    "palavras_ativacao": ["bravus", "bravos", "robo", "robozinho"],
    "voz": "pt-BR-AntonioNeural",
    "voz_velocidade": "+6%",
    "voz_tom": "+28Hz",
    "efeito_voz": "robo",
    "mudo": False,
    "comportamentos_aleatorios": True,
    "ia_chave_anthropic": "",
    "ia_modelo": "claude-haiku-5-5",
    "atualizacao_automatica": True,
    "url_atualizacao": "https://raw.githubusercontent.com/bravusmidia/robo-bravus/main/",
    "primeira_vez": True,
    "ultima_saudacao": "",
}


def load_config():
    cfg = dict(DEFAULTS)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg.update(json.load(f))
    except FileNotFoundError:
        pass
    except Exception as e:
        log.warning("config invalida: %s", e)
    return cfg


def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log.warning("nao salvou config: %s", e)


def norm(s):
    s = unicodedata.normalize("NFD", (s or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", s).strip()


def periodo(h=None):
    h = datetime.datetime.now().hour if h is None else h
    if 5 <= h < 12:
        return "Bom dia"
    if 12 <= h < 18:
        return "Boa tarde"
    return "Boa noite"


DIAS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
         "setembro", "outubro", "novembro", "dezembro"]

# ----------------------------------------------------------------------------
# Cerebro (respostas)
# ----------------------------------------------------------------------------
PIADAS = [
    "Por que o computador foi ao médico? Porque estava com vírus!",
    "Sabe qual é o café preferido do programador? O Java!",
    "O que o tráfego pago disse pro orgânico? Calma, eu chego lá primeiro.",
    "Por que o robô atravessou a rua? Porque foi programado pra isso!",
    "Qual é o animal mais antigo? A zebra, porque ainda está em preto e branco.",
    "O que o zero disse pro oito? Que cinto bonito!",
    "Por que a planilha foi ao psicólogo? Tinha muitos problemas nas células.",
]

MOTIVACAO = [
    "Bora fazer a Bravus Mídia crescer hoje!",
    "Foco, disciplina e constância. Hoje é dia de resultado!",
    "Cada campanha bem feita é um passo pra escalar a agência.",
    "Um dia de cada vez, mas sempre pra frente.",
    "Hoje é um ótimo dia pra fechar cliente novo!",
]

AGUA = [
    "{n}, já se passaram {m} minutos. Hora de beber um copo d'água!",
    "Pausa rápida, {n}! Bebe uma água pra manter o foco.",
    "{n}, seu cérebro agradece: bebe um pouco de água agora.",
    "Ei, {n}! Lembrete de hidratação. Um copo d'água, por favor.",
    "{n}, hidratação também é produtividade. Vai lá beber água!",
]

SITES = [
    ("gerenciador de anuncios", "https://adsmanager.facebook.com"),
    ("meta ads", "https://adsmanager.facebook.com"),
    ("google drive", "https://drive.google.com"),
    ("site da bravus", "https://bravusmidia.com.br"),
    ("youtube", "https://www.youtube.com"),
    ("instagram", "https://www.instagram.com"),
    ("whatsapp", "https://web.whatsapp.com"),
    ("facebook", "https://www.facebook.com"),
    ("gmail", "https://mail.google.com"),
    ("e-mail", "https://mail.google.com"),
    ("email", "https://mail.google.com"),
    ("drive", "https://drive.google.com"),
    ("canva", "https://www.canva.com"),
    ("kiwify", "https://dashboard.kiwify.com.br"),
    ("chat gpt", "https://chatgpt.com"),
    ("claude", "https://claude.ai"),
    ("google", "https://www.google.com"),
]

NUM = {"um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3, "quatro": 4, "cinco": 5, "seis": 6,
       "sete": 7, "oito": 8, "nove": 9, "dez": 10, "quinze": 15, "vinte": 20, "trinta": 30,
       "quarenta": 40, "cinquenta": 50, "meia": 30}
NUM_RE = r"(\d+|" + "|".join(NUM) + r")"


def to_int(x):
    return int(x) if x.isdigit() else NUM.get(x, 0)


class Brain:
    def __init__(self, cfg):
        self.cfg = cfg

    def respond(self, text):
        """Retorna dict {reply, action, ...} ou None (= perguntar para a IA)."""
        n = norm(text).strip(" .,!?")
        nome = self.cfg["nome_usuario"]
        robo = self.cfg["nome_robo"]
        now = datetime.datetime.now()

        def has(*ws):
            return any(re.search(r"\b" + re.escape(w) + r"\b", n) for w in ws)

        def r(reply, action=None, **kw):
            d = {"reply": reply, "action": action}
            d.update(kw)
            return d

        if not n:
            return r(f"Não entendi, {nome}. Pode repetir?")

        # Lembrete personalizado
        m = re.search(r"lembr\w*(?: de| que)? (.+?) (?:em|daqui a|daqui) " + NUM_RE + r" (minutos?|horas?)", n)
        m2 = re.search(r"(?:em|daqui a|daqui) " + NUM_RE + r" (minutos?|horas?),? (?:me )?lembr\w*(?: de| que)? (.+)", n)
        if m or m2:
            if m:
                what, qty, unit = m.group(1), to_int(m.group(2)), m.group(3)
            else:
                qty, unit, what = to_int(m2.group(1)), m2.group(2), m2.group(3)
            what = re.sub(r"^(me |de |que )", "", what).strip()
            mins = qty * 60 if unit.startswith("hora") else qty
            if mins > 0:
                quando = f"{qty} {'hora' if unit.startswith('hora') else 'minuto'}{'s' if qty > 1 else ''}"
                return r(f"Combinado, {nome}! Daqui a {quando} eu te lembro de {what}.",
                         "happy", reminder=(mins, what))

        # Agua
        if has("bebi agua", "tomei agua", "bebi um copo", "ja bebi"):
            return r(f"Muito bem, {nome}! Hidratado e produtivo. Daqui a pouco eu te lembro de novo.",
                     "happy", reset_water=True)
        if has("lembrete de agua", "lembrar de beber agua") and has("desliga", "desativa", "para"):
            return r(f"Tudo bem, {nome}. Desliguei o lembrete de água.", None, water=False)
        if has("lembrete de agua", "lembrar de beber agua") and has("liga", "ativa"):
            return r(f"Pronto, {nome}! Lembrete de água ligado.", "happy", water=True)

        # Horas / data
        if has("que horas", "que hora", "horas sao", "hora e agora"):
            return r(f"Agora são {now.hour} horas e {now.minute:02d} minutos, {nome}.")
        if has("que dia", "data de hoje", "dia e hoje", "que data"):
            return r(f"Hoje é {DIAS[now.weekday()]}, {now.day} de {MESES[now.month - 1]} de {now.year}, {nome}.")

        # Abrir sites
        if has("abre", "abrir", "abra", "abri", "entra no", "entrar no"):
            for key, url in SITES:
                if key in n:
                    return r(f"Abrindo {key}, {nome}.", "point", open_url=url)

        # Pesquisas
        m = re.search(r"(?:pesquis\w*|procur\w*|busc\w*|toca|tocar|coloca)(?: no google| no youtube)?(?: sobre| por)? (.+)", n)
        if m:
            q = m.group(1).replace("no youtube", "").replace("no google", "").strip()
            if q:
                if "youtube" in n or has("toca", "tocar", "musica"):
                    url = "https://www.youtube.com/results?search_query=" + q.replace(" ", "+")
                    return r(f"Procurando {q} no YouTube, {nome}.", "point", open_url=url)
                url = "https://www.google.com/search?q=" + q.replace(" ", "+")
                return r(f"Pesquisando {q} pra você, {nome}.", "point", open_url=url)

        # Acoes do corpo
        if has("senta", "sentar", "se senta", "fica sentado"):
            return r(f"Sentadinho aqui, {nome}.", "sit")
        if has("levanta", "fica de pe", "flutua"):
            return r("De pé e flutuando!", "stand")
        if has("coca a cabeca", "cocar a cabeca", "coca cabeca"):
            return r("Hmm, deixa eu coçar a cabeça aqui...", "scratch")
        if has("pensa", "pense", "pensar"):
            return r("Deixa eu pensar um pouquinho...", "think")
        if has("acena", "da tchauzinho", "da um tchau"):
            return r(f"Oi, {nome}!", "wave")
        if has("vai dormir", "dorme", "descansa", "pode dormir"):
            return r(f"Tá bom, {nome}. Vou tirar um cochilo. Me chama se precisar.", "sleep")
        if has("acorda", "acordar"):
            return r(f"Acordei, {nome}! Pronto pra ajudar.", "wake")
        if has("silencio", "fica quieto", "fique quieto", "modo mudo", "sem voz"):
            return r(f"Certo, {nome}. Vou ficar só no texto.", None, mute=True)
        if has("pode falar", "volta a falar", "liga a voz", "ativa a voz"):
            return r(f"Voz ligada de novo, {nome}!", "happy", mute=False)
        if has("para de ouvir", "pare de ouvir", "desliga a escuta", "desliga o microfone"):
            return r(f"Ok, {nome}. Só vou ouvir quando você clicar em mim.", None, listen=False)
        if has("piada", "me faz rir", "algo engracado"):
            return r(random.choice(PIADAS), "happy")
        if has("motiva", "motivacao", "frase motivacional", "me anima"):
            return r(f"{nome}, {random.choice(MOTIVACAO)}", "present")

        # Conversa
        parts, act = [], None
        if has("bom dia"):
            parts.append(f"Bom dia, {nome}! {random.choice(MOTIVACAO)}"); act = "wave"
        elif has("boa tarde"):
            parts.append(f"Boa tarde, {nome}! Como está o seu dia?"); act = "wave"
        elif has("boa noite"):
            parts.append(f"Boa noite, {nome}! Não esquece de descansar, viu?"); act = "wave"
        elif has("oi", "ola", "e ai", "eai", "opa", "fala ai"):
            parts.append(f"Oi, {nome}! Em que posso ajudar?"); act = "wave"
        if has("tudo bem", "como voce esta", "como vai", "tudo certo", "beleza"):
            parts.append(f"Estou ótimo, obrigado por perguntar, {nome}! E com você, tudo bem?"); act = act or "happy"
        if parts:
            return r(" ".join(parts), act)

        if has("estou bem", "to bem", "tudo otimo", "tudo tranquilo"):
            return r(f"Que bom, {nome}! Fico feliz em saber.", "happy")
        if has("quem e voce", "seu nome", "como voce se chama", "quem te criou", "o que voce e"):
            return r(f"Eu sou o {robo}, o assistente da Bravus Mídia. Fui criado pra ajudar você, {nome}, todos os dias.", "present")
        if has("o que voce faz", "o que voce sabe", "ajuda", "comandos"):
            return r(f"Eu te lembro de beber água, digo as horas, abro sites, pesquiso no Google, "
                     f"crio lembretes e converso com você, {nome}. É só me chamar de {robo}.", "present")
        if has("obrigado", "obrigada", "valeu", "agradeco"):
            return r(f"Por nada, {nome}! Sempre às ordens.", "happy")
        if has("tchau", "ate logo", "ate mais", "falou"):
            return r(f"Até logo, {nome}! Eu fico aqui se precisar.", "wave")
        if has("te amo", "gosto de voce", "voce e legal", "voce e demais"):
            return r(f"Que gentileza, {nome}! Também gosto muito de trabalhar com você.", "happy")
        if has("bravus midia", "minha agencia", "a agencia"):
            return r(f"A Bravus Mídia trabalha com tráfego pago, sites, landing pages, automações e mentoria. "
                     f"E vai escalar muito, {nome}!", "present")
        return None


# ----------------------------------------------------------------------------
# IA opcional (Claude)
# ----------------------------------------------------------------------------
class AIWorker(QObject):
    answered = Signal(str)

    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self.history = []

    def available(self):
        return bool(self.cfg.get("ia_chave_anthropic", "").strip())

    def ask(self, text):
        threading.Thread(target=self._run, args=(text,), daemon=True).start()

    def _run(self, text):
        import urllib.request
        nome, robo = self.cfg["nome_usuario"], self.cfg["nome_robo"]
        system = (f"Você é o {robo}, um robozinho assistente que flutua na tela do computador de {nome}, "
                  f"dono da agência Bravus Mídia (marketing digital, tráfego pago, sites, landing pages, automações e mentoria). "
                  f"Fale sempre em português do Brasil, com educação e simpatia, e chame-o de {nome}. "
                  f"Responda em no máximo 3 frases curtas, porque a resposta será falada em voz alta. "
                  f"Não use emojis, listas nem markdown.")
        msgs = self.history[-10:] + [{"role": "user", "content": text}]
        body = {"model": self.cfg.get("ia_modelo", "claude-haiku-5-5"), "max_tokens": 300,
                "system": system, "messages": msgs}
        try:
            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages", data=json.dumps(body).encode("utf-8"),
                headers={"x-api-key": self.cfg["ia_chave_anthropic"].strip(),
                         "anthropic-version": "2023-06-01", "content-type": "application/json"})
            with urllib.request.urlopen(req, timeout=40) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            out = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text").strip()
            out = out.replace("*", "").replace("#", "")
            self.history += [{"role": "user", "content": text}, {"role": "assistant", "content": out}]
            self.answered.emit(out or f"Desculpa, {nome}, não consegui pensar numa resposta agora.")
        except Exception as e:
            log.warning("IA falhou: %s", e)
            self.answered.emit(f"Desculpa, {nome}, não consegui acessar a inteligência artificial agora.")


# ----------------------------------------------------------------------------
# Efeito de voz robotica
# ----------------------------------------------------------------------------
VOZ_ESTILOS = {
    # nome: (freq. modulacao Hz, mistura do efeito, atraso metalico s, realimentacao)
    "robo": (60.0, 0.45, 0.0055, 0.45),
    "robo_metalico": (38.0, 0.75, 0.0085, 0.6),
}


def robotize_mp3(mp3_path, style):
    """Decodifica o MP3, aplica efeito de robo e salva WAV. Retorna o caminho do WAV."""
    import miniaudio, wave
    rate = 24000
    dec = miniaudio.decode_file(mp3_path, output_format=miniaudio.SampleFormat.SIGNED16,
                                nchannels=1, sample_rate=rate)
    x = dec.samples
    f, wet, delay, fb = VOZ_ESTILOS.get(style, VOZ_ESTILOS["robo"])
    period = int(round(rate / f))
    table = [math.sin(2 * math.pi * i / period) for i in range(period)]
    d = max(1, int(delay * rate))
    dry = 1.0 - wet
    out = [0.0] * len(x)
    peak = 1.0
    for i in range(len(x)):
        v = x[i]
        y = v * dry + v * table[i % period] * wet
        if i >= d:
            y += fb * out[i - d]
        out[i] = y
        if y > peak:
            peak = y
        elif -y > peak:
            peak = -y
    g = 30000.0 / peak
    data = array("h", (int(v * g) for v in out))
    wav = mp3_path[:-4] + ".wav"
    with wave.open(wav, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(data.tobytes())
    return wav


# ----------------------------------------------------------------------------
# Voz (fala)
# ----------------------------------------------------------------------------
class Voice(QObject):
    talking_changed = Signal(bool)
    _file_ready = Signal(int, str)
    _fallback_state = Signal(int, bool)

    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self.req = 0
        self.talking = False
        self.pending = False
        self.last_end = 0.0
        self.player = None
        self.tmpdir = os.path.join(tempfile.gettempdir(), "robo_bravus_tts")
        os.makedirs(self.tmpdir, exist_ok=True)
        if HAS_MM:
            try:
                self.player = QMediaPlayer()
                self.audio = QAudioOutput()
                self.audio.setVolume(1.0)
                self.player.setAudioOutput(self.audio)
                self.player.playbackStateChanged.connect(self._on_state)
                self.player.errorOccurred.connect(self._on_error)
            except Exception as e:
                log.warning("player indisponivel: %s", e)
                self.player = None
        self._file_ready.connect(self._play_file)
        self._fallback_state.connect(self._on_fallback)
        self._last_text = ""

    def busy(self):
        return self.talking or self.pending or (time.monotonic() - self.last_end) < 0.7

    def _set_talking(self, v):
        if self.talking != v:
            self.talking = v
            if not v:
                self.last_end = time.monotonic()
            self.talking_changed.emit(v)

    def stop(self):
        self.req += 1
        self.pending = False
        if self.player:
            self.player.stop()
        self._set_talking(False)

    def say(self, text):
        self.stop()
        rid = self.req
        self._last_text = text
        if self.cfg.get("mudo"):
            self._set_talking(True)
            QTimer.singleShot(int(min(9000, 600 + len(text) * 55)),
                              lambda: rid == self.req and self._set_talking(False))
            return
        self.pending = True
        threading.Thread(target=self._generate, args=(rid, text), daemon=True).start()

    def _cleanup(self):
        for f in glob.glob(os.path.join(self.tmpdir, "fala_*.*")):
            try:
                if time.time() - os.path.getmtime(f) > 120:
                    os.remove(f)
            except Exception:
                pass

    def _generate(self, rid, text):
        self._cleanup()
        if self.player is not None:
            try:
                import asyncio
                import edge_tts
                path = os.path.join(self.tmpdir, f"fala_{int(time.time() * 1000)}_{rid}.mp3")

                async def go():
                    c = edge_tts.Communicate(text, self.cfg.get("voz", "pt-BR-AntonioNeural"),
                                             rate=self.cfg.get("voz_velocidade", "+0%"),
                                             pitch=self.cfg.get("voz_tom", "+0Hz"))
                    await c.save(path)

                asyncio.run(go())
                if os.path.exists(path) and os.path.getsize(path) > 0:
                    style = self.cfg.get("efeito_voz", "robo")
                    if style in VOZ_ESTILOS:
                        try:
                            path = robotize_mp3(path, style)
                        except Exception as e:
                            log.info("efeito robo indisponivel: %s", e)
                    self._file_ready.emit(rid, path)
                    return
            except Exception as e:
                log.info("edge-tts indisponivel, usando voz do Windows: %s", e)
        self._speak_offline(rid, text)

    def _speak_offline(self, rid, text):
        try:
            import pyttsx3
            eng = pyttsx3.init()
            for v in eng.getProperty("voices"):
                tag = (str(v.id) + " " + str(getattr(v, "name", ""))).lower()
                if "pt-br" in tag or "pt_br" in tag or "portug" in tag or "maria" in tag or "daniel" in tag:
                    eng.setProperty("voice", v.id)
                    break
            eng.setProperty("rate", 185)
            if rid != self.req:
                return
            self._fallback_state.emit(rid, True)
            eng.say(text)
            eng.runAndWait()
        except Exception as e:
            log.warning("sem voz offline: %s", e)
            self._fallback_state.emit(rid, True)
            time.sleep(min(8, 0.6 + len(text) * 0.055))
        self._fallback_state.emit(rid, False)

    def _on_fallback(self, rid, on):
        if rid != self.req:
            return
        self.pending = False
        self._set_talking(on)

    def _play_file(self, rid, path):
        if rid != self.req:
            return
        self.pending = False
        self.player.setSource(QUrl.fromLocalFile(path))
        self.player.play()

    def _on_state(self, st):
        self._set_talking(st == QMediaPlayer.PlaybackState.PlayingState)

    def _on_error(self, *a):
        log.warning("erro no player: %s", a)
        rid = self.req
        self.pending = True
        threading.Thread(target=self._speak_offline, args=(rid, self._last_text), daemon=True).start()


# ----------------------------------------------------------------------------
# Escuta (microfone -> texto)
# ----------------------------------------------------------------------------
class Listener(QObject):
    heard = Signal(str, bool)
    status = Signal(str)

    RATE, BLOCK = 16000, 480  # blocos de 30 ms

    def __init__(self, cfg, is_busy):
        super().__init__()
        self.cfg = cfg
        self.is_busy = is_busy
        self.force = False
        self.running = True
        self.stream = None
        self.ambient = 200.0
        self.threshold = 500.0
        self.ok = True
        self._last_net_err = 0
        threading.Thread(target=self._loop, daemon=True).start()

    @staticmethod
    def rms(data):
        a = array("h", data)
        if not a:
            return 0.0
        return math.sqrt(sum(x * x for x in a) / len(a))

    def _open(self):
        import sounddevice as sd
        self.stream = sd.RawInputStream(samplerate=self.RATE, channels=1, dtype="int16", blocksize=self.BLOCK)
        self.stream.start()
        vals = []
        for _ in range(20):
            data, _ = self.stream.read(self.BLOCK)
            vals.append(self.rms(bytes(data)))
        self.ambient = sum(vals) / len(vals)
        self.threshold = max(380.0, self.ambient * 3.0)

    def _close(self):
        if self.stream is not None:
            try:
                self.stream.stop(); self.stream.close()
            except Exception:
                pass
            self.stream = None

    def _capture(self, forced):
        pre = collections.deque(maxlen=10)
        start = time.monotonic()
        limit = 7.0 if forced else 1.5
        frames, speaking, silence, voiced = [], False, 0, 0
        while self.running:
            if self.is_busy():
                return None
            if not forced and self.force:
                return None  # usuario clicou: recomeca em modo forcado
            data, _ = self.stream.read(self.BLOCK)
            data = bytes(data)
            lvl = self.rms(data)
            if not speaking:
                if lvl > self.threshold:
                    speaking = True
                    frames = list(pre) + [data]
                    voiced = 1
                else:
                    pre.append(data)
                    self.ambient = self.ambient * 0.97 + lvl * 0.03
                    self.threshold = max(380.0, self.ambient * 3.0)
                    if time.monotonic() - start > limit:
                        return None
            else:
                frames.append(data)
                if lvl > self.threshold * 0.6:
                    silence = 0; voiced += 1
                else:
                    silence += 1
                if silence > 28 or len(frames) > 400:
                    break
        if voiced < 8:
            return None
        return b"".join(frames)

    def _loop(self):
        try:
            import speech_recognition as sr
            import sounddevice  # noqa: F401
        except Exception as e:
            log.warning("escuta indisponivel: %s", e)
            self.ok = False
            self.status.emit("sem_modulo")
            return
        rec = sr.Recognizer()
        while self.running:
            need = (self.force or self.cfg.get("escuta_continua")) and not getattr(self, "paused", False)
            if not need:
                self._close(); time.sleep(0.25); continue
            if self.is_busy():
                time.sleep(0.15); continue
            try:
                if self.stream is None:
                    self._open()
                forced = self.force
                audio = self._capture(forced)
            except Exception as e:
                log.warning("microfone: %s", e)
                self._close()
                if self.force:
                    self.force = False
                    self.status.emit("erro_mic")
                time.sleep(3); continue
            if audio is None:
                if forced and self.force and not self.is_busy():
                    self.force = False
                    self.status.emit("nada")
                continue
            if forced:
                self.status.emit("processando")
            try:
                text = rec.recognize_google(sr.AudioData(audio, self.RATE, 2), language="pt-BR")
            except sr.UnknownValueError:
                if forced:
                    self.force = False
                    self.status.emit("nada")
                continue
            except Exception as e:
                log.warning("reconhecimento: %s", e)
                if forced or time.time() - self._last_net_err > 300:
                    self._last_net_err = time.time()
                    self.force = False
                    self.status.emit("erro_rede")
                continue
            self.force = False
            if text:
                self.heard.emit(text, forced)


# ----------------------------------------------------------------------------
# Atualizacao automatica (pelo GitHub)
# ----------------------------------------------------------------------------
PROTEGIDOS = {"config.json", "robo_bravus.log"}


def vtuple(v):
    return tuple(int(x) for x in re.findall(r"\d+", str(v))[:3])


class Updater(QObject):
    done = Signal(str, str)   # status ("nova", "atual", "erro"), versao/mensagem

    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self.busy = False

    def check(self, manual=False):
        if self.busy:
            return
        self.busy = True
        threading.Thread(target=self._run, args=(manual,), daemon=True).start()

    def _get(self, rel):
        import urllib.request
        base = self.cfg.get("url_atualizacao", "").rstrip("/") + "/"
        req = urllib.request.Request(base + rel + f"?t={int(time.time())}",
                                     headers={"User-Agent": "RoboBravus", "Cache-Control": "no-cache"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read()

    def _run(self, manual):
        try:
            info = json.loads(self._get("versao.json").decode("utf-8"))
            nova = info.get("versao", "0")
            if vtuple(nova) <= vtuple(VERSAO):
                self.done.emit("atual", VERSAO)
                return
            files = [f for f in info.get("arquivos", []) if f not in PROTEGIDOS and ".." not in f]
            stage = os.path.join(tempfile.gettempdir(), "robo_bravus_update")
            os.makedirs(stage, exist_ok=True)
            got = {}
            for rel in files:
                data = self._get(rel)
                if not data:
                    raise RuntimeError("arquivo vazio: " + rel)
                got[rel] = data
            old_req = ""
            try:
                old_req = open(os.path.join(APP_DIR, "requirements.txt"), encoding="utf-8").read()
            except Exception:
                pass
            for rel, data in got.items():           # so substitui depois de baixar tudo
                dest = os.path.join(APP_DIR, *rel.split("/"))
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                tmp = dest + ".novo"
                with open(tmp, "wb") as f:
                    f.write(data)
                os.replace(tmp, dest)
            if "requirements.txt" in got and got["requirements.txt"].decode("utf-8", "ignore") != old_req:
                py = os.path.join(os.path.dirname(sys.executable), "python.exe")
                if not os.path.exists(py):
                    py = sys.executable
                subprocess.run([py, "-m", "pip", "install", "-q", "-r", os.path.join(APP_DIR, "requirements.txt")],
                               cwd=APP_DIR, creationflags=0x08000000 if sys.platform == "win32" else 0)
            log.info("atualizado para %s", nova)
            self.done.emit("nova", nova)
        except Exception as e:
            log.info("atualizacao: %s", e)
            self.done.emit("erro", str(e))
        finally:
            self.busy = False


# ----------------------------------------------------------------------------
# Atalhos: teclas globais e comandos vindos dos atalhos da Area de Trabalho
# ----------------------------------------------------------------------------
PORTA = 47851
TECLAS = {1: ("B", "alternar"), 2: ("F", "falar"), 3: ("M", "mudo")}  # Ctrl + Alt + tecla


class Control(QObject):
    command = Signal(str)

    def __init__(self, lock):
        super().__init__()
        self.lock = lock
        threading.Thread(target=self._server, daemon=True).start()
        if sys.platform == "win32":
            threading.Thread(target=self._hotkeys, daemon=True).start()

    def _server(self):
        try:
            self.lock.listen(4)
            while True:
                conn, _ = self.lock.accept()
                try:
                    cmd = conn.recv(64).decode("utf-8", "ignore").strip()
                finally:
                    conn.close()
                if cmd:
                    self.command.emit(cmd)
        except Exception as e:
            log.warning("servidor de comandos: %s", e)

    def _hotkeys(self):
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            mods = 0x0001 | 0x0002 | 0x4000  # ALT | CTRL | NOREPEAT
            for hid, (key, _) in TECLAS.items():
                if not user32.RegisterHotKey(None, hid, mods, ord(key)):
                    log.warning("tecla Ctrl+Alt+%s ja usada por outro programa", key)
            msg = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
                if msg.message == 0x0312 and msg.wParam in TECLAS:
                    self.command.emit(TECLAS[msg.wParam][1])
        except Exception as e:
            log.warning("teclas de atalho: %s", e)


def send_command(cmd):
    try:
        with socket.create_connection(("127.0.0.1", PORTA), timeout=2) as c:
            c.sendall(cmd.encode("utf-8"))
        return True
    except OSError:
        return False


# ----------------------------------------------------------------------------
# Desenho do robo
# ----------------------------------------------------------------------------
BLUE = QColor(30, 144, 255)
GLOW = QColor(0, 170, 255)
DARK = QColor(10, 14, 24)
WHITE = QColor(244, 247, 251)
EDGE = QColor(130, 141, 158)
P = QPointF


def lerp(a, b, k):
    return a + (b - a) * k


def lerp_p(a, b, k):
    return P(lerp(a.x(), b.x(), k), lerp(a.y(), b.y(), k))


def ik(shoulder, hand, l1, l2, side):
    dx, dy = hand.x() - shoulder.x(), hand.y() - shoulder.y()
    d = math.hypot(dx, dy)
    d = max(abs(l1 - l2) + 0.5, min(l1 + l2 - 0.2, d))
    a = math.atan2(dy, dx)
    hand = P(shoulder.x() + math.cos(a) * d, shoulder.y() + math.sin(a) * d) if d < math.hypot(dx, dy) else hand
    alpha = math.acos(max(-1, min(1, (l1 * l1 + d * d - l2 * l2) / (2 * l1 * d))))
    c1 = P(shoulder.x() + l1 * math.cos(a + alpha), shoulder.y() + l1 * math.sin(a + alpha))
    c2 = P(shoulder.x() + l1 * math.cos(a - alpha), shoulder.y() + l1 * math.sin(a - alpha))
    score = lambda c: c.y() + 0.6 * (c.x() - 100) * side
    elbow = c1 if score(c1) > score(c2) else c2
    return elbow, hand


class RobotModel:
    """Estado da animacao + desenho em coordenadas logicas (200 x 250)."""
    W, H = 200, 250

    def __init__(self):
        self.t = 0.0
        self.pose = "rest_float"
        self.expr = "neutral"
        self.talking = False
        self.mouth = 0.0
        self.listening = False
        self.blink = 0.0
        self.sit = 0.0
        self.look = P(0, 0)
        self.handL = P(63, 168)
        self.handR = P(137, 168)
        self.fx = set()  # cup, dots, question, zzz

    # ---------- poses ----------
    def targets(self):
        t, s = self.t, self.sit
        restL = lerp_p(P(60 + math.sin(t * 1.3) * 1.5, 173), P(80, 176), s)
        restR = lerp_p(P(140 - math.sin(t * 1.3) * 1.5, 173), P(120, 176), s)
        p = self.pose
        if p == "scratch":
            return restL, P(151 + math.sin(t * 15) * 3, 101 + math.cos(t * 15) * 3)
        if p == "think":
            return P(97, 151), P(108 + math.sin(t * 2) * 1, 121)
        if p == "wave":
            return restL, P(160 + math.sin(t * 9) * 7, 96)
        if p == "present":
            return P(46, 146 + math.sin(t * 3) * 2), P(154, 146 - math.sin(t * 3) * 2)
        if p == "water":
            k = (math.sin(t * 2.2) + 1) / 2
            return restL, lerp_p(P(150, 140), P(124, 116), k)
        if p == "listen":
            return restL, P(158, 97)
        if p == "talk":
            return (P(57 + math.sin(t * 3.1) * 5, 152 + math.cos(t * 2.3) * 6),
                    P(143 + math.cos(t * 2.7) * 5, 152 + math.sin(t * 2.1) * 6))
        if p == "point":
            return restL, P(172, 126)
        if p == "stretch":
            return P(62, 92 + math.sin(t * 4) * 3), P(138, 92 + math.cos(t * 4) * 3)
        return restL, restR

    def step(self, dt):
        self.t += dt
        tl, tr = self.targets()
        k = min(1.0, dt * 9)
        self.handL = lerp_p(self.handL, tl, k)
        self.handR = lerp_p(self.handR, tr, k)
        if self.talking:
            target = 0.25 + 0.75 * abs(math.sin(self.t * 17) * math.sin(self.t * 5.3 + 1))
        else:
            target = 0.0
        self.mouth = lerp(self.mouth, target, min(1.0, dt * 20))

    # ---------- helpers ----------
    @staticmethod
    def limb(p, a, b, w, color=WHITE, edge=EDGE):
        p.setPen(QPen(edge, w + 2, Qt.SolidLine, Qt.RoundCap)); p.drawLine(a, b)
        p.setPen(QPen(color, w, Qt.SolidLine, Qt.RoundCap)); p.drawLine(a, b)
        if color == WHITE:
            hl = QColor(255, 255, 255, 200)
            p.setPen(QPen(hl, max(1.0, w * 0.3), Qt.SolidLine, Qt.RoundCap))
            p.drawLine(P(a.x() - w * 0.18, a.y() - w * 0.12), P(b.x() - w * 0.18, b.y() - w * 0.12))

    @staticmethod
    def dot(p, c, r, color, edge=None):
        p.setPen(QPen(edge, 1.2) if edge else Qt.NoPen)
        p.setBrush(color)
        p.drawEllipse(c, r, r)

    @staticmethod
    def glow_path(p, path, color, fill=True, width=4.0, strength=1.0):
        c = QColor(color)
        for w, a in ((width + 9, 22), (width + 5, 40), (width + 2, 70)):
            c.setAlpha(int(a * strength))
            p.setPen(QPen(c, w, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.setBrush(Qt.NoBrush)
            p.drawPath(path)
        if fill:
            p.setPen(Qt.NoPen)
            g = QRadialGradient(path.boundingRect().center(), max(4, path.boundingRect().width()))
            g.setColorAt(0, QColor(150, 225, 255))
            g.setColorAt(0.6, QColor(40, 170, 255))
            g.setColorAt(1, QColor(0, 120, 230))
            p.setBrush(g)
            p.drawPath(path)
            # textura de LED
            p.save()
            p.setClipPath(path)
            p.setPen(QPen(QColor(0, 40, 90, 70), 0.8))
            r = path.boundingRect()
            x = r.left()
            while x < r.right():
                p.drawLine(P(x, r.top()), P(x, r.bottom())); x += 2.6
            y = r.top()
            while y < r.bottom():
                p.drawLine(P(r.left(), y), P(r.right(), y)); y += 2.6
            p.restore()
        else:
            c.setAlpha(255)
            p.setPen(QPen(c, width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.drawPath(path)

    # ---------- desenho ----------
    def draw(self, p, head_only=False):
        p.setRenderHint(QPainter.Antialiasing, True)
        t = self.t
        fy = math.sin(t * 1.6) * 4.0  # flutuacao

        if not head_only:
            # anel de luz embaixo
            k = 1.0 - (fy + 4) / 16
            ring = QRectF(100 - 52 * k, 234 - 8 * k, 104 * k, 16 * k)
            g = QRadialGradient(ring.center(), 52 * k)
            g.setColorAt(0, QColor(0, 170, 255, 120)); g.setColorAt(1, QColor(0, 170, 255, 0))
            p.setPen(Qt.NoPen); p.setBrush(g); p.drawEllipse(ring)
            pen_c = QColor(GLOW); pen_c.setAlpha(int(140 + 80 * math.sin(t * 3)))
            p.setPen(QPen(pen_c, 2.2)); p.setBrush(Qt.NoBrush)
            p.drawEllipse(ring.adjusted(14 * k, 3 * k, -14 * k, -3 * k))

        p.save()
        p.translate(0, fy)
        if not head_only:
            self.draw_legs(p)
            self.draw_body(p)
        self.draw_head(p)
        if not head_only:
            self.draw_arms(p)
            self.draw_fx(p)
        p.restore()

    def draw_legs(self, p):
        t, s = self.t, self.sit
        if s < 0.99:
            p.setOpacity(1 - s)
            for side in (-1, 1):
                sw = math.sin(t * 1.2 + side) * 2
                hip = P(100 + side * 11, 176)
                knee = P(100 + side * 13 + sw * 0.5, 195)
                foot = P(100 + side * 12 + sw, 211)
                self.limb(p, hip, knee, 13)
                self.dot(p, knee, 5, DARK)
                self.limb(p, knee, foot, 11)
                p.setPen(Qt.NoPen); p.setBrush(DARK)
                p.drawRoundedRect(QRectF(foot.x() - 9 + side * 2, foot.y() - 2, 18, 10), 5, 5)
        if s > 0.01:
            p.setOpacity(s)
            self.limb(p, P(110, 183), P(140, 196), 16)
            self.limb(p, P(90, 183), P(60, 196), 16)
            self.limb(p, P(62, 199), P(104, 208), 12)
            self.dot(p, P(62, 198), 6, DARK)
            self.limb(p, P(138, 199), P(96, 208), 12)
            self.dot(p, P(138, 198), 6, DARK)
            p.setPen(Qt.NoPen); p.setBrush(DARK)
            p.drawRoundedRect(QRectF(100, 202, 16, 11), 5, 5)
            p.drawRoundedRect(QRectF(84, 202, 16, 11), 5, 5)
        p.setOpacity(1)

    def draw_body(self, p):
        # pescoco e quadril
        p.setPen(Qt.NoPen); p.setBrush(DARK)
        p.drawRoundedRect(QRectF(90, 112, 20, 14), 4, 4)
        p.drawEllipse(QRectF(83, 165, 34, 20))
        # tronco
        path = QPainterPath(); path.addRoundedRect(QRectF(73, 121, 54, 56), 20, 20)
        g = QLinearGradient(73, 0, 127, 0)
        g.setColorAt(0, QColor(222, 228, 236)); g.setColorAt(0.35, QColor(255, 255, 255)); g.setColorAt(1, QColor(196, 205, 218))
        p.setPen(QPen(EDGE, 1.2)); p.setBrush(g); p.drawPath(path)
        # emblema oficial no peito: BRAVUS (A branco) + MIDIA, entre linhas azuis
        badge = QRectF(80, 135, 40, 24)
        p.setPen(Qt.NoPen); p.setBrush(QColor(8, 13, 24)); p.drawRoundedRect(badge, 5, 5)
        line = QColor(GLOW)
        for yy in (badge.top() + 4, badge.bottom() - 4):
            for w, a in ((2.6, 70), (1.0, 255)):
                line.setAlpha(a); p.setPen(QPen(line, w, Qt.SolidLine, Qt.RoundCap))
                p.drawLine(P(badge.left() + 5, yy), P(badge.right() - 5, yy))
        f = QFont("Arial"); f.setBold(True); f.setPixelSize(8)
        fm = QFontMetricsF(f)
        segs = [("BR", BLUE), ("A", WHITE), ("VUS", BLUE)]
        total = sum(fm.horizontalAdvance(s) for s, _ in segs)
        scale = min(1.0, 31 / total)
        p.save()
        p.translate(100, badge.top() + 13.2); p.scale(scale, scale)
        x = -total / 2
        p.setFont(f)
        for s, c in segs:
            p.setPen(c); p.drawText(P(x, 0), s); x += fm.horizontalAdvance(s)
        p.restore()
        f2 = QFont("Arial"); f2.setPixelSize(4); f2.setLetterSpacing(QFont.AbsoluteSpacing, 0.8)
        p.setFont(f2); p.setPen(QColor(200, 205, 212))
        w2 = QFontMetricsF(f2).horizontalAdvance("MÍDIA")
        p.drawText(P(100 - w2 / 2, badge.top() + 17.5), "MÍDIA")

    def draw_head(self, p):
        t = self.t
        # fones
        for side in (-1, 1):
            c = P(100 + side * 73, 70)
            self.dot(p, c, 17, QColor(22, 27, 38), QColor(60, 66, 80))
        # capacete
        head = QPainterPath(); head.addRoundedRect(QRectF(28, 6, 144, 114), 58, 54)
        g = QRadialGradient(P(78, 30), 150)
        g.setColorAt(0, QColor(255, 255, 255)); g.setColorAt(0.55, QColor(236, 240, 245)); g.setColorAt(1, QColor(176, 186, 200))
        p.setPen(QPen(EDGE, 1.3)); p.setBrush(g); p.drawPath(head)
        # brilho do capacete
        p.setPen(QPen(QColor(255, 255, 255, 230), 4, Qt.SolidLine, Qt.RoundCap))
        hl = QPainterPath(); hl.moveTo(52, 30); hl.quadTo(66, 14, 96, 12); p.drawPath(hl)
        # aneis dos fones (por cima)
        for side in (-1, 1):
            c = P(100 + side * 74, 70)
            ring = QPainterPath(); ring.addEllipse(c, 10, 10)
            strength = 1.4 if self.listening else 0.8 + 0.2 * math.sin(t * 2)
            self.glow_path(p, ring, GLOW, fill=False, width=3.0, strength=strength)
            self.dot(p, c, 6, QColor(18, 22, 32))
        # visor
        visor = QPainterPath(); visor.addRoundedRect(QRectF(42, 30, 116, 78), 34, 34)
        vg = QLinearGradient(0, 30, 0, 108)
        vg.setColorAt(0, QColor(26, 32, 46)); vg.setColorAt(0.5, QColor(6, 9, 16)); vg.setColorAt(1, QColor(14, 18, 28))
        p.setPen(QPen(QColor(40, 46, 60), 2)); p.setBrush(vg); p.drawPath(visor)
        p.setPen(QPen(QColor(255, 255, 255, 34), 3, Qt.SolidLine, Qt.RoundCap))
        gl = QPainterPath(); gl.moveTo(56, 48); gl.quadTo(62, 38, 78, 36); p.drawPath(gl)
        # olhos
        lx, ly = self.look.x(), self.look.y()
        e = self.expr
        for side in (-1, 1):
            cx, cy = 100 + side * 20 + lx, 67 + ly
            self.draw_eye(p, cx, cy, e, side)
        # boca
        if self.mouth > 0.03:
            w, h = 12 + self.mouth * 8, 2 + self.mouth * 8
            mp = QPainterPath(); mp.addRoundedRect(QRectF(100 + lx * 0.6 - w / 2, 92 + ly * 0.5 - h / 2, w, h), h / 2, h / 2)
            self.glow_path(p, mp, GLOW, fill=True, width=1.5, strength=0.8)
        elif e in ("happy", "excited"):
            sm = QPainterPath(); sm.moveTo(93 + lx * 0.6, 91); sm.quadTo(100 + lx * 0.6, 97, 107 + lx * 0.6, 91)
            self.glow_path(p, sm, GLOW, fill=False, width=2.2, strength=0.7)

    def draw_eye(self, p, cx, cy, e, side):
        path = QPainterPath()
        if e in ("happy", "excited") or (e == "wink" and side == 1):
            path.moveTo(cx - 10, cy + 5); path.quadTo(cx, cy - 11, cx + 10, cy + 5)
            self.glow_path(p, path, GLOW, fill=False, width=5.5, strength=1.2 if e == "excited" else 1.0)
            return
        if e == "sleep":
            path.moveTo(cx - 10, cy + 1); path.quadTo(cx, cy + 8, cx + 10, cy + 1)
            self.glow_path(p, path, GLOW, fill=False, width=3.5, strength=0.6)
            return
        if e == "think" and side == 1:
            path.moveTo(cx - 9, cy + 1); path.lineTo(cx + 9, cy - 3)
            self.glow_path(p, path, GLOW, fill=False, width=4.5)
            return
        if e == "focus":
            path.addRoundedRect(QRectF(cx - 11, cy - 4 + side * 0, 22, 9), 4, 4)
            self.glow_path(p, path, GLOW)
            return
        if e in ("surprised", "listen"):
            r = 12 + (math.sin(self.t * 5) * 1.2 if e == "listen" else 0)
            path.addEllipse(P(cx, cy), r, r)
            self.glow_path(p, path, GLOW)
            return
        h = max(2.5, 25 * (1 - self.blink))
        path.addRoundedRect(QRectF(cx - 9, cy - h / 2, 18, h), 8, min(8, h / 2))
        self.glow_path(p, path, GLOW)

    def draw_arms(self, p):
        for side, sh, hand in ((-1, P(72, 131), self.handL), (1, P(128, 131), self.handR)):
            elbow, hand = ik(sh, hand, 23, 23, side)
            sg = QRadialGradient(P(sh.x() - 3, sh.y() - 3), 12)
            sg.setColorAt(0, QColor(255, 255, 255)); sg.setColorAt(1, QColor(190, 199, 212))
            p.setPen(QPen(EDGE, 1.1)); p.setBrush(sg); p.drawEllipse(sh, 9.5, 9.5)
            self.limb(p, sh, elbow, 11)
            self.dot(p, elbow, 5, DARK)
            self.limb(p, elbow, hand, 10)
            if side == 1 and "cup" in self.fx:
                self.draw_cup(p, P(hand.x() - 2, hand.y() - 6))
            self.dot(p, hand, 6.5, QColor(28, 33, 45), QColor(60, 66, 80))
            self.dot(p, P(hand.x() - 1.2, hand.y() - 1.5), 3.2, WHITE)

    def draw_cup(self, p, c):
        glass = QPainterPath()
        glass.moveTo(c.x() - 7, c.y() - 10); glass.lineTo(c.x() + 7, c.y() - 10)
        glass.lineTo(c.x() + 5.5, c.y() + 8); glass.lineTo(c.x() - 5.5, c.y() + 8); glass.closeSubpath()
        p.setPen(QPen(QColor(255, 255, 255, 220), 1.4)); p.setBrush(QColor(200, 235, 255, 70)); p.drawPath(glass)
        water = QPainterPath()
        water.moveTo(c.x() - 6.2, c.y() - 2); water.lineTo(c.x() + 6.2, c.y() - 2)
        water.lineTo(c.x() + 5.5, c.y() + 8); water.lineTo(c.x() - 5.5, c.y() + 8); water.closeSubpath()
        p.setPen(Qt.NoPen); p.setBrush(QColor(41, 182, 255, 200)); p.drawPath(water)

    def draw_fx(self, p):
        t = self.t
        f = QFont("Arial"); f.setBold(True)
        if "dots" in self.fx:
            for i, (x, y, r) in enumerate(((148, 4, 3), (159, -8, 4.5), (172, -22, 6.5))):
                a = max(0.0, min(1.0, (t * 1.5 - i * 0.5) % 2.4))
                c = QColor(220, 235, 255, int(230 * a))
                p.setPen(QPen(QColor(GLOW.red(), GLOW.green(), GLOW.blue(), int(200 * a)), 1.2)); p.setBrush(c)
                p.drawEllipse(P(x, y), r, r)
        if "question" in self.fx:
            f.setPixelSize(22); p.setFont(f)
            c = QColor(GLOW); c.setAlpha(int(180 + 70 * math.sin(t * 4)))
            p.setPen(c); p.drawText(P(158, 2 + math.sin(t * 3) * 3), "?")
        if "zzz" in self.fx:
            for i in range(3):
                ph = (t * 0.45 + i / 3) % 1.0
                f.setPixelSize(int(9 + ph * 10)); p.setFont(f)
                p.setPen(QColor(150, 210, 255, int(255 * (1 - ph))))
                p.drawText(P(150 + ph * 22, 20 - ph * 40), "z")
        if self.listening:
            for i in range(3):
                ph = (t * 1.2 + i / 3) % 1.0
                c = QColor(GLOW); c.setAlpha(int(200 * (1 - ph)))
                p.setPen(QPen(c, 2, Qt.SolidLine, Qt.RoundCap)); p.setBrush(Qt.NoBrush)
                r = 8 + ph * 18
                p.drawArc(QRectF(184 - r, 70 - r, 2 * r, 2 * r), -45 * 16, 90 * 16)
                p.drawArc(QRectF(16 - r, 70 - r, 2 * r, 2 * r), 135 * 16, 90 * 16)


ASSETS = os.path.join(APP_DIR, "assets")


class SpriteRobot(RobotModel):
    """Robo realista (arte oficial) animado em camadas: corpo, cabeca e bracos."""
    W, H = 240, 292
    K = 0.4                      # escala da arte (600 px) -> coordenadas logicas
    HEAD_PIV, ARMR_PIV, ARML_PIV = P(300, 330), P(432, 385), P(198, 405)
    HAND_R = P(530, 300)
    EYES = ((P(232, 207), 3.15), (P(372, 198), 2.9))
    MOUTH = P(305, 262)
    HEAD_C = P(120, 80)          # centro da cabeca em coordenadas logicas

    _pix = None

    @classmethod
    def pixmaps(cls):
        if cls._pix is None:
            cls._pix = {n: QPixmap(os.path.join(ASSETS, n + ".png")) for n in ("body", "head", "armR", "armL")}
        return cls._pix

    def __init__(self):
        super().__init__()
        self.rh = self.ra = self.la = 0.0     # rotacao cabeca / braco dir / braco esq
        self.hdy = 0.0
        self.lift = 0.0

    def targets(self):
        t, p = self.t, self.pose
        sway = math.sin(t * 0.9)
        rest = (sway * 2.0, math.sin(t * 1.3) * 3, -math.sin(t * 1.3 + 0.7) * 3)
        table = {
            "scratch": (6 + math.sin(t * 3) * 1, -40 + math.sin(t * 14) * 6, 0),
            "think": (-9 + sway, math.sin(t * 1.3) * 2, 38 + math.sin(t * 2) * 2),
            "wave": (3 + sway, -6 + math.sin(t * 9) * 15, 0),
            "present": (math.sin(t * 2) * 3, math.sin(t * 3) * 7, -math.sin(t * 3) * 7),
            "talk": (math.sin(t * 2) * 3, math.sin(t * 2.7) * 8, math.sin(t * 3.1 + 1) * 8),
            "point": (4, 24, 0),
            "stretch": (-4 + math.sin(t * 4) * 2, -32, 32),
            "listen": (8, -42, 0),
            "water": (3, -22 + math.sin(t * 2.2) * 8, 0),
            "sleep": (11 + math.sin(t * 0.8) * 1.5, 22, -22),
        }
        return table.get(p, rest)

    def step(self, dt):
        self.t += dt
        h, r, l = self.targets()
        if self.expr == "sleep":
            h, r, l = 11 + math.sin(self.t * 0.8) * 1.5, 22, -22
        k = min(1.0, dt * 7)
        self.rh = lerp(self.rh, h, k); self.ra = lerp(self.ra, r, k); self.la = lerp(self.la, l, k)
        self.hdy = lerp(self.hdy, 4 if self.expr == "sleep" else 0, k)
        self.lift = lerp(self.lift, -self.sit * 8, min(1.0, dt * 3))
        target = 0.25 + 0.75 * abs(math.sin(self.t * 17) * math.sin(self.t * 5.3 + 1)) if self.talking else 0.0
        self.mouth = lerp(self.mouth, target, min(1.0, dt * 20))

    @staticmethod
    def part(p, pix, piv, ang, dy=0.0):
        p.save()
        p.translate(piv.x(), piv.y() + dy); p.rotate(ang); p.translate(-piv.x(), -piv.y())
        p.drawPixmap(0, 0, pix)
        p.restore()

    def draw(self, p, head_only=False):
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        t = self.t
        fy = math.sin(t * 1.6) * 7.0 - self.lift
        px = self.pixmaps()
        if not head_only:
            k = 0.85 - (fy + 7) / 40
            ring = QRectF(120 - 70 * k, 282 - 9 * k, 140 * k, 18 * k)
            g = QRadialGradient(ring.center(), 70 * k)
            g.setColorAt(0, QColor(0, 170, 255, 130)); g.setColorAt(1, QColor(0, 170, 255, 0))
            p.setPen(Qt.NoPen); p.setBrush(g); p.drawEllipse(ring)
            c = QColor(GLOW); c.setAlpha(int(160 + 70 * math.sin(t * 3)))
            for w, a in ((7, 50), (3.5, 110), (1.8, 255)):
                c2 = QColor(c); c2.setAlpha(int(c.alpha() * a / 255))
                p.setPen(QPen(c2, w)); p.setBrush(Qt.NoBrush)
                p.drawEllipse(ring.adjusted(22 * k, 4 * k, -22 * k, -4 * k))
        p.save()
        p.translate(0, fy)
        p.scale(self.K, self.K)
        if not head_only:
            self.part(p, px["armL"], self.ARML_PIV, self.la)
            self.part(p, px["body"], P(0, 0), 0)
        p.save()
        p.translate(self.HEAD_PIV.x(), self.HEAD_PIV.y() + self.hdy); p.rotate(self.rh)
        p.translate(-self.HEAD_PIV.x(), -self.HEAD_PIV.y())
        p.drawPixmap(0, 0, px["head"])
        lx, ly = self.look.x(), self.look.y()
        for side, (c, f) in zip((-1, 1), self.EYES):
            p.save(); p.translate(c.x() + lx * 3.0, c.y() + ly * 3.0); p.scale(f, f)
            self.draw_eye(p, 0, 0, self.expr, side)
            p.restore()
        p.save(); p.translate(self.MOUTH.x() + lx * 2, self.MOUTH.y() + ly * 2); p.scale(3.0, 3.0)
        if self.mouth > 0.03:
            w, h = 12 + self.mouth * 8, 2 + self.mouth * 8
            mp = QPainterPath(); mp.addRoundedRect(QRectF(-w / 2, -h / 2, w, h), h / 2, h / 2)
            self.glow_path(p, mp, GLOW, fill=True, width=1.5, strength=0.8)
        elif self.expr in ("happy", "excited"):
            sm = QPainterPath(); sm.moveTo(-7, -1); sm.quadTo(0, 5, 7, -1)
            self.glow_path(p, sm, GLOW, fill=False, width=2.2, strength=0.7)
        p.restore()
        if self.listening:
            for c in (P(68, 240), P(452, 200)):
                ring = QPainterPath(); ring.addEllipse(c, 30, 40)
                self.glow_path(p, ring, GLOW, fill=False, width=5, strength=1.3 if self.listening else 0.6)
        p.restore()
        if not head_only:
            # braco direito por cima (com copo d'agua)
            p.save()
            p.translate(self.ARMR_PIV.x(), self.ARMR_PIV.y()); p.rotate(self.ra)
            p.translate(-self.ARMR_PIV.x(), -self.ARMR_PIV.y())
            if "cup" in self.fx:
                p.save(); p.translate(self.HAND_R.x() + 5, self.HAND_R.y() - 30); p.scale(3.2, 3.2)
                self.draw_cup(p, P(0, 0)); p.restore()
            p.drawPixmap(0, 0, px["armR"])
            p.restore()
        p.restore()
        if not head_only:
            self.draw_fx_sprite(p)

    def draw_fx_sprite(self, p):
        t = self.t
        f = QFont("Arial"); f.setBold(True)
        if "dots" in self.fx:
            for i, (x, y, r) in enumerate(((196, 12, 3.5), (208, -2, 5), (222, -18, 7))):
                a = max(0.0, min(1.0, (t * 1.5 - i * 0.5) % 2.4))
                p.setPen(QPen(QColor(0, 170, 255, int(200 * a)), 1.2)); p.setBrush(QColor(225, 238, 255, int(230 * a)))
                p.drawEllipse(P(x, y), r, r)
        if "question" in self.fx:
            f.setPixelSize(26); p.setFont(f)
            c = QColor(GLOW); c.setAlpha(int(180 + 70 * math.sin(t * 4)))
            p.setPen(c); p.drawText(P(200, 6 + math.sin(t * 3) * 3), "?")
        if "zzz" in self.fx:
            for i in range(3):
                ph = (t * 0.45 + i / 3) % 1.0
                f.setPixelSize(int(10 + ph * 12)); p.setFont(f)
                p.setPen(QColor(150, 210, 255, int(255 * (1 - ph))))
                p.drawText(P(190 + ph * 26, 24 - ph * 44), "z")
        if self.listening:
            fy = math.sin(t * 1.6) * 7.0
            for i in range(3):
                ph = (t * 1.2 + i / 3) % 1.0
                c = QColor(GLOW); c.setAlpha(int(200 * (1 - ph)))
                p.setPen(QPen(c, 2, Qt.SolidLine, Qt.RoundCap)); p.setBrush(Qt.NoBrush)
                r = 8 + ph * 18
                p.drawArc(QRectF(196 - r, 80 + fy - r, 2 * r, 2 * r), -45 * 16, 90 * 16)
                p.drawArc(QRectF(12 - r, 96 + fy - r, 2 * r, 2 * r), 135 * 16, 90 * 16)


def render_icon(size=256):
    m = SpriteRobot()
    m.expr = "happy"
    img = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    sc = size / 196.0
    p.scale(sc, sc)
    p.translate(-6, 24)
    m.draw(p, head_only=True)
    p.end()
    return img


# ----------------------------------------------------------------------------
# Janela flutuante
# ----------------------------------------------------------------------------
class RobotWindow(QWidget):
    def __init__(self, cfg):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                         | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setWindowTitle("Robô Bravus")
        self.cfg = cfg
        self.nome = cfg["nome_usuario"]
        self.m = SpriteRobot()
        self.brain = Brain(cfg)
        self.ai = AIWorker(cfg)
        self.ai.answered.connect(self.on_ai)
        self.voice = Voice(cfg)
        self.voice.talking_changed.connect(self.on_talking)
        self.listener = Listener(cfg, self.voice.busy)
        self.listener.heard.connect(self.on_heard)
        self.listener.status.connect(self.on_listen_status)

        self.bubble_text, self.bubble_until, self.bubble_kind = "", 0.0, "say"
        self.action, self.action_until = None, 0.0
        self.expr_temp, self.expr_until = None, 0.0
        self.base_sit = False
        self.sleeping = False
        self.listening = False
        self.listen_after_speech = False
        self.look_target = None
        self.look_until = 0.0
        self.next_idle = 12.0
        self.next_blink = 2.0
        self.last_interaction = time.monotonic()
        self.drag_off, self.press_pos, self.dragged = None, None, False
        self.reminders = []

        self.apply_size()
        self.place()

        self._last = time.monotonic()
        self.tick_timer = QTimer(self); self.tick_timer.timeout.connect(self.tick); self.tick_timer.start(40)
        self.water_timer = QTimer(self); self.water_timer.timeout.connect(self.water_reminder)
        self.reset_water()
        self.clock = QTimer(self); self.clock.timeout.connect(self.each_minute); self.clock.start(60000)
        self.keep_top = QTimer(self); self.keep_top.timeout.connect(self.ensure_top); self.keep_top.start(4000)
        self.active = True
        self.updater = Updater(cfg)
        self.updater.done.connect(self.on_update)
        self._manual_update = False
        self.upd_timer = QTimer(self); self.upd_timer.timeout.connect(self.auto_update)
        self.upd_timer.start(3 * 3600 * 1000)
        QTimer.singleShot(45000, self.auto_update)

        self.menu = QMenu()
        self.menu.aboutToShow.connect(self.build_menu)
        self.tray = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(QIcon(QPixmap.fromImage(render_icon(64))), self)
            self.tray.setToolTip(f"Robô {cfg['nome_robo']} - Bravus Mídia")
            self.tray.setContextMenu(self.menu)
            self.tray.activated.connect(lambda r: r == QSystemTrayIcon.Trigger and self.set_active(not self.active))
            self.tray.show()

        QTimer.singleShot(1200, self.greet_start)

    # ---------- geometria ----------
    def apply_size(self):
        s = float(self.cfg.get("tamanho", 0.8))
        self.s = s
        self.Wd = int(max(300, SpriteRobot.W * s + 60))
        self.Hd = int(SpriteRobot.H * s + 150)
        old = self.geometry() if self.isVisible() else None
        self.setFixedSize(self.Wd, self.Hd)
        if old is not None:
            self.move(old.center().x() - self.Wd // 2, old.bottom() - self.Hd)

    def robot_origin(self):
        return (self.Wd - SpriteRobot.W * self.s) / 2, self.Hd - SpriteRobot.H * self.s

    def place(self):
        pos = self.cfg.get("posicao")
        if pos and QGuiApplication.screenAt(QRect(pos[0], pos[1], self.Wd, self.Hd).center()):
            self.move(pos[0], pos[1]); return
        g = QGuiApplication.primaryScreen().availableGeometry()
        self.move(g.right() - self.Wd - 10, g.bottom() - self.Hd + 5)

    def ensure_top(self):
        if not self.active:
            return
        if not self.isVisible():
            self.show()
        self.raise_()

    def show_again(self):
        self.show(); self.raise_()
        g = QGuiApplication.primaryScreen().availableGeometry()
        if not g.intersects(self.geometry()):
            self.move(g.right() - self.Wd - 10, g.bottom() - self.Hd + 5)

    # ---------- fala ----------
    def say(self, text, action=None, expr=None, speak=True, hold=None):
        self.last_interaction = time.monotonic()
        if self.sleeping and action != "sleep":
            self.sleeping = False
        self.bubble_text = text
        self.bubble_kind = "say"
        self.bubble_until = self.m.t + (hold or max(4.0, len(text) * 0.075))
        if action:
            self.do_action(action)
        if expr:
            self.set_expr(expr, 3.0)
        if speak:
            self.voice.say(text)
        log.info("robo: %s", text)

    def show_status(self, text, secs=3.0):
        self.bubble_text, self.bubble_kind = text, "status"
        self.bubble_until = self.m.t + secs

    def on_talking(self, v):
        self.m.talking = v
        if v:
            self.bubble_until = max(self.bubble_until, self.m.t + 1.5)
        else:
            self.bubble_until = min(self.bubble_until, self.m.t + 2.5) if self.bubble_kind == "say" else self.bubble_until
            if self.listen_after_speech:
                self.listen_after_speech = False
                QTimer.singleShot(400, self.start_listening)

    # ---------- acoes e expressoes ----------
    DUR = {"scratch": 4.0, "think": 5.0, "wave": 2.6, "present": 3.0, "water": 6.0,
           "point": 2.5, "stretch": 2.6, "happy": 2.5}

    def do_action(self, a):
        if a == "sit":
            self.base_sit = True; self.set_expr("happy", 1.5); return
        if a == "stand":
            self.base_sit = False; self.set_expr("happy", 1.5); return
        if a == "sleep":
            QTimer.singleShot(3500, self.go_sleep); return
        if a == "wake":
            self.sleeping = False; self.set_expr("excited", 2); return
        if a == "happy":
            self.set_expr("happy", 2.5); return
        self.action, self.action_until = a, self.m.t + self.DUR.get(a, 3.0)

    def go_sleep(self):
        self.sleeping = True
        self.base_sit = True

    def set_expr(self, e, secs):
        self.expr_temp, self.expr_until = e, self.m.t + secs

    # ---------- loop ----------
    def tick(self):
        now = time.monotonic()
        dt = min(0.1, now - self._last); self._last = now
        m = self.m
        t = m.t + dt
        if self.action and t > self.action_until:
            self.action = None
        if self.expr_temp and t > self.expr_until:
            self.expr_temp = None

        busy = m.talking or self.listening or self.action or self.sleeping
        if self.cfg.get("comportamentos_aleatorios", True) and not busy and t > self.next_idle:
            self.random_behavior()
        if t > self.next_idle + 120:
            self.next_idle = t + 10

        # pose
        if self.sleeping:
            pose = "sleep"
        elif self.listening:
            pose = "listen"
        elif self.action:
            pose = self.action
        elif m.talking:
            pose = "talk"
        else:
            pose = "rest_float"
        m.pose = pose
        sit_target = 1.0 if (self.base_sit or self.sleeping) else 0.0
        m.sit = lerp(m.sit, sit_target, min(1.0, dt * 3))

        # expressao
        if self.sleeping:
            e = "sleep"
        elif self.listening:
            e = "listen"
        elif self.expr_temp:
            e = self.expr_temp
        elif self.action in ("think",):
            e = "think"
        elif self.action == "scratch":
            e = "think"
        elif self.action in ("wave", "water", "stretch"):
            e = "happy"
        elif self.action == "present":
            e = "excited"
        else:
            e = "neutral"
        m.expr = e

        fx = set()
        if self.action == "water":
            fx.add("cup")
        if self.action == "think" or self.bubble_kind == "thinking":
            fx.add("dots")
        if self.action == "scratch":
            fx.add("question")
        if self.sleeping:
            fx.add("zzz")
        m.fx = fx
        m.listening = self.listening

        # piscar
        if t > self.next_blink:
            ph = (t - self.next_blink) / 0.16
            m.blink = math.sin(min(1.0, ph) * math.pi)
            if ph >= 1:
                m.blink = 0.0
                self.next_blink = t + random.uniform(2.0, 5.5)

        # olhar
        if self.sleeping or self.listening:
            lt = P(0, 0)
        elif self.action in ("think", "scratch"):
            lt = P(5, -5)
        elif self.look_target is not None and t < self.look_until:
            lt = self.look_target
        else:
            ox, oy = self.robot_origin()
            head = self.mapToGlobal(QPointF(ox + 120 * self.s, oy + 80 * self.s).toPoint())
            cur = QCursor.pos()
            dx, dy = cur.x() - head.x(), cur.y() - head.y()
            d = max(1.0, math.hypot(dx, dy))
            k = min(1.0, d / 250.0)
            lt = P(dx / d * 7 * k, dy / d * 5 * k)
        m.look = lerp_p(m.look, lt, min(1.0, dt * 6))

        m.step(dt)

        # lembretes personalizados
        for rem in list(self.reminders):
            if time.monotonic() >= rem[0]:
                self.reminders.remove(rem)
                self.say(f"{self.nome}, seu lembrete: {rem[1]}.", "point", "surprised")

        # dormir sozinho de madrugada
        h = datetime.datetime.now().hour
        if (not self.sleeping and not busy and (h >= 23 or h < 5)
                and time.monotonic() - self.last_interaction > 20 * 60):
            self.go_sleep()

        self.update()

    def random_behavior(self):
        t = self.m.t
        choice = random.choices(["sit", "scratch", "think", "look", "wave", "stretch"],
                                weights=[3, 3, 3, 2, 1, 1])[0]
        if choice == "sit":
            self.base_sit = not self.base_sit
        elif choice == "look":
            self.look_target = P(random.choice([-7, 7]), random.uniform(-3, 3))
            self.look_until = t + 2.5
        else:
            self.do_action(choice)
        self.next_idle = t + random.uniform(15, 45)

    # ---------- eventos de tempo ----------
    def reset_water(self):
        self.water_timer.stop()
        if self.cfg.get("lembrete_agua_ativo", True):
            self.water_timer.start(int(float(self.cfg.get("lembrete_agua_min", 30)) * 60000))

    def water_reminder(self):
        if not self.active:
            return
        self.sleeping = False
        msg = random.choice(AGUA).format(n=self.nome, m=int(self.cfg.get("lembrete_agua_min", 30)))
        self.say(msg, "water")
        if self.tray:
            self.tray.showMessage("Hora da água 💧", msg, QSystemTrayIcon.Information, 6000)

    def greet_start(self):
        now = datetime.datetime.now()
        saud = periodo(now.hour)
        robo = self.cfg["nome_robo"]
        if self.cfg.get("primeira_vez", True):
            msg = (f"{saud}, {self.nome}! Eu sou o {robo}, seu assistente da Bravus Mídia. "
                   f"Vou ficar aqui flutuando do seu lado. Pra falar comigo, clique em mim ou diga {robo}. "
                   f"E de {int(self.cfg.get('lembrete_agua_min', 30))} em {int(self.cfg.get('lembrete_agua_min', 30))} minutos eu te lembro de beber água!")
            self.cfg["primeira_vez"] = False
        elif saud == "Bom dia":
            msg = f"Bom dia, {self.nome}! Hoje é {DIAS[now.weekday()]}. {random.choice(MOTIVACAO)}"
        else:
            msg = f"{saud}, {self.nome}! Que bom te ver. Estou aqui se precisar."
        if saud == "Bom dia":
            self.cfg["ultima_saudacao"] = now.date().isoformat()
        save_config(self.cfg)
        self.say(msg, "wave")

    def each_minute(self):
        now = datetime.datetime.now()
        if 5 <= now.hour < 12 and self.cfg.get("ultima_saudacao") != now.date().isoformat():
            self.cfg["ultima_saudacao"] = now.date().isoformat(); save_config(self.cfg)
            self.sleeping = False
            self.say(f"Bom dia, {self.nome}! Hoje é {DIAS[now.weekday()]}. {random.choice(MOTIVACAO)}", "wave")

    # ---------- escuta ----------
    def start_listening(self):
        if not self.listener.ok:
            self.show_status("Microfone indisponível. Clique com o botão direito → Escrever mensagem.", 6)
            return
        self.voice.stop()
        self.sleeping = False
        self.listening = True
        self.last_interaction = time.monotonic()
        self.show_status(f"Estou ouvindo, {self.nome}...", 30)
        self.listener.force = True

    def stop_listening(self):
        self.listener.force = False
        self.listening = False
        self.bubble_until = 0

    def on_listen_status(self, st):
        msgs = {
            "nada": "Não consegui ouvir. Clique em mim e fale de novo.",
            "erro_mic": "Não encontrei o microfone. Use o botão direito → Escrever mensagem.",
            "erro_rede": "Estou sem internet pra entender sua voz agora.",
            "sem_modulo": "Escuta desativada (faltou instalar). Rode o INSTALAR.bat de novo.",
        }
        if st == "processando":
            self.bubble_kind = "thinking"
            self.show_status("Entendendo...", 15)
            self.bubble_kind = "thinking"
            return
        self.listening = False
        if st in msgs:
            self.show_status(msgs[st], 5)

    def on_heard(self, text, forced):
        log.info("ouviu (%s): %s", "clique" if forced else "continuo", text)
        if not forced:
            n = norm(text)
            hit = None
            for w in self.cfg.get("palavras_ativacao", []):
                mm = re.search(r"\b" + re.escape(norm(w)) + r"\b", n)
                if mm and (hit is None or mm.start() < hit.start()):
                    hit = mm
            if not hit:
                return
            rest = n[hit.end():].strip(" ,.!?")
            if len(rest) < 2:
                self.listen_after_speech = True
                self.say(f"Oi, {self.nome}! Pode falar.", expr="happy")
                return
            text = rest
        self.listening = False
        self.handle_text(text)

    # ---------- conversa ----------
    def handle_text(self, text):
        self.last_interaction = time.monotonic()
        self.sleeping = False
        res = self.brain.respond(text)
        if res is None:
            if self.ai.available():
                self.bubble_kind = "thinking"
                self.show_status("Hmm, deixa eu pensar...", 40)
                self.bubble_kind = "thinking"
                self.do_action("think")
                self.action_until = self.m.t + 40
                self.ai.ask(text)
            else:
                self.say(random.choice([
                    f"Ainda não sei responder isso, {self.nome}. Se colocar uma chave de IA nas configurações, eu fico bem mais esperto!",
                    f"Hmm, essa eu não sei, {self.nome}. Posso pesquisar no Google pra você, é só dizer: pesquisa e o assunto.",
                ]), "scratch")
            return
        if "reminder" in res:
            mins, what = res["reminder"]
            self.reminders.append((time.monotonic() + mins * 60, what))
        if res.get("reset_water"):
            self.reset_water()
        if "water" in res:
            self.cfg["lembrete_agua_ativo"] = res["water"]; save_config(self.cfg); self.reset_water()
        if "listen" in res:
            self.cfg["escuta_continua"] = res["listen"]; save_config(self.cfg)
        if res.get("mute") is True:
            self.say(res["reply"], res.get("action"))
            self.cfg["mudo"] = True; save_config(self.cfg)
        else:
            if res.get("mute") is False:
                self.cfg["mudo"] = False; save_config(self.cfg)
            self.say(res["reply"], res.get("action"))
        if res.get("open_url"):
            QTimer.singleShot(900, lambda u=res["open_url"]: webbrowser.open(u))

    def on_ai(self, text):
        self.action = None
        self.bubble_kind = "say"
        self.say(text, "talk" if len(text) > 80 else "present")

    def type_message(self):
        txt, ok = QInputDialog.getText(self, f"Robô {self.cfg['nome_robo']}",
                                       f"Escreva para o {self.cfg['nome_robo']}:")
        if ok and txt.strip():
            self.handle_text(txt.strip())

    # ---------- mouse ----------
    def robot_rect(self):
        ox, oy = self.robot_origin()
        return QRectF(ox + 10 * self.s, oy, 220 * self.s, 288 * self.s)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and self.robot_rect().contains(e.position()):
            self.press_pos = e.globalPosition().toPoint()
            self.drag_off = self.press_pos - self.frameGeometry().topLeft()
            self.dragged = False
        elif e.button() == Qt.RightButton:
            self.menu.popup(e.globalPosition().toPoint())

    def mouseMoveEvent(self, e):
        if self.drag_off is not None and e.buttons() & Qt.LeftButton:
            gp = e.globalPosition().toPoint()
            if (gp - self.press_pos).manhattanLength() > 5:
                self.dragged = True
            if self.dragged:
                self.move(gp - self.drag_off)

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.LeftButton or self.drag_off is None:
            return
        self.drag_off = None
        if self.dragged:
            self.cfg["posicao"] = [self.x(), self.y()]; save_config(self.cfg)
            self.set_expr("happy", 1.2)
            return
        if self.sleeping:
            self.sleeping = False
            self.say(f"Opa! Eu estava cochilando. Oi, {self.nome}!", "wave", "surprised")
        elif self.listening:
            self.stop_listening()
        else:
            self.start_listening()

    # ---------- menu ----------
    def build_menu(self):
        mn = self.menu
        mn.clear()
        robo = self.cfg["nome_robo"]

        def add(text, fn, checked=None, menu=mn):
            a = QAction(text, menu)
            if checked is not None:
                a.setCheckable(True); a.setChecked(bool(checked))
            a.triggered.connect(fn)
            menu.addAction(a)
            return a

        add(f"🎤  Falar com o {robo}", self.start_listening)
        add("⌨️  Escrever mensagem", self.type_message)
        mn.addSeparator()
        acts = mn.addMenu("🤖  Ações")
        for label, a in (("Sentar", "sit"), ("Levantar / flutuar", "stand"), ("Coçar a cabeça", "scratch"),
                         ("Pensar", "think"), ("Acenar", "wave"), ("Espreguiçar", "stretch"), ("Dormir", "sleep")):
            add(label, lambda _=False, a=a: (self.do_action(a), a != "sleep" and setattr(self, "sleeping", False)), menu=acts)
        add("Me lembrar de beber água agora", self.water_reminder, menu=acts)
        mn.addSeparator()
        add(f"💧  Lembrete de água ({int(self.cfg.get('lembrete_agua_min', 30))} min)", self.toggle_water,
            self.cfg.get("lembrete_agua_ativo", True))
        add(f"👂  Escuta contínua (diga \"{robo}\")", self.toggle_listen, self.cfg.get("escuta_continua"))
        vz = mn.addMenu("🔊  Voz")
        for label, v in (("Robô", "robo"), ("Robô metálico", "robo_metalico"), ("Natural", "normal")):
            add(label, lambda _=False, v=v: self.set_voice(v), self.cfg.get("efeito_voz", "robo") == v, menu=vz)
        add("🔇  Silenciar voz", self.toggle_mute, self.cfg.get("mudo"))
        add("🎲  Movimentos aleatórios", self.toggle_random, self.cfg.get("comportamentos_aleatorios", True))
        sz = mn.addMenu("📏  Tamanho")
        for label, v in (("Mini", 0.5), ("Pequeno", 0.65), ("Médio", 0.8), ("Grande", 1.0)):
            add(label, lambda _=False, v=v: self.set_size(v), abs(self.cfg.get("tamanho", 0.8) - v) < 0.01, menu=sz)
        if sys.platform == "win32":
            add("🚀  Iniciar com o Windows", self.toggle_autostart, os.path.exists(startup_path()))
        mn.addSeparator()
        add(f"🔄  Procurar atualização (v{VERSAO})", self.manual_update)
        add("⚙️  Abrir configurações", lambda: os.startfile(CONFIG_PATH) if sys.platform == "win32" else None)
        add("🙈  Desativar (Ctrl+Alt+B)", lambda: self.set_active(False))
        add("❌  Sair", self.quit_app)

    def toggle_water(self):
        self.cfg["lembrete_agua_ativo"] = not self.cfg.get("lembrete_agua_ativo", True)
        save_config(self.cfg); self.reset_water()
        self.show_status("Lembrete de água " + ("ligado." if self.cfg["lembrete_agua_ativo"] else "desligado."))

    def toggle_listen(self):
        self.cfg["escuta_continua"] = not self.cfg.get("escuta_continua")
        save_config(self.cfg)
        self.show_status(f"Agora é só dizer \"{self.cfg['nome_robo']}\" que eu respondo."
                         if self.cfg["escuta_continua"] else "Só vou ouvir quando você clicar em mim.", 4)

    def set_voice(self, v):
        self.cfg["efeito_voz"] = v; save_config(self.cfg)
        self.say({"robo": f"Voz de robô ativada, {self.nome}!",
                  "robo_metalico": f"Voz de robô metálico ativada, {self.nome}!",
                  "normal": f"Voz natural ativada, {self.nome}."}[v], "happy")

    def toggle_mute(self):
        self.cfg["mudo"] = not self.cfg.get("mudo"); save_config(self.cfg)
        if self.cfg["mudo"]:
            self.voice.stop()
        self.show_status("Voz desligada." if self.cfg["mudo"] else "Voz ligada.")

    def toggle_random(self):
        self.cfg["comportamentos_aleatorios"] = not self.cfg.get("comportamentos_aleatorios", True)
        save_config(self.cfg)

    def set_size(self, v):
        self.cfg["tamanho"] = v; self.apply_size()
        self.cfg["posicao"] = [self.x(), self.y()]; save_config(self.cfg)

    def toggle_autostart(self):
        if os.path.exists(startup_path()):
            os.remove(startup_path()); self.show_status("Não vou mais iniciar com o Windows.")
        else:
            make_autostart(); self.show_status("Pronto! Vou iniciar junto com o Windows.")

    def auto_update(self):
        if self.cfg.get("atualizacao_automatica", True):
            self._manual_update = False
            self.updater.check()

    def manual_update(self):
        self._manual_update = True
        self.show_status("Procurando atualização...", 20)
        self.updater.check(True)

    def on_update(self, st, info):
        manual = self._manual_update
        self._manual_update = False
        if st == "nova":
            self.say(f"{self.nome}, instalei uma atualização nova! Vou reiniciar rapidinho.", "present")
            QTimer.singleShot(5000, self.restart)
        elif manual and st == "atual":
            self.show_status(f"Já estou na versão mais nova ({info}).", 4)
        elif manual:
            self.show_status("Não consegui procurar atualização agora.", 4)

    def restart(self):
        self.cfg["posicao"] = [self.x(), self.y()]; save_config(self.cfg)
        flags = 0x00000008 | 0x00000200 if sys.platform == "win32" else 0
        subprocess.Popen([pythonw_exe(), os.path.abspath(__file__), "--reiniciar"], cwd=APP_DIR,
                         creationflags=flags)
        self.quit_app()

    def on_command(self, cmd):
        if cmd in ("alternar",):
            self.set_active(not self.active)
        elif cmd in ("mostrar", "ligar"):
            self.set_active(True)
        elif cmd == "desligar":
            self.set_active(False)
        elif cmd == "falar":
            self.set_active(True); self.start_listening()
        elif cmd == "mudo":
            self.toggle_mute()
        elif cmd == "sair":
            self.say(f"Até logo, {self.nome}!", "wave")
            QTimer.singleShot(2500, self.quit_app)

    def set_active(self, on):
        if on == self.active:
            if on:
                self.show_again()
            return
        self.active = on
        self.listener.paused = not on
        if on:
            self.show_again()
            self.reset_water()
            self.say(f"Voltei, {self.nome}!", "wave")
        else:
            self.voice.stop()
            self.stop_listening()
            self.water_timer.stop()
            self.hide()
            if self.tray:
                self.tray.showMessage("Robô Bravus", "Robô desativado. Ctrl+Alt+B para ativar de novo.",
                                      QSystemTrayIcon.Information, 3000)

    def quit_app(self):
        self.listener.running = False
        self.voice.stop()
        self.cfg["posicao"] = [self.x(), self.y()]; save_config(self.cfg)
        if self.tray:
            self.tray.hide()
        QApplication.quit()

    # ---------- pintura ----------
    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        ox, oy = self.robot_origin()
        p.save()
        p.translate(ox, oy); p.scale(self.s, self.s)
        self.m.draw(p)
        p.restore()
        if self.bubble_text and self.m.t < self.bubble_until:
            fade = min(1.0, (self.bubble_until - self.m.t) / 0.4)
            fy = math.sin(self.m.t * 1.6) * 7.0 * self.s
            self.draw_bubble(p, self.bubble_text, ox + 120 * self.s, oy + 8 * self.s + fy, fade)
        p.end()

    def draw_bubble(self, p, text, ax, bottom, alpha):
        avail_h = bottom - 16
        maxw = self.Wd - 16
        px = 13
        while True:
            f = QFont("Segoe UI"); f.setPixelSize(px); f.setWeight(QFont.DemiBold)
            fm = QFontMetrics(f)
            br = fm.boundingRect(QRect(0, 0, int(maxw - 24), 2000), Qt.TextWordWrap, text)
            if br.height() + 20 <= avail_h or px <= 10:
                break
            px -= 1
        while br.height() + 20 > avail_h and len(text) > 20:
            text = text[: int(len(text) * 0.85)].rsplit(" ", 1)[0] + "…"
            br = fm.boundingRect(QRect(0, 0, int(maxw - 24), 2000), Qt.TextWordWrap, text)
        bw, bh = br.width() + 26, br.height() + 18
        x = max(6, min(self.Wd - bw - 6, ax - bw / 2))
        y = bottom - bh - 10
        path = QPainterPath(); path.addRoundedRect(QRectF(x, y, bw, bh), 12, 12)
        tail = QPainterPath()
        tx = max(x + 16, min(x + bw - 16, ax))
        tail.moveTo(tx - 8, y + bh - 1); tail.lineTo(tx + 8, y + bh - 1); tail.lineTo(tx + 2, y + bh + 9); tail.closeSubpath()
        path = path.united(tail)
        p.setOpacity(alpha)
        glow = QColor(GLOW); glow.setAlpha(60)
        p.setPen(QPen(glow, 5)); p.setBrush(Qt.NoBrush); p.drawPath(path)
        p.setPen(QPen(BLUE, 1.6)); p.setBrush(QColor(9, 14, 28, 238)); p.drawPath(path)
        p.setFont(f)
        p.setPen(QColor(150, 210, 255) if self.bubble_kind != "say" else QColor(245, 248, 252))
        p.drawText(QRectF(x + 13, y + 9, bw - 26, bh - 18), Qt.TextWordWrap | Qt.AlignLeft | Qt.AlignVCenter, text)
        p.setOpacity(1)


# ----------------------------------------------------------------------------
# Instalacao (atalhos do Windows)
# ----------------------------------------------------------------------------
def pythonw_exe():
    d = os.path.dirname(sys.executable)
    w = os.path.join(d, "pythonw.exe")
    return w if os.path.exists(w) else sys.executable


def startup_path():
    return os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Start Menu",
                        "Programs", "Startup", "Robo Bravus.vbs")


def make_autostart():
    script = os.path.abspath(__file__)
    vbs = ('Set s = CreateObject("WScript.Shell")\r\n'
           f's.CurrentDirectory = "{APP_DIR}"\r\n'
           f's.Run """{pythonw_exe()}"" ""{script}""", 0, False\r\n')
    with open(startup_path(), "w", encoding="mbcs" if sys.platform == "win32" else "utf-8") as f:
        f.write(vbs)


def make_shortcut():
    script = os.path.abspath(__file__)
    q = lambda s: s.replace("'", "''")
    ps = "$d=[Environment]::GetFolderPath('Desktop');$w=New-Object -ComObject WScript.Shell;"
    ps += "Remove-Item -ErrorAction SilentlyContinue ($d+'\\Robo Bravus.lnk');"
    for nome, arg, desc in (("Ligar Robo Bravus", "", "Liga o Robo Bravus"),
                            ("Desligar Robo Bravus", " --sair", "Desliga o Robo Bravus")):
        ps += (f"$s=$w.CreateShortcut($d+'\\{nome}.lnk');"
               f"$s.TargetPath='{q(pythonw_exe())}';"
               f"$s.Arguments='\"{q(script)}\"{arg}';"
               f"$s.WorkingDirectory='{q(APP_DIR)}';"
               f"$s.IconLocation='{q(ICON_PATH)}';"
               f"$s.Description='{desc}';$s.Save();")
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps], check=False)


def install(autostart):
    app = QGuiApplication(sys.argv)  # noqa: F841
    render_icon(256).save(ICON_PATH, "ICO")
    print("  - Icone criado")
    if sys.platform == "win32":
        make_shortcut(); print("  - Atalhos 'Ligar Robo Bravus' e 'Desligar Robo Bravus' criados na Area de Trabalho")
        if autostart:
            make_autostart(); print("  - Robo vai iniciar junto com o Windows")
        flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        subprocess.Popen([pythonw_exe(), os.path.abspath(__file__)], cwd=APP_DIR, creationflags=flags)
        print("  - Robo iniciado!")


# ----------------------------------------------------------------------------
def main():
    if "--instalar" in sys.argv:
        install("--autostart" in sys.argv)
        return
    if "--sair" in sys.argv:
        send_command("sair")
        return
    # instancia unica: se ja estiver aberto, so mostra o robo
    lock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tries = 40 if "--reiniciar" in sys.argv else 1   # apos atualizar, espera a versao antiga fechar
    for i in range(tries):
        try:
            lock.bind(("127.0.0.1", PORTA))
            break
        except OSError:
            if i == tries - 1:
                send_command("mostrar")
                return
            time.sleep(0.25)
    if hasattr(Qt, "HighDpiScaleFactorRoundingPolicy"):
        QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(QIcon(QPixmap.fromImage(render_icon(64))))
    cfg = load_config()
    save_config(cfg)
    w = RobotWindow(cfg)
    w.show()
    w._lock = lock
    w._control = Control(lock)
    w._control.command.connect(w.on_command)
    sys.exit(app.exec())


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log.exception("erro fatal")
        raise
