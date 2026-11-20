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

VERSAO = "1.6.0"
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
    "palavras_ativacao": ["bravus", "bravos", "bravo", "brabus", "bravis", "bravu", "robo", "robozinho"],
    "microfone": None,
    "voz": "pt-BR-AntonioNeural",
    "voz_velocidade": "+4%",
    "voz_tom": "+28Hz",
    "efeito_voz": "menino",
    "mudo": False,
    "comportamentos_aleatorios": True,
    "ia_chave_anthropic": "",
    "ia_modelo": "claude-haiku-5-5",
    "ia_chave_gemini": "",
    "ia_modelo_gemini": "gemini-flash-lite-latest",
    "atualizacao_automatica": True,
    "url_atualizacao": "https://raw.githubusercontent.com/bravusmidia/robo-bravus/main/",
    "fuso_horario": -3,
    "relogio_fixo": False,
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
    load_config.cache = cfg
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


# Relogio: hora real puxada da internet (corrige o relogio do PC se estiver errado)
_RELOGIO = {"offset": 0.0, "sync": False}


def sync_relogio():
    """Pega a hora certa do servidor do Google (cabecalho Date) e guarda a diferenca para o relogio do PC."""
    import email.utils, urllib.request
    for url in ("https://www.google.com", "https://www.cloudflare.com", "http://www.google.com"):
        try:
            t0 = time.time()
            try:
                req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "RoboBravus"})
                with urllib.request.urlopen(req, timeout=8) as r:
                    d = r.headers.get("Date")
            except Exception:
                curl = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "curl.exe")
                if not os.path.exists(curl):
                    raise
                out = subprocess.run([curl, "-sI", "-m", "8", url], capture_output=True, text=True,
                                     creationflags=0x08000000).stdout
                d = next((l.split(":", 1)[1].strip() for l in out.splitlines() if l.lower().startswith("date:")), None)
            if not d:
                continue
            real = email.utils.parsedate_to_datetime(d).timestamp() + (time.time() - t0) / 2
            _RELOGIO["offset"] = real - time.time()
            _RELOGIO["sync"] = True
            log.info("relogio sincronizado pela internet (diferenca do PC: %.0f s)", _RELOGIO["offset"])
            return True
        except Exception as e:
            log.info("relogio %s: %s", url, e)
    return False


def agora():
    """Hora oficial do robo: hora da internet no fuso de Fortaleza/Brasilia (UTC-3)."""
    fuso = float(load_config.cache.get("fuso_horario", -3)) if hasattr(load_config, "cache") else -3.0
    tz = datetime.timezone(datetime.timedelta(hours=fuso))
    return datetime.datetime.fromtimestamp(time.time() + _RELOGIO["offset"], tz).replace(tzinfo=None)


def periodo(h=None):
    h = agora().hour if h is None else h
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

PROGRAMAS = [  # (palavras faladas, comando do Windows)
    (("bloco de notas", "notepad"), "notepad"),
    (("calculadora",), "calc"),
    (("explorador de arquivos", "meus arquivos", "explorador"), "explorer"),
    (("paint",), "mspaint"),
    (("configuracoes", "configuracao do windows"), "ms-settings:"),
    (("gerenciador de tarefas",), "taskmgr"),
    (("prompt de comando", "cmd"), "cmd"),
    (("chrome", "google chrome", "navegador"), "chrome"),
    (("edge",), "msedge"),
    (("firefox",), "firefox"),
    (("word",), "winword"),
    (("excel",), "excel"),
    (("powerpoint",), "powerpnt"),
    (("spotify",), "spotify:"),
    (("vs code", "visual studio code", "vscode"), "code"),
    (("camera",), "microsoft.windows.camera:"),
    (("ferramenta de captura", "recorte"), "ms-screenclip:"),
    (("lixeira",), "shell:RecycleBinFolder"),
]
PASTAS = [
    (("downloads", "download"), "Downloads"),
    (("documentos",), "Documents"),
    (("area de trabalho", "desktop"), "Desktop"),
    (("imagens", "fotos"), "Pictures"),
    (("musicas",), "Music"),
    (("videos",), "Videos"),
]
TECLAS_PC = [  # (palavras, teclas, resposta)
    (("nova aba", "abre uma aba", "abrir aba"), ["ctrl", "t"], "Nova aba aberta."),
    (("fecha a aba", "fechar aba", "fecha essa aba", "fecha aba"), ["ctrl", "w"], "Aba fechada."),
    (("proxima aba",), ["ctrl", "tab"], "Próxima aba."),
    (("aba anterior",), ["ctrl", "shift", "tab"], "Aba anterior."),
    (("reabre a aba", "reabrir aba"), ["ctrl", "shift", "t"], "Reabri a última aba."),
    (("volta a pagina", "voltar pagina", "pagina anterior", "volta pagina"), ["alt", "left"], "Voltando."),
    (("avanca a pagina", "proxima pagina", "avancar pagina"), ["alt", "right"], "Avançando."),
    (("atualiza a pagina", "recarrega", "atualizar pagina"), ["f5"], "Atualizando a página."),
    (("rola para baixo", "rola pra baixo", "desce a pagina", "desce"), ["pagedown"], None),
    (("rola para cima", "rola pra cima", "sobe a pagina", "sobe"), ["pageup"], None),
    (("tela cheia",), ["f11"], "Tela cheia."),
    (("aumenta o zoom", "mais zoom"), ["ctrl", "="], None),
    (("diminui o zoom", "menos zoom"), ["ctrl", "-"], None),
    (("minimiza tudo", "mostra a area de trabalho", "minimizar tudo"), ["win", "d"], "Pronto, área de trabalho."),
    (("fecha a janela", "fecha o programa", "fecha essa janela", "fechar janela"), ["alt", "f4"], "Fechando a janela."),
    (("troca de janela", "proxima janela", "muda de janela"), ["alt", "tab"], None),
    (("print", "captura de tela", "tira um print", "printa a tela"), ["win", "shift", "s"], "Selecione a área do print."),
    (("pausa a musica", "pausa o video", "pausar", "despausa", "continua a musica", "play"), ["playpause"], None),
    (("proxima musica", "pula a musica", "proxima faixa"), ["nexttrack"], None),
    (("musica anterior", "faixa anterior"), ["prevtrack"], None),
    (("salva o arquivo", "salvar arquivo", "salva isso"), ["ctrl", "s"], "Salvo."),
    (("copia isso", "copiar"), ["ctrl", "c"], "Copiado."),
    (("cola aqui", "colar", "cola isso"), ["ctrl", "v"], "Colado."),
    (("desfaz", "desfazer"), ["ctrl", "z"], "Desfeito."),
    (("seleciona tudo", "selecionar tudo"), ["ctrl", "a"], None),
]

