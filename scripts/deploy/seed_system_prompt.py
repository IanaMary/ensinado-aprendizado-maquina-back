#!/usr/bin/env python
"""Semeia a instrução de sistema do chat no MongoDB: db.configuracoes_tutor,
doc {chave: 'system_prompt'}.

Em regime normal você NÃO precisa rodar isto: o backend semeia no boot
(`app/main.py:semear_instrucao_do_tutor`), e reiniciar o serviço é o que todo caminho de deploy
tem em comum. Este CLI existe para (a) rodar o seed sem reiniciar, (b) `--forcar`, que é a única
maneira de impor o padrão do repo por cima de uma edição do admin, e (c) paridade com o
`deploy.sh`, onde o resultado aparece no log do deploy.

A decisão de escrever ou preservar mora em `app/conteudo/system_prompt_seed.py` (dez estados,
testados lá).

Uso (na VM, dentro do backend, com o .env carregado):
    venv/bin/python -m scripts.deploy.seed_system_prompt [--forcar]
"""
import asyncio
import os
import sys

_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)


async def _main(forcar: bool) -> None:
    from app.conteudo.system_prompt_seed import resumo_legivel, semear_system_prompt
    from app.database import configuracoes_tutor

    try:
        await configuracoes_tutor.create_index("chave", unique=True)
    except Exception as e:  # duplicata legada não pode impedir o seed
        print(f"  aviso: índice único em `chave` não criado ({type(e).__name__})")

    resultado = await semear_system_prompt(forcar=forcar)
    print(resumo_legivel(resultado))


if __name__ == "__main__":
    asyncio.run(_main("--forcar" in sys.argv[1:]))
