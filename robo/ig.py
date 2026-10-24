# -*- coding: utf-8 -*-
"""Reels no Instagram do Tioban (API com login do Instagram). O Instagram baixa o vídeo de um link público:
o robô publica o vídeo no GitHub Pages logo antes e passa o link."""
import os
import time

import requests

API = "https://graph.instagram.com"


def _token():
    return os.environ["IG_TOKEN"], os.environ["IG_USER_ID"]


def _get(caminho, **params):
    tok, _ = _token()
    r = requests.get(f"{API}/{caminho}", params={**params, "access_token": tok}, timeout=60).json()
    if "error" in r:
        raise RuntimeError(f"Instagram {caminho}: {r['error'].get('message')}")
    return r


def _post(caminho, data):
    tok, _ = _token()
    r = requests.post(f"{API}/{caminho}", params={"access_token": tok}, data=data, timeout=120).json()
    if "error" in r:
        raise RuntimeError(f"Instagram {caminho}: {r['error'].get('message')}")
    return r


def publicar(video_url, legenda):
    """Devolve (id, link)."""
    _, uid = _token()
    cont = _post(f"{uid}/media", {"media_type": "REELS", "video_url": video_url, "caption": legenda[:2200],
                                  "share_to_feed": "true", "thumb_offset": "1500"})["id"]
    for _ in range(90):
        time.sleep(10)
        st = _get(cont, fields="status_code,status")
        if st.get("status_code") == "FINISHED":
            mid = _post(f"{uid}/media_publish", {"creation_id": cont})["id"]
            try:
                link = _get(mid, fields="permalink").get("permalink")
            except Exception:
                link = None
            return mid, link or "https://www.instagram.com/"
        if st.get("status_code") in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Instagram recusou o vídeo: {st}")
    raise RuntimeError("Instagram demorou demais para processar o vídeo")