VK = {"ctrl": 0x11, "shift": 0x10, "alt": 0x12, "win": 0x5B, "tab": 0x09, "left": 0x25, "right": 0x27,
      "f4": 0x73, "f5": 0x74, "f11": 0x7A, "pagedown": 0x22, "pageup": 0x21, "=": 0xBB, "-": 0xBD,
      "playpause": 0xB3, "nexttrack": 0xB0, "prevtrack": 0xB1, "volup": 0xAF, "voldown": 0xAE,
      "mute": 0xAD, "enter": 0x0D}
EXT = {"left", "right", "pagedown", "pageup", "win", "playpause", "nexttrack", "prevtrack", "volup", "voldown", "mute"}


def pc_keys(keys, times=1):
    """Aperta uma combinacao de teclas no Windows (vai para a janela que estiver na frente)."""
    if sys.platform != "win32":
        log.info("teclas %s (so no Windows)", keys); return
    import ctypes
    u = ctypes.windll.user32
    codes = [(VK[k] if k in VK else ord(k.upper()), k in EXT) for k in keys]
    for _ in range(times):
        for c, e in codes:
            u.keybd_event(c, 0, 1 if e else 0, 0)
        for c, e in reversed(codes):
            u.keybd_event(c, 0, (1 if e else 0) | 2, 0)
        time.sleep(0.03)


def pc_open(target):
    if sys.platform != "win32":
        log.info("abrir %s (so no Windows)", target); return
    try:
        os.startfile(target)
    except Exception:
        subprocess.Popen(["cmd", "/c", "start", "", target], creationflags=0x08000000)


def pc_folder(name):
    pc_open(os.path.join(os.path.expanduser("~"), name))


def pc_type(text):
    """Escreve o texto na janela da frente (usa a area de transferencia para aceitar acentos)."""
    QApplication.clipboard().setText(text)
    QTimer.singleShot(150, lambda: pc_keys(["ctrl", "v"]))


def pc_lock():
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.user32.LockWorkStation()


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
        now = agora()

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
        if has("que horas", "que hora", "horas sao", "hora e agora", "hora", "horas", "relogio", "mostra a hora"):
            return r(f"Agora são {now.hour} horas e {now.minute:02d} minutos, {nome}.", "clock", clock=True)
        if has("que dia", "data de hoje", "dia e hoje", "que data"):
            return r(f"Hoje é {DIAS[now.weekday()]}, {now.day} de {MESES[now.month - 1]} de {now.year}, {nome}.", "clock", clock=True)

        # Atualizar o proprio robo por voz
        if (has("se atualiza", "se atualizar", "atualiza voce", "atualize voce", "atualiza o robo", "atualizar o robo",
                "procura atualizacao", "procurar atualizacao", "busca atualizacao", "tem atualizacao",
                "nova versao", "atualiza ai", "atualize se", "atualize-se", "se atualize")
                and "pagina" not in n):
            return r(f"Certo, {nome}! Vou procurar uma versão nova agora.", "think", update=True)
        if has("qual sua versao", "qual a sua versao", "que versao", "versao voce"):
            return r(f"Estou na versão {VERSAO}, {nome}.", "present")
        # Confirmacoes pendentes (ex.: desligar o PC)
        # ---- Comandos no computador ----
        abrir = has("abre", "abrir", "abra", "abri", "entra no", "entrar no", "inicia", "executa")
        if abrir:
            for key, url in SITES:
                if key in n and key not in ("google", "drive") or (key in ("google", "drive") and re.search(r"\b" + key + r"\b", n)):
                    if key == "google" and "chrome" in n:
                        continue
                    return r(f"Abrindo {key}, {nome}.", "point", open_url=url)
            for words, cmd in PROGRAMAS:
                if any(w in n for w in words):
                    return r(f"Abrindo {words[0]}, {nome}.", "point", pc=("open", cmd))
            if "pasta" in n:
                for words, pasta in PASTAS:
                    if any(w in n for w in words):
                        return r(f"Abrindo a pasta {words[0]}.", "point", pc=("folder", pasta))
            m = re.search(r"\bsite (?:do |da |de )?([\w\.-]+)", n) or re.search(r"\b([\w-]+\.(?:com|com\.br|net|org|br|io|ai)(?:\.br)?)\b", n)
            if m:
                dom = m.group(1).strip(".")
                if "." not in dom:
                    dom += ".com.br"
                return r(f"Abrindo {dom}, {nome}.", "point", open_url="https://" + dom)
        for words, pasta in PASTAS:
            if any(("pasta " + w) in n or ("pasta de " + w) in n for w in words):
                return r(f"Abrindo a pasta {words[0]}.", "point", pc=("folder", pasta))
        m = re.search(r"^(?:digita|digite|escreve|escreva|escrever)(?: ai| aí| isso)?:? (.+)$", text.strip(), re.I)
        if m:
            return r("Escrevendo.", None, pc=("type", m.group(1)), quiet=True)
        if has("aumenta o volume", "aumentar o volume", "sobe o volume", "mais volume", "volume mais alto"):
            return r("Volume aumentado.", None, pc=("keys", ["volup"], 5))
        if has("diminui o volume", "diminuir o volume", "abaixa o volume", "baixa o volume", "menos volume"):
            return r("Volume diminuído.", None, pc=("keys", ["voldown"], 5))
        if has("tira o som", "muta o som", "silencia o computador", "volta o som"):
            return r("Pronto.", None, pc=("keys", ["mute"], 1))
        if has("bloqueia o computador", "bloquear o computador", "bloqueia o pc", "bloqueia a tela"):
            return r(f"Bloqueando o computador. Até já, {nome}!", "wave", pc=("lock",))
        if has("desliga o computador", "desligar o computador", "desliga o pc", "desligar o pc"):
            return r(f"Tem certeza que quer desligar o computador, {nome}? Diga: sim, pode desligar.", "think",
                     confirm=("shutdown",))
        if has("reinicia o computador", "reiniciar o computador", "reinicia o pc"):
            return r(f"Tem certeza que quer reiniciar o computador, {nome}? Diga: sim, pode reiniciar.", "think",
                     confirm=("restart",))
        if has("cancela o desligamento", "nao desliga", "cancelar desligamento"):
            return r("Cancelado! O computador não vai desligar.", "happy", pc=("cancel_shutdown",))
        for words, keys, resp in TECLAS_PC:
            if any(re.search(r"\b" + re.escape(w) + r"\b", n) for w in words):
                return r(resp or "Ok.", None, pc=("keys", keys, 1), quiet=resp is None)

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
            return r(random.choice(PIADAS), "happy", chat=True)
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
            return r(" ".join(parts), act, chat=True)

        if has("estou bem", "to bem", "tudo otimo", "tudo tranquilo"):
            return r(f"Que bom, {nome}! Fico feliz em saber.", "happy", chat=True)
        if has("quem e voce", "seu nome", "como voce se chama", "quem te criou", "o que voce e"):
            return r(f"Eu sou o {robo}, o assistente da Bravus Mídia. Fui criado pra ajudar você, {nome}, todos os dias.", "present", chat=True)
        if has("o que voce faz", "o que voce sabe", "ajuda", "comandos"):
            return r(f"Eu te lembro de beber água, digo as horas, abro sites, pesquiso no Google, "
                     f"crio lembretes e converso com você, {nome}. É só me chamar de {robo}.", "present")
        if has("obrigado", "obrigada", "valeu", "agradeco"):
            return r(f"Por nada, {nome}! Sempre às ordens.", "happy", chat=True)
        if has("tchau", "ate logo", "ate mais", "falou"):
            return r(f"Até logo, {nome}! Eu fico aqui se precisar.", "wave", chat=True)
        if has("te amo", "gosto de voce", "voce e legal", "voce e demais"):
            return r(f"Que gentileza, {nome}! Também gosto muito de trabalhar com você.", "happy", chat=True)
        if has("bravus midia", "minha agencia", "a agencia"):
            return r(f"A Bravus Mídia trabalha com tráfego pago, sites, landing pages, automações e mentoria. "
                     f"E vai escalar muito, {nome}!", "present")
        return None


