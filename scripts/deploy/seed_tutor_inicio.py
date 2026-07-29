#!/usr/bin/env python
"""Semeia as boas-vindas do tutor (Área de Trabalho): db.tutor, doc {pipe: 'inicio'},
campo texto_pipe.

Idempotente e CONSERVADOR: preserva o texto que o admin gravar em conf-tutor → Início, e propaga o
padrão novo para quem nunca editou. A decisão vive em `app/conteudo/texto_versionado.py` (dez
estados testados lá); o placeholder de uma frase do `seed-mongodb.sh` está registrado como texto
legado NOSSO, então é substituído em vez de ser confundido com edição do admin.

Antes a comparação era `==` de string bruta, e por isso dois caracteres de espaço a mais no banco
faziam o script relatar "editado pelo admin" e nunca mais atualizar nada — era o estado de produção.

O backend também semeia no boot (`app/main.py`); este CLI existe para rodar sem reiniciar, para o
`--forcar` e para o resultado aparecer no log do deploy.

Uso (na VM, dentro do backend, com o .env carregado):
    venv/bin/python -m scripts.deploy.seed_tutor_inicio [--forcar]
"""
import asyncio
import os
import sys

_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)


async def _main(forcar: bool) -> None:
    from app.conteudo.textos_do_tutor import ALVO_INICIO, resumo_legivel, semear_texto_do_tutor

    resultado = await semear_texto_do_tutor(ALVO_INICIO, forcar=forcar)
    print(resumo_legivel(resultado, ALVO_INICIO))


if __name__ == "__main__":
    asyncio.run(_main("--forcar" in sys.argv[1:]))
