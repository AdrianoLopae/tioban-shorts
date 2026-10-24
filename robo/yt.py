# -*- coding: utf-8 -*-
"""Shorts no canal do YouTube do Tioban (YouTube Data API, envio retomável).

Atenção: enquanto o Google não aprovar a auditoria do projeto, todo vídeo enviado pela API fica PRIVADO
travado. Por isso o YouTube começa desligado no config.json (redes.youtube = false)."""
import json
import os
from pathlib import Path

import requests


def _acesso():
    r = requests.post("https://oauth2.googleapis.com/token", data={
        "client_id": os.environ["YT_CLIENT_ID"], "client_secret": os.environ["YT_CLIENT_SECRET"],
        "refresh_token": os.environ["YT_REFRESH_TOKEN"], "grant_type": "refresh_token"}, timeout=60).json()
    if "access_token" not in r:
        raise RuntimeError(f"YouTube: login recusado ({r.get('error')}: {r.get('error_description')})")
    return r["access_token"]


def publicar(caminho, titulo, descricao, tags, privacidade="public", conteudo_alterado=False):
    """Devolve (id, link)."""
    titulo = titulo.replace("<", "").replace(">", "")[:100]
    tags_ok, total = [], 0
    for t in tags:
        t = t.lstrip("#")
        if t and total + len(t) + 1 <= 450:
            tags_ok.append(t)
            total += len(t) + 1
    meta = {"snippet": {"title": titulo, "description": descricao.replace("<", "").replace(">", "")[:4900],
                        "tags": tags_ok, "categoryId": "20", "defaultLanguage": "pt-BR",
                        "defaultAudioLanguage": "pt-BR"},
            "status": {"privacyStatus": privacidade, "selfDeclaredMadeForKids": False,
                       "containsSyntheticMedia": bool(conteudo_alterado)}}
    h = {"Authorization": f"Bearer {_acesso()}"}
    caminho = Path(caminho)
    ini = requests.post("https://www.googleapis.com/upload/youtube/v3/videos",
                        params={"uploadType": "resumable", "part": "snippet,status"},
                        headers={**h, "Content-Type": "application/json; charset=UTF-8",
                                 "X-Upload-Content-Type": "video/mp4",
                                 "X-Upload-Content-Length": str(caminho.stat().st_size)},
                        data=json.dumps(meta), timeout=60)
    if ini.status_code >= 400:
        raise RuntimeError(f"YouTube: {ini.status_code} {ini.text[:400]}")
    with open(caminho, "rb") as f:
        r = requests.put(ini.headers["Location"], headers={**h, "Content-Type": "video/mp4"}, data=f, timeout=1800)
    if r.status_code >= 400:
        raise RuntimeError(f"YouTube: {r.status_code} {r.text[:400]}")
    vid = r.json()["id"]
    return vid, f"https://youtube.com/shorts/{vid}"
