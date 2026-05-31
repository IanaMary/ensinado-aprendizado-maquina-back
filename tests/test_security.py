import pytest
from app.security import get_senha_hash, verificar_senha, SECRET_KEY, ALGORITHM
import jwt


class TestSenhaHash:
    def test_hash_e_verificacao(self):
        senha = "minha_senha_123"
        hashed = get_senha_hash(senha)
        assert hashed != senha
        assert verificar_senha(senha, hashed) is True

    def test_senha_incorreta(self):
        hashed = get_senha_hash("senha_correta")
        assert verificar_senha("senha_errada", hashed) is False

    def test_hash_diferente_para_mesma_senha(self):
        senha = "teste"
        h1 = get_senha_hash(senha)
        h2 = get_senha_hash(senha)
        assert h1 != h2


class TestJWT:
    def test_decodificar_token_valido(self):
        token = jwt.encode({"sub": "user@test.com"}, SECRET_KEY, algorithm=ALGORITHM)
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        assert payload["sub"] == "user@test.com"

    def test_token_invalido(self):
        with pytest.raises(jwt.exceptions.DecodeError):
            jwt.decode("token-invalido", SECRET_KEY, algorithms=[ALGORITHM])

    def test_token_com_secret_errado(self):
        token = jwt.encode({"sub": "user@test.com"}, "wrong-secret", algorithm=ALGORITHM)
        with pytest.raises(jwt.exceptions.DecodeError):
            jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
