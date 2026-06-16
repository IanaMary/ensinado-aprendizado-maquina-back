"""Processo filho do sandbox. Lê spec+dados, aplica limites, faz fit, grava artefatos.

Invocado como `python -m app.sandbox.child <workdir>` pelo `runner.py`. Não
acessa Mongo nem rede — toda comunicação com o pai é via arquivos no workdir.
"""
from __future__ import annotations

import importlib
import json
import sys
import traceback
from pathlib import Path


def _apply_limits(max_ram_mb: int, max_cpu_sec: int) -> None:
    """Aplica limites de recurso onde o SO permite.

    macOS frequentemente rejeita RLIMIT_AS ("current limit exceeds maximum"),
    então tratamos cada limite isoladamente — em produção Linux ambos passam.
    """
    import resource

    ram_bytes = max_ram_mb * 1024 * 1024
    for nome, limite, valor in (
        ("RLIMIT_AS", resource.RLIMIT_AS, ram_bytes),
        ("RLIMIT_CPU", resource.RLIMIT_CPU, max_cpu_sec),
    ):
        try:
            resource.setrlimit(limite, (valor, valor))
        except (ValueError, OSError) as e:
            # Não derruba o run — apenas perde a defesa em profundidade desse limite.
            print(f"[sandbox] aviso: setrlimit({nome}) ignorado: {e}", flush=True)


def _write_result(work: Path, payload: dict) -> None:
    (work / "result.json").write_text(json.dumps(payload, default=str))


def _instanciar(modulo: str, classe: str, hiper: dict):
    """Importa e instancia uma classe sklearn (modulo.classe) com kwargs."""
    mod = importlib.import_module(modulo)
    cls = getattr(mod, classe)
    return cls(**(hiper or {}))


def _montar_modelo(spec: dict):
    """Monta o estimador final. Com pré-processamento, devolve um sklearn Pipeline
    (transformers + estimador) para que o modelo serializado já contenha as
    transformações ajustadas — assim `predict()` aplica tudo sobre X cru.

    Cada etapa com colunas específicas vira um ColumnTransformer (remainder
    passthrough); sem colunas, o transformer atua sobre todas as features.
    """
    module_path, _, class_name = spec["class_path"].rpartition(".")
    if not module_path or not class_name:
        raise ValueError(f"class_path inválido: {spec['class_path']!r}")
    estimador = _instanciar(module_path, class_name, spec.get("hiperparametros", {}))

    etapas = spec.get("pre_processamento") or []
    if not etapas:
        return estimador

    from sklearn.compose import ColumnTransformer
    from sklearn.pipeline import Pipeline

    steps = []
    for i, etapa in enumerate(etapas):
        transformer = _instanciar(
            etapa["modulo"], etapa["classe"], etapa.get("hiperparametros", {})
        )
        nome = f"prep_{i}_{etapa.get('valor', 'transformer')}"
        colunas = etapa.get("colunas") or []
        if colunas:
            ct = ColumnTransformer(
                transformers=[(nome, transformer, colunas)],
                remainder="passthrough",
                verbose_feature_names_out=False,
            )
            steps.append((nome, ct))
        else:
            steps.append((nome, transformer))
    steps.append(("modelo", estimador))

    pipe = Pipeline(steps)
    # Mantém DataFrames (com nomes de coluna) entre etapas — necessário quando uma
    # etapa posterior referencia colunas por nome.
    try:
        pipe.set_output(transform="pandas")
    except Exception:
        pass
    return pipe


def _estimador_final(modelo):
    """Retorna o último estimador, desembrulhando um Pipeline se necessário."""
    try:
        from sklearn.pipeline import Pipeline

        if isinstance(modelo, Pipeline):
            return modelo.steps[-1][1]
    except Exception:
        pass
    return modelo


def main(workdir: str) -> int:
    work = Path(workdir)
    try:
        spec = json.loads((work / "spec.json").read_text())
    except Exception as e:
        # Sem spec não há como reportar via result.json estruturado;
        # mesmo assim tentamos.
        _write_result(
            work,
            {"ok": False, "error_type": "spec", "error": f"falha ao ler spec: {e}"},
        )
        return 1

    try:
        _apply_limits(int(spec["max_ram_mb"]), int(spec["max_cpu_sec"]))
    except Exception as e:
        _write_result(
            work,
            {"ok": False, "error_type": "limits", "error": f"setrlimit falhou: {e}"},
        )
        return 1

    try:
        import joblib
        import pandas as pd

        X_train = pd.read_pickle(work / "X_train.pkl")
        y_train = None
        if not spec["is_clustering"]:
            y_train = pd.read_pickle(work / "y_train.pkl")

        modelo = _montar_modelo(spec)
        if spec["is_clustering"]:
            modelo.fit(X_train)
        else:
            modelo.fit(X_train, y_train)

        joblib.dump(modelo, work / "model.joblib")

        final = _estimador_final(modelo)
        classes: list = []
        if hasattr(final, "classes_"):
            classes = [str(c) for c in final.classes_]
        elif hasattr(final, "labels_"):
            classes = [str(c) for c in sorted(set(final.labels_))]

        try:
            params = json.loads(json.dumps(modelo.get_params(), default=str))
        except Exception:
            params = {k: str(v) for k, v in modelo.get_params().items()}

        _write_result(
            work,
            {
                "ok": True,
                "classes": classes,
                "params": params,
                "model_repr": str(modelo),
            },
        )
        return 0

    except MemoryError:
        _write_result(
            work,
            {
                "ok": False,
                "error_type": "memory",
                "error": "Limite de memória excedido durante o treinamento.",
            },
        )
        return 2
    except Exception as e:
        _write_result(
            work,
            {
                "ok": False,
                "error_type": "exception",
                "error": f"{type(e).__name__}: {e}",
                "traceback": traceback.format_exc(),
            },
        )
        return 1


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("uso: python -m app.sandbox.child <workdir>", file=sys.stderr)
        sys.exit(64)
    sys.exit(main(sys.argv[1]))