# ----------------------------------------------------------------------------
# IA opcional (Claude)
# ----------------------------------------------------------------------------
def http_json(url, body=None, headers=None, timeout=40):
    """GET/POST JSON. Se o Python nao conseguir (certificados antigos), usa o curl do Windows."""
    import urllib.request, urllib.error
    headers = dict(headers or {})
    data = json.dumps(body).encode("utf-8") if body is not None else None
    if data is not None:
        headers["content-type"] = "application/json"
    try:
        req = urllib.request.Request(url, data=data, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read().decode('utf-8', 'ignore')[:300]}")
    except Exception as e:
        curl = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "curl.exe")
        if sys.platform != "win32" or not os.path.exists(curl):
            raise
        log.info("python sem acesso (%s); usando curl", e)
        cmd = [curl, "-sS", "-m", str(timeout), url]
        for k, v in headers.items():
            cmd += ["-H", f"{k}: {v}"]
        if data is not None:
            cmd += ["--data-binary", "@-"]
        r = subprocess.run(cmd, input=data, capture_output=True, timeout=timeout + 10, creationflags=0x08000000)
        if r.returncode != 0:
            raise RuntimeError(r.stderr.decode("utf-8", "ignore")[-300:])
        out = json.loads(r.stdout.decode("utf-8"))
        if isinstance(out, dict) and "error" in out and not out.get("candidates") and not out.get("content"):
            raise RuntimeError(str(out["error"])[:300])
        return out


class AIWorker(QObject):
    """Cerebro de IA: Gemini (Google, tem plano gratis) ou Claude (Anthropic, pago por uso)."""
    answered = Signal(str)

    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self.history = []   # [(pergunta, resposta)]

    def provider(self):
        if self.cfg.get("ia_chave_gemini", "").strip():
            return "gemini"
        if self.cfg.get("ia_chave_anthropic", "").strip():
            return "anthropic"
        return None

    def available(self):
        return self.provider() is not None

    def ask(self, text):
        threading.Thread(target=self._run, args=(text,), daemon=True).start()

    def system_prompt(self):
        nome, robo = self.cfg["nome_usuario"], self.cfg["nome_robo"]
        agr = agora()
        return (f"Você é o {robo}, um robozinho assistente com jeito de menino, simpático e educado, que flutua "
                f"na tela do computador de {nome}, CEO da agência Bravus Mídia (marketing digital, tráfego pago, "
                f"sites, landing pages, automações e mentoria). Hoje é {DIAS[agr.weekday()]}, "
                f"{agr.day}/{agr.month}/{agr.year}, {agr.hour}h{agr.minute:02d}. "
                f"Responda a qualquer pergunta, sobre qualquer assunto, sempre em português do Brasil, e chame-o de {nome}. "
                f"Seja direto: no máximo 3 frases curtas, porque a resposta será falada em voz alta. "
                f"Não use emojis, listas, asteriscos nem markdown. "
                f"Você controla o navegador do computador: se ele pedir para abrir, mostrar, tocar ou procurar algo na internet, "
                f"responda curto e coloque no final UMA destas marcações: [SITE:https://endereco] para abrir um site, "
                f"[PESQUISAR:termo] para pesquisar no Google ou [YOUTUBE:termo] para procurar no YouTube.")

    # modos para responder rapido (sem "pensar" demais); o primeiro que o modelo aceitar fica salvo
    RAPIDO = [{"thinkingConfig": {"thinkingBudget": 0}}, {"thinkingConfig": {"thinkingLevel": "minimal"}},
              {"thinkingConfig": {"thinkingLevel": "low"}}, {}]

    def _gemini(self, text):
        key = self.cfg["ia_chave_gemini"].strip()
        contents = []
        for q, a in self.history[-6:]:
            contents += [{"role": "user", "parts": [{"text": q}]}, {"role": "model", "parts": [{"text": a}]}]
        contents.append({"role": "user", "parts": [{"text": text}]})
        base = "https://generativelanguage.googleapis.com/v1beta/"
        hdr = {"x-goog-api-key": key}
        model = self.cfg.get("ia_modelo_gemini") or "gemini-flash-lite-latest"
        if model == "gemini-flash-latest":      # versoes antigas usavam o modelo mais lento
            model = "gemini-flash-lite-latest"

        def call(model, modo):
            gen = {"maxOutputTokens": 300, "temperature": 0.7}
            gen.update(self.RAPIDO[modo])
            body = {"system_instruction": {"parts": [{"text": self.system_prompt()}]}, "contents": contents,
                    "generationConfig": gen}
            return http_json(f"{base}models/{model}:generateContent", body, hdr, timeout=25)

        modo = int(self.cfg.get("ia_modo_rapido", 0))
        tentativas = 0
        while True:
            try:
                data = call(model, modo)
                break
            except RuntimeError as e:
                msg = str(e).lower()
                tentativas += 1
                if tentativas > 6:
                    raise
                if ("404" in msg or "not found" in msg):
                    lst = http_json(f"{base}models?pageSize=200", None, hdr).get("models", [])
                    ok = [m["name"].split("/")[-1] for m in lst
                          if "generateContent" in m.get("supportedGenerationMethods", [])
                          and "flash" in m["name"] and not any(x in m["name"] for x in ("live", "tts", "image", "audio", "embedding"))]
                    if not ok:
                        raise
                    # prefere "flash-lite" (mais rapido), estavel e mais novo
                    ok.sort(key=lambda n: ("lite" not in n, "preview" in n or "exp" in n,
                                           [-int(x) for x in re.findall(r"\d+", n)[:2]]))
                    model = ok[0]
                    continue
                if "400" in msg and ("thinking" in msg or "invalid json" in msg or "unknown name" in msg) and modo < len(self.RAPIDO) - 1:
                    modo += 1
                    continue
                raise
        if self.cfg.get("ia_modelo_gemini") != model or self.cfg.get("ia_modo_rapido") != modo:
            self.cfg["ia_modelo_gemini"] = model; self.cfg["ia_modo_rapido"] = modo; save_config(self.cfg)
        parts = (data.get("candidates") or [{}])[0].get("content", {}).get("parts", [])
        return "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()

    def _anthropic(self, text):
        msgs = []
        for q, a in self.history[-6:]:
            msgs += [{"role": "user", "content": q}, {"role": "assistant", "content": a}]
        msgs.append({"role": "user", "content": text})
        body = {"model": self.cfg.get("ia_modelo", "claude-haiku-5-5"), "max_tokens": 400,
                "system": self.system_prompt(), "messages": msgs}
        data = http_json("https://api.anthropic.com/v1/messages", body,
                         {"x-api-key": self.cfg["ia_chave_anthropic"].strip(), "anthropic-version": "2023-06-01"})
        return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text").strip()

    def _run(self, text):
        nome = self.cfg["nome_usuario"]
        try:
            out = self._gemini(text) if self.provider() == "gemini" else self._anthropic(text)
            out = re.sub(r"[*#_`]", "", out).strip()
            if out:
                self.history.append((text, out))
            self.answered.emit(out or f"Hmm, não consegui pensar numa resposta agora, {nome}.")
        except Exception as e:
            log.warning("IA falhou: %s", e)
            msg = str(e)
            if "429" in msg or "quota" in msg.lower():
                self.answered.emit(f"{nome}, usei todas as perguntas grátis por agora. Daqui a pouco eu volto a responder.")
            elif "400" in msg or "401" in msg or "403" in msg or "API key" in msg:
                self.answered.emit(f"{nome}, a chave da inteligência artificial parece inválida. Confere no menu, em Configurar IA.")
            else:
                motivo = "demorou demais" if "timed out" in msg.lower() or "timeout" in msg.lower() else "sem conexão com a IA"
                self.answered.emit(f"Desculpa, {nome}, não consegui responder agora: {motivo}. Tenta de novo?")


