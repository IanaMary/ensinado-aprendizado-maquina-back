from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional
import logging
import pandas as pd

from app.models.dataset_config import (
    DatasetType, get_all_datasets, get_dataset_config
)
from app.models.dataset_loaders import (
    DatasetNaoConfigurado, carregar_com_rotulos, carregar_gerador, carregar_sklearn,
    carregar_uci,
    # Reexportado: o startup em app/main.py chama toy_datasets.prewarm_uci_cache.
    prewarm_uci_cache,
)
from app.coleta_dados.configuracao_treinamento import aviso_estratificacao, dividir_dataframe
from app.schemas.schemas import ReDivisaoColetaRequest
from app.utils.seed import seed_everything, get_seed, get_sklearn_random_state
from app.database import arquivos, configuracoes_treinamento
from app.security import exigir_admin_ou_professor, get_usuario_atual
from app.desafios.base_dados import perfil_do_dataset
from app.funcoes_genericas.funcoes_genericas import df_para_base64

logger = logging.getLogger("uvicorn")

router = APIRouter(prefix="/toy_datasets", tags=["Toy Datasets"])

# Proporção da divisão inicial de um dataset de exemplo. Vai na RESPOSTA porque a tela
# não tem como adivinhá-la: ela assumia 70/30 enquanto o treino rodava com 75/25, e o
# script exportado saía com a divisão errada — acurácia diferente da que o aluno viu.
TEST_SIZE_PADRAO = 0.25


@router.get("/")
async def listar_datasets(
    tipo: Optional[str] = Query(None, description="Filtrar por tipo: classificacao, regressao, agrupamento"),
    fonte: Optional[str] = Query(None, description="Filtrar por fonte: sklearn, uci")
):
    """Lista todos os datasets disponiveis com informacoes detalhadas."""
    datasets = get_all_datasets()
    
    result = []
    for ds in datasets.values():
        # Aplicar filtros
        if tipo and ds.tipo.value != tipo:
            continue
        if fonte and ds.fonte != fonte:
            continue
        result.append(ds.to_dict())
    
    return result


@router.get("/{dataset_name}/conteudo")
async def conteudo_dataset(dataset_name: str):
    """Bloco `conteudo` educacional do dataset para o card do tutor.

    Read-only: NÃO carrega o dataset nem escreve no banco (ao contrário de
    GET /toy_datasets/{name}).
    """
    ds = get_dataset_config(dataset_name)
    if ds is None:
        raise HTTPException(status_code=404, detail=f"Dataset '{dataset_name}' não encontrado")
    return ds.conteudo_card()


@router.get("/{dataset_name}/perfil-desafio")
async def perfil_desafio_dataset(
    dataset_name: str,
    _: dict = Depends(exigir_admin_ou_professor),
):
    """Perfil do dataset para criar um desafio de montagem: tarefa, textos do enunciado e as
    características da base lidas do dataframe (valores faltando, texto, escalas).

    Carrega o dataframe (por isso o gate de professor/admin), mas **não** escreve no banco.
    """
    perfil = perfil_do_dataset(dataset_name)
    if perfil is None:
        raise HTTPException(status_code=404, detail=f"Dataset '{dataset_name}' não encontrado")
    return perfil


