# -*- coding: utf-8 -*-
"""Robô de postagem do Tioban no GitHub Actions (roda a cada 20 min, das 8h às 23h40 de Brasília).

    python robo/postar.py verificar   tira da fila o que passou do horário e diz se tem Short para postar (tem=1)
    python robo/postar.py baixar      baixa os vídeos do horário para site/v/ (o Pages dá o link para o Instagram)
    python robo/postar.py publicar    posta nas redes ligadas, guarda os links e tira da fila

A fila (anexos do release "fila") é enchida pelo PC com o que sobrou na pasta "E:\\TIOBAN\\Postar DD-MM".
Redes ligadas = config.json -> redes (e o segredo da rede tem de existir). Nunca posta duas vezes: o link de cada
rede fica gravado no .json do item; o item só sai da fila quando todas as redes ligadas postaram, ou quando passa
de atraso_max_horas do horário (aí vai para postados.json como "parcial" ou "perdido").
"""
import json
import os
import subprocess
import sys
import time
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fila import Fila  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]
CONFIG = json.loads((RAIZ / "config.json").read_text(encoding="utf-8"))
POSTADOS = RAIZ / "postados.json"
SITE = RAIZ / "site"
BRT = timezone(timedelta(hours=-3))
NOMES = {"instagram": "Instagram", "facebook": "Facebook", "youtube": "YouTube"}
SEGREDO = {"instagram": "IG_TOKEN", "facebook": "FB_PAGE_TOKEN", "youtube": "YT_REFRESH_TOKEN"}


def agora():
    return datetime.now(timezone.utc)


def redes_ligadas():
    """Redes ligadas no config e com segredo. No passo "verificar" os segredos não vêm: vem TEM_<SEGREDO>=true."""
    out = []
    for rede, ligada in CONFIG.get("redes", {}).items():
        s = SEGREDO.get(rede)
        if ligada and s and (os.environ.get(s) or os.environ.get(f"TEM_{s}") == "true"):
            out.append(rede)
    return out


def legenda(d):
    return "\n\n".join(x for x in (d["titulo"], d.get("descricao", ""), d.get("hashtags", "")) if x).strip()


def saida(chave, valor):
    arq = os.environ.get("GITHUB_OUTPUT")
    if arq:
        with open(arq, "a", encoding="utf-8") as f:
            f.write(f"{chave}={valor}\n")
    print(f"{chave}={valor}")


def git(*a, ok=False):
    r = subprocess.run(["git", "-C", str(RAIZ), *a], capture_output=True, text=True)
    if r.returncode and not ok:
        raise RuntimeError(f"git {' '.join(a)}: {r.stderr[-500:]}")
    return r


