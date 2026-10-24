# -*- coding: utf-8 -*-
"""Fila de postagem do Tioban, guardada como anexos de um release do GitHub (tag "fila").

Cada Short da fila = dois anexos: <id>.mp4 (o vídeo) e <id>.json (texto, horário e o que já foi postado).
O id é AAAAMMDD-HHMM-N (horário de Brasília + número do vídeo na pasta do dia).
Anexo de release não entra no histórico do git: o repositório não incha com os vídeos.
O .json é sempre enviado depois do .mp4, então item sem .json ainda está chegando.
Usado pelo PC (sincronizar a pasta "Postar DD-MM") e pelo GitHub Actions (postar no horário).
"""
import json
import time
from pathlib import Path

import requests

API = "https://api.github.com"
TAG = "fila"


class Fila:
    def __init__(self, repo, token):
        self.repo = repo
        self.s = requests.Session()
        self.s.headers.update({"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                               "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "robo-tioban"})
        self._rel = None

    # ---- base -------------------------------------------------------------------------------------------
    def _req(self, metodo, url, ok=(200, 201, 204), **kw):
        kw.setdefault("timeout", 120)
        for tentativa in range(4):
            try:
                r = self.s.request(metodo, url, **kw)
            except requests.RequestException:
                if tentativa == 3:
                    raise
                time.sleep(5 * (tentativa + 1))
                continue
            if r.status_code in ok:
                return r
            if r.status_code >= 500 and tentativa < 3:
                time.sleep(5 * (tentativa + 1))
                continue
            raise RuntimeError(f"GitHub {metodo} {url}: {r.status_code} {r.text[:300]}")

    def release(self):
        if self._rel is None:
            r = self.s.get(f"{API}/repos/{self.repo}/releases/tags/{TAG}", timeout=60)
            if r.status_code == 404:
                r = self._req("POST", f"{API}/repos/{self.repo}/releases", json={
                    "tag_name": TAG, "name": "Fila de postagem",
                    "body": "Vídeos aprovados esperando o horário. O robô apaga cada um depois de postar.",
                    "prerelease": True})
            elif r.status_code != 200:
                raise RuntimeError(f"GitHub release: {r.status_code} {r.text[:300]}")
            self._rel = r.json()
        return self._rel

    def anexos(self):
        """{nome: anexo} só dos anexos que terminaram de subir; os quebrados (upload interrompido) são apagados."""
        rid = self.release()["id"]
        out, pagina = {}, 1
        while True:
            lote = self._req("GET", f"{API}/repos/{self.repo}/releases/{rid}/assets",
                             params={"per_page": 100, "page": pagina}).json()
            for a in lote:
                if a.get("state") == "uploaded":
                    out[a["name"]] = a
                else:
                    self.apagar(a)
            if len(lote) < 100:
                return out
            pagina += 1

    def itens(self):
        """{id: {"mp4": anexo|None, "json": anexo|None}}"""
        out = {}
        for nome, a in self.anexos().items():
            p = Path(nome)
            if p.suffix in (".mp4", ".json"):
                out.setdefault(p.stem, {"mp4": None, "json": None})[p.suffix[1:]] = a
        return out

    def ler_json(self, anexo):
        r = self._req("GET", anexo["url"], headers={"Accept": "application/octet-stream"})
        return json.loads(r.content.decode("utf-8"))

    def baixar(self, anexo, destino):
        destino = Path(destino)
        destino.parent.mkdir(parents=True, exist_ok=True)
        with self._req("GET", anexo["url"], headers={"Accept": "application/octet-stream"}, stream=True,
                       timeout=600) as r, open(destino, "wb") as f:
            for bloco in r.iter_content(1 << 20):
                f.write(bloco)
        return destino

    def enviar(self, nome, dados, tipo):
        """dados: bytes ou caminho de arquivo."""
        url = self.release()["upload_url"].split("{")[0]
        if isinstance(dados, (str, Path)):
            with open(dados, "rb") as f:
                return self._req("POST", url, params={"name": nome}, headers={"Content-Type": tipo}, data=f,
                                 timeout=1800).json()
        return self._req("POST", url, params={"name": nome}, headers={"Content-Type": tipo}, data=dados).json()

    def apagar(self, anexo):
        self._req("DELETE", f"{API}/repos/{self.repo}/releases/assets/{anexo['id']}", ok=(204, 404))

    # ---- itens da fila ---------------------------------------------------------------------------------
    def gravar_json(self, iid, dados, antigo=None):
        corpo = json.dumps(dados, ensure_ascii=False, indent=1).encode("utf-8")
        if antigo:
            self.apagar(antigo)
        return self.enviar(f"{iid}.json", corpo, "application/json")

    def tirar(self, item):
        for a in (item.get("json"), item.get("mp4")):
            if a:
                self.apagar(a)

    # ---- arquivos do repositório (config.json, postados.json) -----------------------------------------
    def arquivo(self, caminho, padrao=None):
        r = self.s.get(f"{API}/repos/{self.repo}/contents/{caminho}", timeout=60,
                       headers={"Accept": "application/vnd.github.raw+json"})
        if r.status_code == 404:
            return padrao
        if r.status_code != 200:
            raise RuntimeError(f"GitHub {caminho}: {r.status_code} {r.text[:200]}")
        return json.loads(r.content.decode("utf-8"))

    def gravar_arquivo(self, caminho, dados, mensagem):
        r = self.s.get(f"{API}/repos/{self.repo}/contents/{caminho}", timeout=60)
        sha = r.json().get("sha") if r.status_code == 200 else None
        import base64
        corpo = json.dumps(dados, ensure_ascii=False, indent=1) + "\n"
        self._req("PUT", f"{API}/repos/{self.repo}/contents/{caminho}", json={
            "message": mensagem, "content": base64.b64encode(corpo.encode("utf-8")).decode(),
            **({"sha": sha} if sha else {})})
