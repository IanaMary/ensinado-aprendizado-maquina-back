from app.database import colecao_usuario

async def find_user_by_email(email: str):
  return await colecao_usuario.find_one({"email": email})

async def insert_user(user_dict: dict):
  result = await colecao_usuario.insert_one(user_dict)
  user_dict["_id"] = str(result.inserted_id)
  return user_dict