def registrar(entradas):
    """Acrescenta em postados.json (registro de tudo que foi postado) e manda pro GitHub."""
    if not entradas:
        return
    git("config", "user.name", "robo-tioban")
    git("config", "user.email", "robo-tioban@users.noreply.github.com")
    for tentativa in range(5):
        git("pull", "--rebase", "--quiet", ok=True)
        lista = json.loads(POSTADOS.read_text(encoding="utf-8")) if POSTADOS.exists() else []
        ids = {e["id"] for e in lista}
        lista += [e for e in entradas if e["id"] not in ids]
        POSTADOS.write_text(json.dumps(lista, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        git("add", "postados.json")
        if git("diff", "--cached", "--quiet", ok=True).returncode == 0:
            return
        resumo = "; ".join(f"{e['id']} {e['situacao']}" for e in entradas)
        git("commit", "-m", f"postados: {resumo}"[:200])
        if git("push", ok=True).returncode == 0:
            return
        git("reset", "--hard", "HEAD~1")
        time.sleep(3 * (tentativa + 1))
    raise RuntimeError("não consegui gravar postados.json")


def entrada(iid, d, situacao):
    return {"id": iid, "pasta": d.get("pasta"), "numero": d.get("numero"), "titulo": d["titulo"],
            "publicar_em": d["publicar_em"], "situacao": situacao,
            "registrado_em": agora().astimezone(BRT).isoformat(timespec="seconds"),
            "postado": d.get("postado", {}), "erros": d.get("erros", {})}


def carregar(fila):
    """[(quando, id, item, dados)] de tudo que está completo na fila, mais antigo primeiro."""
    out = []
    for iid, it in fila.itens().items():
        if not (it["json"] and it["mp4"]):
            continue
        d = fila.ler_json(it["json"])
        out.append((datetime.fromisoformat(d["publicar_em"]), iid, it, d))
    return sorted(out, key=lambda x: x[0])


def pendentes(d, redes):
    return [r for r in redes if r not in d.get("postado", {})]


def do_horario(fila, redes):
    """Itens no horário (até 2 min antes) com alguma rede ligada faltando; tira da fila os que passaram do limite."""
    limite = timedelta(hours=float(CONFIG.get("atraso_max_horas", 3)))
    vencidos, prontos = [], []
    for quando, iid, it, d in carregar(fila):
        if quando > agora() + timedelta(minutes=2):
            continue
        if agora() - quando > limite:
            sit = "parcial" if d.get("postado") else "perdido"
            d.setdefault("erros", {})["geral"] = (d.get("erros", {}).get("geral") or
                                                  f"passou {limite} do horário sem postar em tudo")
            vencidos.append((iid, it, d, sit))
        elif pendentes(d, redes):
            prontos.append((quando, iid, it, d))
    if vencidos:
        registrar([entrada(iid, d, sit) for iid, it, d, sit in vencidos])
        for iid, it, d, sit in vencidos:
            fila.tirar(it)
            print(f"tirado da fila ({sit}): {iid} {d['titulo']}")
    return prontos


def main(passo):
    fila = Fila(os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_TOKEN"])
    if CONFIG.get("pausado"):
        print("postagem PAUSADA no config.json: nada a fazer")
        saida("tem", 0)
        return
    redes = redes_ligadas()
    print("redes ligadas:", ", ".join(NOMES[r] for r in redes) or "nenhuma")
    if not redes:
        saida("tem", 0)
        return
    prontos = do_horario(fila, redes)
    if passo == "verificar":
        for quando, iid, it, d in prontos:
            print(f"no horário: {iid} {d['titulo']} (falta: {', '.join(pendentes(d, redes))})")
        saida("tem", 1 if prontos else 0)
        return
    if passo == "baixar":
        (SITE / "v").mkdir(parents=True, exist_ok=True)
        for quando, iid, it, d in prontos:
            fila.baixar(it["mp4"], SITE / "v" / f"{iid}.mp4")
            print(f"baixado {iid}.mp4 ({(SITE / 'v' / f'{iid}.mp4').stat().st_size / 1e6:.1f} MB)")
        return
    # publicar
    pages = os.environ.get("PAGES_URL", "").rstrip("/")
    erro = False
    for quando, iid, it, d in prontos:
        video = SITE / "v" / f"{iid}.mp4"
        if not video.exists():
            fila.baixar(it["mp4"], video)
        d.setdefault("postado", {})
        d.setdefault("erros", {})
        for rede in pendentes(d, redes):
            try:
                print(f"{NOMES[rede]}: postando {iid} {d['titulo']}")
                if rede == "instagram":
                    import ig
                    url = f"{pages}/v/{iid}.mp4"
                    for _ in range(30):
                        if requests.head(url, timeout=20).status_code == 200:
                            break
                        time.sleep(10)
                    pid, link = ig.publicar(url, legenda(d))
                elif rede == "facebook":
                    import fb
                    pid, link = fb.publicar(video, legenda(d))
                else:
                    import yt
                    tags = [h for h in d.get("hashtags", "").split() if h.startswith("#")]
                    desc = "\n\n".join(x for x in (d.get("descricao", ""), d.get("hashtags", "") + " #shorts") if x)
                    pid, link = yt.publicar(video, d["titulo"], desc.strip(), tags,
                                            CONFIG.get("youtube_privacidade", "public"),
                                            CONFIG.get("youtube_conteudo_alterado", False))
                d["postado"][rede] = {"id": pid, "link": link,
                                      "quando": agora().astimezone(BRT).isoformat(timespec="seconds")}
                d["erros"].pop(rede, None)
                print(f"{NOMES[rede]}: OK {link}")
            except Exception as e:
                erro = True
                d["erros"][rede] = str(e)[:500]
                print(f"{NOMES[rede]}: ERRO\n{traceback.format_exc()}")
            it["json"] = fila.gravar_json(iid, d, it["json"])  # grava na hora: nunca posta duas vezes
        if not pendentes(d, redes):
            registrar([entrada(iid, d, "postado")])
            fila.tirar(it)
            print(f"concluído: {iid}")
    if erro:
        raise SystemExit(1)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "verificar")