@router.get("/{dataset_name}")
async def carregar_dataset(
    dataset_name: str,
    seed: Optional[int] = Query(None, description="Seed para reprodutibilidade (opcional)"),
    n_amostras: Optional[int] = Query(None, ge=10, le=5000, description="(geradores) número de amostras"),
    n_features: Optional[int] = Query(None, ge=1, le=50, description="(geradores) número de atributos"),
    ruido: Optional[float] = Query(None, ge=0.0, le=10.0, description="(geradores) nível de ruído"),
    n_classes: Optional[int] = Query(None, ge=2, le=10, description="(geradores) número de classes"),
    n_clusters: Optional[int] = Query(None, ge=2, le=10, description="(geradores) número de grupos"),
    current_user: dict = Depends(get_usuario_atual),
):
    """Carrega um dataset e retorna no formato esperado pelo frontend."""
    ds = get_dataset_config(dataset_name)
    if ds is None:
        raise HTTPException(status_code=404, detail=f"Dataset '{dataset_name}' não encontrado")

    # Aplicar seed se fornecido
    if seed is not None:
        seed_everything(seed)

    try:
        # Despacho por `fonte` vive SÓ no `carregar_com_rotulos`. Aqui havia uma segunda lista de
        # fontes, e quando o Titanic virou `openml` ela não foi atualizada: `df` ficava `None` e
        # este endpoint — o que a tela chama para abrir o dataset — devolvia 500, com o carregador
        # novo funcionando e os testes de unidade verdes.
        df, target_names = carregar_com_rotulos(
            dataset_name, ds,
            n_amostras=n_amostras, n_features=n_features, ruido=ruido,
            n_classes=n_classes, n_clusters=n_clusters,
        )

        if df is None:
            raise HTTPException(status_code=500, detail="Erro ao carregar dataset")
        
        # Substituir target numerico por labels de texto se disponivel
        # O target real no dataframe e sempre "target" para sklearn datasets
        target_col = "target" if "target" in df.columns else ds.target
        
        # Só em CLASSIFICAÇÃO: em regressão o `target_names` do sklearn é o nome da coluna, não
        # uma lista de rótulos. No california_housing (`target_names == ['MedHouseVal']`) o
        # `else str(x)` transformava a coluna contínua inteira em texto — a tela então deduzia
        # "Exploratório" para um dataset de regressão, e o script exportado (que usa o alvo
        # numérico) media outra coisa.
        e_classificacao_alvo = ds.tipo == DatasetType.CLASSIFICATION
        if target_names is not None and target_col in df.columns and e_classificacao_alvo:
            if df[target_col].dtype in ['int64', 'float64']:
                # Mapear inteiros para labels de texto
                df[target_col] = df[target_col].apply(lambda x: target_names[int(x)] if int(x) < len(target_names) else str(x))
        
        # Preparar dados
        colunas = list(df.columns)
        colunas_detalhes = []
        for col in colunas:
            tipo_col = "Número" if df[col].dtype in ['int64', 'float64'] else "Texto"
            colunas_detalhes.append({
                "nome_coluna": col,
                "tipo_coluna": tipo_col
            })

        # Dados para preview (limitar a 50 linhas)
        dados = df.head(50).to_dict(orient='records')

        # Informacoes do target
        tipo_target = None
        if target_col and target_col in df.columns:
            tipo_target = "Número" if df[target_col].dtype in ['int64', 'float64'] else "Texto"

        # Persistir no MongoDB para que o pipeline de treinamento encontre os IDs
        # - Salva o dataframe completo em 'arquivos' (content_treino_base64/content_teste_base64)
        # - Salva configuração inicial em 'configuracoes_treinamento'
        # Divisão REAL de treino/teste. Antes o treino recebia o dataframe inteiro e o teste
        # a cauda de 25% — o teste era um subconjunto do treino (vazamento) e, sem embaralhar,
        # a cauda de um dataset ordenado por classe (iris, wine) só tinha uma categoria.
        # Classificação estratifica por padrão; `dividir_dataframe` cai numa divisão simples
        # se alguma categoria tiver exemplos de menos.
        e_classificacao = ds.tipo == DatasetType.CLASSIFICATION
        df_treino, df_teste, estratificou = dividir_dataframe(
            df,
            ReDivisaoColetaRequest(test_size=TEST_SIZE_PADRAO, shuffle=True,
                                   stratify=e_classificacao, target=target_col),
        )
        content_completo_b64 = df_para_base64(df)
        content_treino_b64 = df_para_base64(df_treino)
        content_teste_b64 = df_para_base64(df_teste)

        atributos_iniciais = {c: True for c in colunas}
        if target_col and target_col in colunas:
            atributos_iniciais[target_col] = False

        doc_arquivo = {
            "arquivo_nome_treino": f"{ds.nome}.xlsx",
            "arquivo_nome_teste": f"{ds.nome}_teste.xlsx",
            # `content_completo_base64` é o que a redivisão relê ao mudar a proporção/alvo —
            # sem ele, redividir usaria o treino já dividido e o dataset encolheria a cada vez.
            "content_completo_base64": content_completo_b64,
            "content_treino_base64": content_treino_b64,
            "content_teste_base64": content_teste_b64,
            "fonte": "toy_dataset",
            "dataset_nome": ds.nome,
            "num_linhas_total": len(df),
            "num_linhas_treino": len(df_treino),
            "num_linhas_teste": len(df_teste),
            "num_colunas": len(colunas),
            "atributos": atributos_iniciais,
            "colunas_detalhes": colunas_detalhes,
            "usuario_id": str(current_user.get("_id", "")),
        }
        result_arquivo = await arquivos.insert_one(doc_arquivo)
        id_coleta = str(result_arquivo.inserted_id)

        doc_config = {
            "id_coleta": result_arquivo.inserted_id,
            "test_size": TEST_SIZE_PADRAO,
            "shuffle": True,
            "stratify": estratificou,
            "atributos": atributos_iniciais,
            "tipo_target": tipo_target,
            "target": target_col,
            "prever_categoria": ds.tipo == DatasetType.CLASSIFICATION,
            "dados_rotulados": target_col is not None,
            "fonte": "toy_dataset",
            "dataset_nome": ds.nome,
            "usuario_id": str(current_user.get("_id", "")),
        }
        result_config = await configuracoes_treinamento.insert_one(doc_config)
        id_configuracoes_treinamento = str(result_config.inserted_id)

        return {
            "id_coleta": id_coleta,
            "id_configuracoes_treinamento": id_configuracoes_treinamento,
            "id": ds.id,
            "nome_dataset": ds.nome,
            "fonte": ds.fonte,
            "colunas": colunas,
            "colunas_detalhes": colunas_detalhes,
            "dados": dados,
            "total_dados": len(df),
            "target": target_col,
            "tipo_target": tipo_target,
            "prever_categoria": ds.tipo == DatasetType.CLASSIFICATION,
            "dados_rotulados": target_col is not None,
            "stratify": estratificou,
            "test_size": TEST_SIZE_PADRAO,
            # Tamanhos REAIS dos dois conjuntos. Sem eles a tela exibia o dataset inteiro
            # como treino e "Teste: 0" — a divisão que o servidor fez ficava invisível.
            "num_linhas_treino": len(df_treino),
            "num_linhas_teste": len(df_teste),
            "aviso_estratificacao": aviso_estratificacao(e_classificacao, estratificou),
            "n_amostras": ds.n_amostras,
            "n_features": ds.n_features,
            "pre_split": ds.pre_split.value,
            "n_treino": ds.n_treino,
            "n_teste": ds.n_teste,
            "dificuldade": ds.dificuldade,
            "descricao_target": ds.descricao_target,
            "descricao_features": ds.descricao_features,
            "missao": ds.to_dict().get("missao"),
            "seed": get_seed()
        }
    
    except HTTPException:
        raise
    except DatasetNaoConfigurado as e:
        # Antes o próprio carregador levantava HTTPException(400); a exceção do módulo
        # extraído preserva esse status (o except genérico abaixo devolveria 500).
        raise HTTPException(status_code=400, detail=str(e))
    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"Biblioteca não instalada: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao carregar dataset: {str(e)}")
