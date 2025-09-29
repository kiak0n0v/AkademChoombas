from typing import Annotated
from fastapi import FastAPI, Header
from pydantic import BaseModel
import json
import time
import requests
import base64

class FusionBrainAPI:

    def __init__(self, url, api_key, secret_key):
        self.URL = url
        self.AUTH_HEADERS = {
            'X-Key': f'Key {api_key}',
            'X-Secret': f'Secret {secret_key}',
        }

    def get_pipeline(self):
        response = requests.get(self.URL + 'key/api/v1/pipelines', headers=self.AUTH_HEADERS)
        data = response.json()
        print(data, type(data))
        if isinstance(data, list):
            return data[0]['id']
        else:
            return None
        #return None

    def generate(self, prompt, pipeline_id, images=1, width=340, height=390):
        params = {
            "type": "GENERATE",
            "numImages": images,
            "width": width,
            "height": height,
            "generateParams": {
                "query": "{prompt}"
            }
        }

        data = {
            'pipeline_id': (None, pipeline_id),
            'params': (None, json.dumps(params), 'application/json')
        }
        response = requests.post(self.URL + 'key/api/v1/pipeline/run', headers=self.AUTH_HEADERS, files=data)
        data = response.json()
        return data['uuid']

    def check_generation(self, request_id, attempts=10, delay=10):
        while attempts > 0:
            response = requests.get(self.URL + 'key/api/v1/pipeline/status/' + request_id, headers=self.AUTH_HEADERS)
            data = response.json()
            if data['status'] == 'DONE':
                return data['result']['files']

            attempts -= 1
            time.sleep(delay)


app = FastAPI()

class GenerateRequest(BaseModel):
    prompt: str

@app.post("/generate/")
async def generate_image(
    body: GenerateRequest,
    x_key: Annotated[str | None, Header(alias="X-Key")] = None,
    x_secret: Annotated[str | None, Header(alias="X-Secret")] = None,
):
    if body.prompt and x_key and x_secret:
        api = FusionBrainAPI('https://api-key.fusionbrain.ai/', x_key, x_secret)
        pipeline_id = api.get_pipeline()
        if pipeline_id:
            f_prompt = f'Описание отца: Высокий, статный мужчина, в лице которого выгравирована мудрость. Очень опрятный, с аккуратно уложенной, слегка поседевшей шевелюрой и ровной, ухоженной кожей; черты лица ясные и сдержанные, подбородок уверенный, скулы гармоничные. Глаза внимательные и глубокие, с тихой проницательностью; редкая тёплая улыбка, не кричащая, но ободряющая. Голос спокойный и глубокий, речь размеренная, слова точные. Характер уравновешенный: терпение, выдержка, ответственность, бескорыстная забота, сдержанная доброжелательность. Внутреннее достоинство, моральная устойчивость, умение слушать, наставничество и постоянное стремление к пониманию — опора для семьи и окружения. Описание сына: Низкий по сравнению с отцом, но стройный и подвижный молодой человек; лицо живое, с подчеркивающейся любознательностью мимикой и тонкими, выразительными чертами. Волосы густые, тёмные или с натуральной мелировкой, немного небрежные, кожа свежая, с лёгким румянцем любопытства; глаза яркие, острые, с постоянным блеском интереса, взгляд быстро считывающий детали. Улыбка быстрая и открытая, легко меняющаяся в зависимости от разговора; голос энергичный, интонации живые, речь порой быстрая, полная вопросов и точных замечаний. Характер — подвижный, пытливый, искренне внимательный: стремление узнать больше всех сочетается с умением внимательно слушать и искренне интересоваться чужими мыслями. Ум гибкий и любознательный, склонность к анализу и креативному мышлению; интуиция сильна, память — на отдельные факты и связи. Эмоциональная открытость и эмпатия делают его понятным людям; в поведении присутствует некоторая нетерпеливость и импульсивность, но она смягчается искренней доброжелательностью и готовностью меняться. Внутренне тянется к знаниям и опыту, постоянная устремлённость к новым идеям и диалогу — его естественная сила и привлекающая особенность. Основное описание{body.prompt}'
            uuid = api.generate(body.prompt, pipeline_id)
            return {'uuid': uuid}
        else:
            return {'error': 'Unauthorized'}
    else:
        return {'error': 'One of elements is not defined'}

@app.get("/background/")
async def background_image():
    binary_data = base64.b64encode(open("background.png", "rb").read())
    return {'data': binary_data.decode("utf-8")}
