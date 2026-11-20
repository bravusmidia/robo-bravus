# -*- coding: utf-8 -*-
"""Atualizador do Robo Bravus (nao usa PowerShell).
Baixa a versao mais nova do GitHub, instala por cima mantendo suas configuracoes e abre o robo."""
import os, sys, time, socket, shutil, zipfile, tempfile, subprocess, urllib.request

ZIP_URL = "https://github.com/bravusmidia/robo-bravus/archive/refs/heads/main.zip"
MANTER = {"config.json", "robo_bravus.log", ".gitattributes", "README.md"}


def baixar(url, destino):
    curl = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "curl.exe")
    if os.path.exists(curl):  # usa a internet do proprio Windows (certificados do sistema)
        r = subprocess.run([curl, "-sSfL", "--retry", "2", "-o", destino, url])
        if r.returncode == 0 and os.path.getsize(destino) > 0:
            return
    with urllib.request.urlopen(url, timeout=60) as resp, open(destino, "wb") as f:
        f.write(resp.read())


def achar_pasta():
    home = os.path.expanduser("~")
    bases = [os.path.join(home, p) for p in ("Desktop", "Área de Trabalho", "Documents", "Documentos",
                                              "Downloads", "OneDrive")] + [home]
    achados = []
    for base in bases:
        if not os.path.isdir(base):
            continue
        for raiz, pastas, arqs in os.walk(base):
            if raiz[len(base):].count(os.sep) >= 4:
                pastas[:] = []
                continue
            pastas[:] = [p for p in pastas if not p.startswith(".") and p not in ("AppData", "node_modules")]
            if "robo_bravus.pyw" in arqs:
                achados.append(raiz)
    if not achados:
        return os.path.join(home, "Documents", "RoboBravus")
    return max(set(achados), key=lambda p: os.path.getmtime(os.path.join(p, "robo_bravus.pyw")))


def main():
    print("\n  ROBO BRAVUS - atualizando...\n")
    pasta = achar_pasta()
    print("  Pasta do robo:", pasta)

    # fecha o robo se estiver aberto
    try:
        with socket.create_connection(("127.0.0.1", 47851), timeout=2) as c:
            c.sendall(b"sair")
        print("  Fechando o robo...")
        time.sleep(4)
    except OSError:
        pass

    tmp = tempfile.mkdtemp(prefix="robo_bravus_")
    zp = os.path.join(tmp, "robo.zip")
    print("  Baixando a versao nova...")
    baixar(ZIP_URL, zp)
    with zipfile.ZipFile(zp) as z:
        z.extractall(tmp)
    src = os.path.join(tmp, "robo-bravus-main")
    os.makedirs(pasta, exist_ok=True)
    for nome in os.listdir(src):
        if nome in MANTER:
            continue
        a, b = os.path.join(src, nome), os.path.join(pasta, nome)
        if os.path.isdir(a):
            shutil.copytree(a, b, dirs_exist_ok=True)
        else:
            shutil.copy2(a, b)
    print("  Arquivos atualizados.")

    print("  Instalando componentes (pode levar 1 minuto)...")
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--disable-pip-version-check",
                    "-r", os.path.join(pasta, "requirements.txt")])
    subprocess.run([sys.executable, os.path.join(pasta, "robo_bravus.pyw"), "--instalar"], cwd=pasta)
    shutil.rmtree(tmp, ignore_errors=True)
    print("\n  PRONTO! O Robo Bravus foi atualizado e ja esta abrindo.\n")
    time.sleep(5)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("\n  ERRO:", e)
        input("  Tire um print desta tela e aperte Enter para fechar...")
