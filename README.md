# Tioban – postagem dos Shorts

Robô que posta os Shorts do canal Tioban (notícias de GTA) no Instagram, no Facebook e no YouTube, cada um no seu horário.

- O PC do Adriano manda para a fila (anexos do release `fila`) só o que sobrou aprovado na pasta `Postar DD-MM`.
- O GitHub Actions (`.github/workflows/postar.yml`) roda a cada 20 minutos e posta o que chegou no horário.
- `config.json`: liga/desliga cada rede e pausa tudo. `postados.json`: registro do que foi postado, com os links.
