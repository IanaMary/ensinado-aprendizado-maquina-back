"""Estimador de Regressão Polinomial compatível com o trainer genérico.

A Regressão Polinomial não é um estimador único do sklearn: é a combinação de
``PolynomialFeatures`` (expande os atributos em termos polinomiais) com uma
``LinearRegression``. Para encaixar no padrão de ``treinar_modelo_generico`` —
que instancia uma única classe com ``**hiperparametros`` e usa ``get_params()``,
``fit``/``predict`` e ``is_regressor`` — embrulhamos o pipeline num estimador
sklearn-compatível com ``__init__`` explícito (necessário para a inspeção de
assinatura feita pelo trainer e para o ``get_params`` do BaseEstimator).
"""

from sklearn.base import BaseEstimator, RegressorMixin
from sklearn.linear_model import LinearRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import PolynomialFeatures


class RegressaoPolinomial(RegressorMixin, BaseEstimator):
    def __init__(
        self,
        degree: int = 2,
        include_bias: bool = True,
        interaction_only: bool = False,
        fit_intercept: bool = True,
        positive: bool = False,
    ):
        self.degree = degree
        self.include_bias = include_bias
        self.interaction_only = interaction_only
        self.fit_intercept = fit_intercept
        self.positive = positive

    def fit(self, X, y):
        self.pipeline_ = make_pipeline(
            PolynomialFeatures(
                degree=self.degree,
                include_bias=self.include_bias,
                interaction_only=self.interaction_only,
            ),
            LinearRegression(fit_intercept=self.fit_intercept, positive=self.positive),
        )
        self.pipeline_.fit(X, y)
        return self

    def predict(self, X):
        return self.pipeline_.predict(X)
