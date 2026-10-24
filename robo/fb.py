# -*- coding: utf-8 -*-
"""Reels na página do Facebook do Tioban (Graph API). O vídeo sobe direto do arquivo, sem precisar de link."""
import os
import time
from pathlib import Path

import requests

G = "https://graph.facebook.com/v24.0"


def _ok(r):
    try:
        d = r.json()
    except ValueError:
        d = {"texto": r.text[:300]}
    if r.status_code >= 400 or (isinstance(d, dict) and "error" in d):
        raise RuntimeError(f"Facebook: {d.get('error', d) if isinstance(d, dict) else d}")
    return d


def publicar(caminho, descricao):
    """Devolve (id, link)."""
    tok, pagina = os.environ["FB_PAGE_TOKEN"], os.environ["FB_PAGE_ID"]
    caminho = Path(caminho)
    ini = _ok(requests.post(f"{G}/{pagina}/video_reels", params={"upload_phase": "start", "access_token": tok},
                            timeout=60))
    vid = ini["video_id"]
    with open(caminho, "rb") as f:
        _ok(requests.post(ini.get("upload_url") or f"https://rupload.facebook.com/video-upload/v24.0/{vid}",
                          headers={"Authorization": f"OAuth {tok}", "offset": "0",
                                   "file_size": str(caminho.stat().st_size)}, data=f, timeout=1800))
    _ok(requests.post(f"{G}/{pagina}/video_reels", params={
        "upload_phase": "finish", "video_id": vid, "video_state": "PUBLISHED", "description": descricao,
        "access_token": tok}, timeout=120))
    link = f"https://www.facebook.com/reel/{vid}"
    for _ in range(60):
        time.sleep(10)
        s = _ok(requests.get(f"{G}/{vid}", params={"fields": "status", "access_token": tok}, timeout=60)).get(
            "status", {})
        if s.get("video_status") == "error" or s.get("processing_phase", {}).get("status") == "error":
            raise RuntimeError(f"Facebook recusou o vídeo: {s}")
        if s.get("video_status") == "ready" and s.get("publishing_phase", {}).get("status") in (None, "complete"):
            return vid, link
        if s.get("publishing_phase", {}).get("status") == "complete":
            return vid, link
    return vid, link  # já foi enviado para publicar; o Facebook termina de processar sozinho