# ----------------------------------------------------------------------------
# Efeito de voz robotica
# ----------------------------------------------------------------------------
# estilo: (voz do Edge, tom, velocidade, efeito)   efeito: None | "metal" | "metal_forte"
# estilo: (voz online do Edge, tom, velocidade, efeito, aceleracao da voz do Windows)
# estilo: (voz online, tom, velocidade, efeito, aceleracao online, aceleracao da voz do Windows)
# Menino: voz masculina com a voz "encolhida" (aceleracao) -> timbre de crianca, e metal bem leve.
VOZ_ESTILOS = {
    "menino": ("pt-BR-AntonioNeural", "+18Hz", "-10%", "metal_leve", 1.2, 1.25),
    "normal": ("pt-BR-AntonioNeural", "+0Hz", "+4%", None, 1.0, 1.0),
}


def process_voice(x, rate, effect, speed, out_path):
    """speed > 1 deixa a voz mais aguda e jovem (voz de menino); effect adiciona o metal de robo."""
    import wave
    x = [float(v) for v in x]
    if speed and abs(speed - 1.0) > 0.01:
        n = int(len(x) / speed)
        y = [0.0] * n
        for i in range(n):
            p = i * speed
            j = int(p)
            f = p - j
            a = x[j] if j < len(x) else 0.0
            b = x[j + 1] if j + 1 < len(x) else a
            y[i] = a + (b - a) * f
        x = y
    out = x
    if effect:
        if effect == "metal_leve":
            taps, fb_d, fb = ((0.0023, 0.16),), 0.004, 0.08
        elif effect == "metal_forte":
            taps, fb_d, fb = ((0.0031, 0.55), (0.0069, 0.4), (0.0113, 0.25)), 0.0045, 0.5
        else:
            taps, fb_d, fb = ((0.0029, 0.35), (0.0061, 0.2)), 0.0052, 0.28
        taps = [(max(1, int(d * rate)), g) for d, g in taps]
        fd = max(1, int(fb_d * rate))
        out = [0.0] * len(x)
        for i in range(len(x)):
            v = x[i]
            for d, g in taps:
                if i >= d:
                    v += g * x[i - d]
            if i >= fd:
                v += fb * out[i - fd]
            out[i] = v
    peak = max(1.0, max((abs(v) for v in out), default=1.0))
    g = 30000.0 / peak
    data = array("h", (int(v * g) for v in out))
    with wave.open(out_path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(data.tobytes())
    return out_path


def robotize_mp3(mp3_path, effect, speed=1.0):
    import miniaudio
    rate = 24000
    dec = miniaudio.decode_file(mp3_path, output_format=miniaudio.SampleFormat.SIGNED16,
                                nchannels=1, sample_rate=rate)
    return process_voice(dec.samples, rate, effect, speed, mp3_path[:-4] + ".wav")


def robotize_wav(wav_path, effect, speed=1.0):
    import wave
    with wave.open(wav_path, "rb") as w:
        rate, ch, sw = w.getframerate(), w.getnchannels(), w.getsampwidth()
        raw = w.readframes(w.getnframes())
    if sw != 2:
        raise RuntimeError("wav nao suportado")
    x = array("h", raw)
    if ch == 2:
        x = x[::2]
    return process_voice(x, rate, effect, speed, wav_path[:-4] + "_robo.wav")


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
        for f in glob.glob(os.path.join(self.tmpdir, "fala_*")):
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
                    voz, tom, vel, _, _, _ = VOZ_ESTILOS.get(self.cfg.get("efeito_voz", "menino"), VOZ_ESTILOS["menino"])
                    ultimo = None
                    # se a voz escolhida nao existir mais no servidor, tenta as parecidas
                    for v in dict.fromkeys([voz, voz.replace("Neural", "MultilingualNeural"),
                                            "pt-BR-FranciscaNeural", "pt-BR-AntonioNeural"]):
                        try:
                            await edge_tts.Communicate(text, v, rate=vel, pitch=tom).save(path)
                            if os.path.getsize(path) > 0:
                                return
                        except Exception as e:
                            ultimo = e
                    raise ultimo or RuntimeError("sem audio")

                asyncio.run(go())
                if os.path.exists(path) and os.path.getsize(path) > 0:
                    est = VOZ_ESTILOS.get(self.cfg.get("efeito_voz", "menino"), VOZ_ESTILOS["menino"])
                    efeito, acel = est[3], est[4]
                    log.info("voz: online (%s)", self.cfg.get("efeito_voz"))
                    if efeito or acel != 1.0:
                        try:
                            path = robotize_mp3(path, efeito, acel)
                        except Exception as e:
                            log.info("efeito robo indisponivel: %s", e)
                    self._file_ready.emit(rid, path)
                    return
            except Exception as e:
                log.warning("voz online falhou, usando voz do Windows: %s", e)
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
            eng.setProperty("rate", 175)
            if rid != self.req:
                return
            _, _, _, efeito, _, speed = VOZ_ESTILOS.get(self.cfg.get("efeito_voz", "menino"), VOZ_ESTILOS["menino"])
            if self.player is not None and not getattr(self, "_player_broken", False):
                try:   # grava, transforma em voz de menino e toca no player
                    wav = os.path.join(self.tmpdir, f"fala_{int(time.time() * 1000)}_{rid}.wav")
                    eng.save_to_file(text, wav)
                    eng.runAndWait()
                    if os.path.exists(wav) and os.path.getsize(wav) > 100:
                        out = robotize_wav(wav, efeito, speed) if (efeito or speed != 1.0) else wav
                        log.info("voz: Windows (offline) com efeito %s", self.cfg.get("efeito_voz"))
                        self._file_ready.emit(rid, out)
                        return
                except Exception as e:
                    log.info("voz do Windows sem efeito: %s", e)
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
        self._player_broken = True
        rid = self.req
        self.pending = True
        threading.Thread(target=self._speak_offline, args=(rid, self._last_text), daemon=True).start()


# ----------------------------------------------------------------------------
# Escuta (microfone -> texto)
# ----------------------------------------------------------------------------
class Listener(QObject):
    heard = Signal(str, bool)
    status = Signal(str)
    level = Signal(float)     # 0..1, para mostrar que esta ouvindo

    RATE, BLOCK = 16000, 480  # blocos de 30 ms
    MIN_THR = 160.0           # sensibilidade (menor = ouve mais baixo)

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
        dev = self.cfg.get("microfone")
        try:
            log.info("microfones: %s", [(i, d["name"]) for i, d in enumerate(sd.query_devices())
                                         if d["max_input_channels"] > 0])
        except Exception:
            pass
        self.stream = sd.RawInputStream(samplerate=self.RATE, channels=1, dtype="int16", blocksize=self.BLOCK,
                                        device=dev if dev not in ("", None) else None)
        self.stream.start()
        vals = []
        for _ in range(20):
            data, _ = self.stream.read(self.BLOCK)
            vals.append(self.rms(bytes(data)))
        self.ambient = sum(vals) / len(vals)
        self.threshold = max(self.MIN_THR, self.ambient * 2.5)
        log.info("microfone aberto (aparelho %s); ruido %.0f, limite %.0f", dev, self.ambient, self.threshold)

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
            self._lv = getattr(self, "_lv", 0) + 1
            if self._lv % 3 == 0:
                self.level.emit(min(1.0, lvl / 3000.0))
            if not speaking:
                if lvl > self.threshold:
                    speaking = True
                    frames = list(pre) + [data]
                    voiced = 1
                else:
                    pre.append(data)
                    self.ambient = self.ambient * 0.97 + lvl * 0.03
                    self.threshold = max(self.MIN_THR, self.ambient * 2.5)
                    if time.monotonic() - start > limit:
                        return None
            else:
                frames.append(data)
                if lvl > self.threshold * 0.6:
                    silence = 0; voiced += 1
                else:
                    silence += 1
                if silence > 20 or len(frames) > 400:
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
        url = base + rel + f"?t={int(time.time())}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "RoboBravus", "Cache-Control": "no-cache"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except Exception as e:
            if sys.platform != "win32":
                raise
            log.info("download pelo Python falhou (%s); tentando pelo Windows", e)
            curl = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "curl.exe")
            if os.path.exists(curl):
                r = subprocess.run([curl, "-sSfL", "-H", "Cache-Control: no-cache", url], capture_output=True,
                                   timeout=90, creationflags=0x08000000)
                if r.returncode == 0 and r.stdout:
                    return r.stdout
                log.info("curl falhou: %s", r.stderr[-200:])
            # plano B: baixa usando a internet do proprio Windows (resolve certificados antigos)
            tmp = os.path.join(tempfile.gettempdir(), "robo_bravus_dl.tmp")
            ps = ("[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12;"
                  f"Invoke-WebRequest -UseBasicParsing -Uri '{url}' -OutFile '{tmp}'")
            r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
                               capture_output=True, text=True, timeout=90, creationflags=0x08000000)
            if r.returncode != 0 or not os.path.exists(tmp):
                raise RuntimeError("sem acesso ao GitHub: " + (r.stderr or str(e))[-200:])
            with open(tmp, "rb") as f:
                data = f.read()
            os.remove(tmp)
            return data

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
            old_req = b""
            try:
                old_req = open(os.path.join(APP_DIR, "requirements.txt"), "rb").read()
            except Exception:
                pass
            for rel, data in got.items():           # so substitui depois de baixar tudo
                dest = os.path.join(APP_DIR, *rel.split("/"))
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                tmp = dest + ".novo"
                with open(tmp, "wb") as f:
                    f.write(data)
                os.replace(tmp, dest)
            if "requirements.txt" in got and got["requirements.txt"].strip() != old_req.strip():
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
TECLAS = {1: ("B", "alternar"), 2: ("F", "falar"), 3: ("M", "mudo"), 4: ("U", "atualizar")}  # Ctrl + Alt + tecla


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
        self.lift = lerp(self.lift, -self.sit * 16, min(1.0, dt * 3))
        target = 0.25 + 0.75 * abs(math.sin(self.t * 17) * math.sin(self.t * 5.3 + 1)) if self.talking else 0.0
        self.mouth = lerp(self.mouth, target, min(1.0, dt * 20))

    _scaled = {}

    @classmethod
    def blit(cls, p, name):
        """Desenha a camada ja redimensionada para o tamanho da tela (bem mais leve)."""
        pix = cls.pixmaps()[name]
        tr = p.transform()
        dpr = p.device().devicePixelRatioF() if p.device() else 1.0
        eff = round(math.hypot(tr.m11(), tr.m12()) * dpr, 3)
        key = (name, eff)
        sp = cls._scaled.get(key)
        if sp is None:
            if len(cls._scaled) > 24:
                cls._scaled.clear()
            sp = pix.scaled(max(1, int(pix.width() * eff)), max(1, int(pix.height() * eff)),
                            Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
            sp.setDevicePixelRatio(dpr)
            cls._scaled[key] = sp
        p.save()
        p.scale(pix.width() / (sp.width() / dpr), pix.height() / (sp.height() / dpr))
        p.drawPixmap(0, 0, sp)
        p.restore()

    @classmethod
    def part(cls, p, name, piv, ang, dy=0.0):
        p.save()
        p.translate(piv.x(), piv.y() + dy); p.rotate(ang); p.translate(-piv.x(), -piv.y())
        cls.blit(p, name)
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
            self.part(p, "armL", self.ARML_PIV, self.la)
            self.part(p, "body", P(0, 0), 0)
        p.save()
        p.translate(self.HEAD_PIV.x(), self.HEAD_PIV.y() + self.hdy); p.rotate(self.rh)
        p.translate(-self.HEAD_PIV.x(), -self.HEAD_PIV.y())
        self.blit(p, "head")
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
        mic = getattr(self, "mic", 0.0)
        if self.listening or mic > 0.05:
            for c in (P(68, 240), P(452, 200)):
                ring = QPainterPath(); ring.addEllipse(c, 30, 40)
                self.glow_path(p, ring, GLOW, fill=False, width=5,
                               strength=min(1.6, (1.0 if self.listening else 0.3) + mic * 2.5))
        p.restore()
        if not head_only:
            # braco direito por cima (com copo d'agua)
            p.save()
            p.translate(self.ARMR_PIV.x(), self.ARMR_PIV.y()); p.rotate(self.ra)
            p.translate(-self.ARMR_PIV.x(), -self.ARMR_PIV.y())
            if "cup" in self.fx:
                p.save(); p.translate(self.HAND_R.x() + 5, self.HAND_R.y() - 30); p.scale(3.2, 3.2)
                self.draw_cup(p, P(0, 0)); p.restore()
            self.blit(p, "armR")
            if "clock" in self.fx:
                self.draw_holo_clock(p)
            p.restore()
        p.restore()
        if not head_only:
            self.draw_fx_sprite(p)

    def draw_holo_clock(self, p):
        """Relogio holografico flutuando sobre a palma da mao direita."""
        t = self.t
        hx, hy = 520, 120 + math.sin(t * 2.2) * 6
        w, h = 340, 175
        rect = QRectF(hx - w / 2, hy - h / 2, w, h)
        # feixe de luz saindo da mao
        beam = QPainterPath()
        beam.moveTo(518, 292); beam.lineTo(rect.left() + 30, rect.bottom()); beam.lineTo(rect.right() - 30, rect.bottom())
        beam.lineTo(548, 292); beam.closeSubpath()
        g = QLinearGradient(0, 292, 0, rect.bottom())
        g.setColorAt(0, QColor(0, 190, 255, 140)); g.setColorAt(1, QColor(0, 190, 255, 15))
        p.setPen(Qt.NoPen); p.setBrush(g); p.drawPath(beam)
        panel = QPainterPath(); panel.addRoundedRect(rect, 22, 22)
        p.setBrush(QColor(4, 20, 40, 170)); p.drawPath(panel)
        self.glow_path(p, panel, GLOW, fill=False, width=4, strength=1.1)
        # linhas de holograma
        p.save(); p.setClipPath(panel)
        off = (t * 30) % 8
        p.setPen(QPen(QColor(0, 200, 255, 28), 2))
        y = rect.top() + off
        while y < rect.bottom():
            p.drawLine(P(rect.left(), y), P(rect.right(), y)); y += 8
        p.restore()
        hora = getattr(self, "clock_text", "--:--")
        if int(t * 2) % 2 == 1:
            hora = hora.replace(":", " ")
        f = QFont("Segoe UI"); f.setBold(True); f.setPixelSize(100)
        p.setFont(f)
        for wdt, a in ((8, 40), (4, 80)):
            p.setPen(QPen(QColor(0, 180, 255, a), wdt))
            p.drawText(QRectF(rect.left(), rect.top() + 6, w, 115), Qt.AlignCenter, hora)
        p.setPen(QColor(210, 245, 255))
        p.drawText(QRectF(rect.left(), rect.top() + 6, w, 115), Qt.AlignCenter, hora)
        f2 = QFont("Segoe UI"); f2.setPixelSize(36); f2.setBold(True)
        p.setFont(f2); p.setPen(QColor(120, 210, 255))
        p.drawText(QRectF(rect.left(), rect.top() + 116, w, 50), Qt.AlignCenter, getattr(self, "date_text", ""))

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
        self.listener.level.connect(self.on_mic_level)
        self.mic_level = 0.0
        self.mic_test_until = 0.0

        self.bubble_text, self.bubble_until, self.bubble_kind = "", 0.0, "say"
        self.action, self.action_until = None, 0.0
        self.expr_temp, self.expr_until = None, 0.0
        self.base_sit = False
        self.sleeping = False
        self.listening = False
        self.listen_after_speech = False
        self.look_target = None
        self.look_until = 0.0
        self.next_idle = 20.0
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
        self.upd_timer.start(3600 * 1000)   # procura sozinho a cada 1 hora
        threading.Thread(target=sync_relogio, daemon=True).start()
        self.sync_timer = QTimer(self)
        self.sync_timer.timeout.connect(lambda: threading.Thread(target=sync_relogio, daemon=True).start())
        self.sync_timer.start(3600 * 1000)
        QTimer.singleShot(45000, self.auto_update)
        if sys.platform == "win32" and self.cfg.get("atalhos_versao") != VERSAO:
            def _atalhos():
                try:
                    make_shortcut()
                    self.cfg["atalhos_versao"] = VERSAO; save_config(self.cfg)
                except Exception as e:
                    log.warning("atalhos: %s", e)
            threading.Thread(target=_atalhos, daemon=True).start()

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
    DUR = {"clock": 10.0, "scratch": 4.0, "think": 5.0, "wave": 2.6, "present": 3.0, "water": 6.0,
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
            pose = "rest_float" if self.action == "clock" else self.action
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
        elif self.action == "clock":
            e = "happy"
        else:
            e = "neutral"
        m.expr = e

        fx = set()
        if self.action == "water":
            fx.add("cup")
        if self.action == "clock" or (self.cfg.get("relogio_fixo") and not self.action and not self.sleeping):
            fx.add("clock")
            agr = agora()
            m.clock_text = agr.strftime("%H:%M")
            m.date_text = f"{DIAS[agr.weekday()][:3].upper()}  {agr.day:02d}/{agr.month:02d}/{agr.year}"
        if self.action == "think" or self.bubble_kind == "thinking":
            fx.add("dots")
        if self.action == "scratch":
            fx.add("question")
        if self.sleeping:
            fx.add("zzz")
        m.fx = fx
        m.listening = self.listening
        self.mic_level *= 0.85
        m.mic = self.mic_level

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
        h = agora().hour
        if (not self.sleeping and not busy and (h >= 23 or h < 5)
                and time.monotonic() - self.last_interaction > 20 * 60):
            self.go_sleep()

        animado = m.talking or self.listening or self.action or self.bubble_until > t
        iv = 40 if animado else 66          # 25 fps em acao, 15 fps parado
        if self.tick_timer.interval() != iv:
            self.tick_timer.setInterval(iv)
        if self.isVisible():
            self.update()

    ROTINA = ["sit", "scratch", "think", "wave", "stretch", "nap"]

    def random_behavior(self):
        """A cada 1 minuto faz uma das acoes do menu, em ordem embaralhada (sem repetir seguido)."""
        t = self.m.t
        if not getattr(self, "_fila", None):
            fila = self.ROTINA[:]
            random.shuffle(fila)
            if getattr(self, "_ultima", None) == fila[0]:
                fila.append(fila.pop(0))
            self._fila = fila
        choice = self._fila.pop(0)
        self._ultima = choice
        if choice == "sit":
            self.base_sit = not self.base_sit          # senta ou levanta/flutua
            self.set_expr("happy", 1.5)
        elif choice == "nap":
            self.go_sleep()                             # cochilo rapido
            self._napping = True
            QTimer.singleShot(9000, self.end_nap)
        else:
            self.do_action(choice)
        self.next_idle = t + 60

    def end_nap(self):
        if getattr(self, "_napping", False) and self.sleeping:
            self.sleeping = False
            self.base_sit = False
            self.do_action("stretch")
        self._napping = False

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
        now = agora()
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
        if "--reiniciar" in sys.argv:
            msg = f"Pronto, {self.nome}! Fui atualizado para a versão {VERSAO}. Essa é minha voz de robô menino!"
        if saud == "Bom dia":
            self.cfg["ultima_saudacao"] = now.date().isoformat()
        save_config(self.cfg)
        self.say(msg, "wave")

    def each_minute(self):
        now = agora()
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

    def on_mic_level(self, v):
        self.mic_level = max(v, self.mic_level * 0.6)
        self.m.mic = self.mic_level
        if self.m.t < self.mic_test_until:
            barras = int(self.mic_level * 20)
            self.show_status("Nível do microfone:  " + "▮" * barras + "▯" * (20 - barras)
                             + ("\nEstou te ouvindo bem!" if self.mic_level > 0.08 else "\nFale algo..."), 1.0)

    def test_mic(self):
        if not self.listener.ok:
            self.show_status("A escuta não está instalada. Rode o atualizador de novo.", 6); return
        self.mic_test_until = self.m.t + 12
        self.listener.force = True
        self.listening = True
        self.show_status("Fale algo para testar o microfone...", 3)

    def mic_menu(self, menu):
        try:
            import sounddevice as sd
            devs = [(i, d["name"]) for i, d in enumerate(sd.query_devices())
                    if d["max_input_channels"] > 0 and sd.query_hostapis(d["hostapi"])["name"] == "MME"]
        except Exception:
            devs = []
        atual = self.cfg.get("microfone")
        a = QAction("Padrão do Windows", menu); a.setCheckable(True); a.setChecked(atual in (None, ""))
        a.triggered.connect(lambda: self.set_mic(None)); menu.addAction(a)
        for i, nome in devs:
            a = QAction(nome[:45], menu); a.setCheckable(True); a.setChecked(atual == i)
            a.triggered.connect(lambda _=False, i=i: self.set_mic(i)); menu.addAction(a)

    def set_mic(self, i):
        self.cfg["microfone"] = i; save_config(self.cfg)
        self.listener._close()
        self.show_status("Microfone trocado. Vamos testar!", 2)
        QTimer.singleShot(1500, self.test_mic)

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
            import difflib
            n = norm(text)
            words = re.findall(r"[\w']+", n)
            wake = [norm(w) for w in self.cfg.get("palavras_ativacao", [])] + ["bravus"]
            idx = None
            for i, w in enumerate(words):
                cand = [w] + ([w + words[i + 1]] if i + 1 < len(words) else [])
                if any(c in wake or difflib.SequenceMatcher(None, c, "bravus").ratio() >= 0.72 for c in cand):
                    idx = i
                    break
            if idx is None:
                log.info("ouviu sem a palavra Bravus: %s", text)
                return
            rest = " ".join(words[idx + 1:]).strip()
            if rest and difflib.SequenceMatcher(None, words[idx] + (words[idx + 1] if idx + 1 < len(words) else ""), "bravus").ratio() > 0.9:
                rest = " ".join(words[idx + 2:]).strip()
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
        pend = getattr(self, "pending_confirm", None)
        self.pending_confirm = None
        if pend and time.monotonic() - pend[1] < 40:
            nn = norm(text)
            if re.search(r"\b(sim|pode|confirmo|isso)\b", nn) and not re.search(r"\bnao\b", nn):
                acao = pend[0][0]
                self.say(f"Ok, {self.nome}. O computador vai {'desligar' if acao == 'shutdown' else 'reiniciar'} em 30 segundos. "
                         f"Se mudar de ideia, diga: cancela o desligamento.", "wave")
                self.run_pc((acao,))
                return
            self.say(f"Tudo bem, {self.nome}, não vou fazer nada.", "happy")
            return
        res = self.brain.respond(text)
        if res is not None and res.get("chat") and self.ai.available() and len(text.split()) > 3:
            res = None   # pergunta de verdade: deixa a IA responder
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
                    f"Ainda não sei responder isso, {self.nome}. Clique em mim com o botão direito, em Configurar IA, e eu passo a responder tudo!",
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
        if res.get("quiet"):
            self.show_status(res["reply"], 2)
        elif res.get("mute") is True:
            self.say(res["reply"], res.get("action"))
            self.cfg["mudo"] = True; save_config(self.cfg)
        else:
            if res.get("mute") is False:
                self.cfg["mudo"] = False; save_config(self.cfg)
            self.say(res["reply"], res.get("action"))
        if res.get("open_url"):
            QTimer.singleShot(900, lambda u=res["open_url"]: webbrowser.open(u))
        if res.get("pc"):
            QTimer.singleShot(500, lambda c=res["pc"]: self.run_pc(c))
        if res.get("update"):
            QTimer.singleShot(2500, self.manual_update)
        if res.get("confirm"):
            self.pending_confirm = (res["confirm"], time.monotonic())
            self.listen_after_speech = True

    def run_pc(self, c):
        try:
            kind = c[0]
            if kind == "keys":
                pc_keys(c[1], c[2] if len(c) > 2 else 1)
            elif kind == "open":
                pc_open(c[1])
            elif kind == "folder":
                pc_folder(c[1])
            elif kind == "type":
                pc_type(c[1])
            elif kind == "lock":
                QTimer.singleShot(1500, pc_lock)
            elif kind == "shutdown" and sys.platform == "win32":
                subprocess.Popen(["shutdown", "/s", "/t", "30"], creationflags=0x08000000)
            elif kind == "restart" and sys.platform == "win32":
                subprocess.Popen(["shutdown", "/r", "/t", "30"], creationflags=0x08000000)
            elif kind == "cancel_shutdown" and sys.platform == "win32":
                subprocess.Popen(["shutdown", "/a"], creationflags=0x08000000)
            log.info("comando no PC: %s", c)
        except Exception as e:
            log.warning("comando falhou %s: %s", c, e)
            self.show_status(f"Não consegui fazer isso: {e}", 5)

    def on_ai(self, text):
        import urllib.parse
        for tipo, valor in re.findall(r"\[(SITE|PESQUISAR|YOUTUBE):\s*([^\]]+)\]", text, re.I):
            tipo, valor = tipo.upper(), valor.strip()
            if tipo == "SITE" and re.match(r"https?://", valor):
                url = valor
            elif tipo == "YOUTUBE":
                url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(valor)
            else:
                url = "https://www.google.com/search?q=" + urllib.parse.quote_plus(valor)
            QTimer.singleShot(900, lambda u=url: webbrowser.open(u))
        text = re.sub(r"\[(SITE|PESQUISAR|YOUTUBE):[^\]]*\]", "", text, flags=re.I).strip()
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
        mic = mn.addMenu("🎙️  Microfone")
        add("Testar microfone", self.test_mic, menu=mic)
        mic.addSeparator()
        self.mic_menu(mic)
        vz = mn.addMenu("🔊  Voz")
        for label, v in (("Robô menino", "menino"), ("Natural", "normal")):
            add(label, lambda _=False, v=v: self.set_voice(v), self.cfg.get("efeito_voz", "menino") == v, menu=vz)
        add("🔇  Silenciar voz", self.toggle_mute, self.cfg.get("mudo"))
        add("🕒  Mostrar a hora agora", lambda: self.handle_text("que horas são"))
        add("🕒  Relógio sempre na mão", self.toggle_clock, self.cfg.get("relogio_fixo"))
        add("🎲  Movimentos aleatórios", self.toggle_random, self.cfg.get("comportamentos_aleatorios", True))
        sz = mn.addMenu("📏  Tamanho")
        for label, v in (("Mini", 0.5), ("Pequeno", 0.65), ("Médio", 0.8), ("Grande", 1.0)):
            add(label, lambda _=False, v=v: self.set_size(v), abs(self.cfg.get("tamanho", 0.8) - v) < 0.01, menu=sz)
        if sys.platform == "win32":
            add("🚀  Iniciar com o Windows", self.toggle_autostart, os.path.exists(startup_path()))
        mn.addSeparator()
        add("🧠  Configurar IA (responder tudo)" + ("  ✓" if self.ai.available() else ""), self.config_ai)
        add(f"🔄  Procurar atualização (v{VERSAO})", self.manual_update)
        add("📋  Ver registro (para suporte)", lambda: pc_open(LOG_PATH))
        add("⚙️  Abrir configurações", lambda: os.startfile(CONFIG_PATH) if sys.platform == "win32" else None)
        add("🙈  Desativar (Ctrl+Alt+B)", lambda: self.set_active(False))
        add("❌  Sair", self.quit_app)

    def config_ai(self):
        txt, ok = QInputDialog.getText(
            self, "Robô Bravus - Inteligência Artificial",
            "Cole aqui a sua chave de IA:\n\n"
            "• Gemini (grátis): crie em aistudio.google.com/apikey  (começa com AIza...)\n"
            "• Claude (pago): crie em console.anthropic.com  (começa com sk-ant-...)\n\n"
            "Para remover a chave, deixe em branco e clique OK.")
        if not ok:
            return
        k = txt.strip()
        if k.startswith("sk-ant"):
            self.cfg["ia_chave_anthropic"] = k; self.cfg["ia_chave_gemini"] = ""
        elif k:
            self.cfg["ia_chave_gemini"] = k; self.cfg["ia_chave_anthropic"] = ""
        else:
            self.cfg["ia_chave_gemini"] = ""; self.cfg["ia_chave_anthropic"] = ""
        save_config(self.cfg)
        if k:
            self.say(f"Chave salva, {self.nome}! Agora pode me perguntar qualquer coisa. Vou testar...", "happy")
            QTimer.singleShot(4500, lambda: self.handle_text("Se apresente em uma frase curta e diga que está pronto pra ajudar."))
        else:
            self.say(f"Chave removida, {self.nome}.")

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
        self.say({"menino": f"Oi, {self.nome}! Essa é minha voz de robô menino. Gostou?",
                  "normal": f"Voz natural ativada, {self.nome}."}[v], "happy")

    def toggle_mute(self):
        self.cfg["mudo"] = not self.cfg.get("mudo"); save_config(self.cfg)
        if self.cfg["mudo"]:
            self.voice.stop()
        self.show_status("Voz desligada." if self.cfg["mudo"] else "Voz ligada.")

    def toggle_clock(self):
        self.cfg["relogio_fixo"] = not self.cfg.get("relogio_fixo"); save_config(self.cfg)

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
            self.show_status("Não consegui atualizar: " + info[:120], 8)

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
        elif cmd == "atualizar":
            self.set_active(True); self.manual_update()
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
    """Cria os atalhos (Area de Trabalho + Menu Iniciar) usando VBScript; nao depende do PowerShell."""
    script = os.path.abspath(__file__)
    vq = lambda x: x.replace('"', '""')
    lines = ['Set w = CreateObject("WScript.Shell")',
             'Set fs = CreateObject("Scripting.FileSystemObject")',
             'd = w.SpecialFolders("Desktop")',
             'm = w.SpecialFolders("Programs") & "\\Robo Bravus"',
             'If Not fs.FolderExists(m) Then fs.CreateFolder(m)',
             'If fs.FileExists(d & "\\Robo Bravus.lnk") Then fs.DeleteFile(d & "\\Robo Bravus.lnk")']
    for pasta, nome, arg, desc, tecla in (("d", "Ligar Robo Bravus", "", "Liga o Robo Bravus (Ctrl+Alt+R)", "CTRL+ALT+R"),
                                         ("d", "Desligar Robo Bravus", " --sair", "Desliga o Robo Bravus", ""),
                                         ("m", "Robo Bravus", "", "Robo Bravus - Bravus Midia", "")):
        lines += [f'Set s = w.CreateShortcut({pasta} & "\\{nome}.lnk")',
                  f's.TargetPath = "{vq(pythonw_exe())}"',
                  f's.Arguments = """{vq(script)}""{arg}"',
                  f's.WorkingDirectory = "{vq(APP_DIR)}"',
                  f's.IconLocation = "{vq(ICON_PATH)}"',
                  f's.Description = "{desc}"']
        if tecla:
            lines.append(f's.Hotkey = "{tecla}"')
        lines.append("s.Save")
    vbs = os.path.join(tempfile.gettempdir(), "robo_bravus_atalhos.vbs")
    with open(vbs, "w", encoding="mbcs" if sys.platform == "win32" else "utf-8") as f:
        f.write("\r\n".join(lines) + "\r\n")
    cscript = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "cscript.exe")
    r = subprocess.run([cscript, "//nologo", vbs], capture_output=True, text=True,
                       creationflags=0x08000000 if sys.platform == "win32" else 0)
    if r.returncode != 0:
        raise RuntimeError("atalhos: " + (r.stderr or r.stdout)[-200:])


def install(autostart):
    app = QGuiApplication(sys.argv)  # noqa: F841
    render_icon(256).save(ICON_PATH, "ICO")
    print("  - Icone criado")
    if sys.platform == "win32":
        try:
            make_shortcut(); print("  - Atalhos criados (Area de Trabalho e Menu Iniciar). Ctrl+Alt+R liga o robo")
        except Exception as e:
            print("  - Nao consegui criar os atalhos:", e)
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
    if cfg.get("efeito_voz") not in VOZ_ESTILOS or not cfg.get("voz_menino_v2"):
        cfg["efeito_voz"] = "menino"; cfg["voz_menino_v2"] = True
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
