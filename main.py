import base64
import binascii
import io
import json
import mimetypes
import os
import tempfile
import time
import uuid
import http.client
from urllib.parse import urlparse, unquote
from typing import Annotated, List, Optional

from fastapi import FastAPI, Header, Body, Request
from pydantic import BaseModel
import uvicorn
import requests



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
        #print(data, type(data))
        if isinstance(data, list):
            return data[0]['id']
        else:
            return None
        #return None

    def generate(self, prompt, pipeline_id, images=1, width=512, height=587):
        params = {
            "type": "GENERATE",
            "numImages": images,
            "width": width,
            "height": height,
            "style": "COMICS",
            "generateParams": {
                "query": prompt
            }
        }

        data = {
            'pipeline_id': (None, pipeline_id),
            'params': (None, json.dumps(params), 'application/json')
        }
        response = requests.post(self.URL + 'key/api/v1/pipeline/run', headers=self.AUTH_HEADERS, files=data)
        data = response.json()
        print(data)
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
        try:
            api = FusionBrainAPI('https://api-key.fusionbrain.ai/', x_key, x_secret)
            pipeline_id = api.get_pipeline()
            if pipeline_id:
                f_prompt = f'Описание отца: мужчина, 55 лет, рост 190 см, сдержанные черты лица, опрятный, слегка поседевший, ясные бледно-голубые глаза, овальная форма лица, немного острый нос. Описание сына: парень, 14 лет, рост 170 см, стройный, опрятный, яркий взгляд, светло-голубые глаза, заинтересованность, овальная форма лица, стремеление к знаниям. Общая стилистика: манга 2010-х годов, чернобелая картинка, полностью 2D, штриховка - для передачи динамики. Основное описание: {body.prompt}'
                uuid = api.generate(f_prompt, pipeline_id)
                return {'uuid': uuid}
            else:
                return {'error': 'Unauthorized'}
        except Exception as err:
            print(err)
            return {'error': str(err)}
    else:
        return {'error': 'One of elements is not defined'}

@app.post("/background/")
async def background_image():
    binary_data = base64.b64encode(open("background.png", "rb").read())
    return {'data': binary_data.decode("utf-8")}

#openai.api_key = os.getenv("OPENAI_API_KEY")
openai.api_key = "secret-key"
# необязательно: можно переопределить модель через OPENAI_MODEL
DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4")


async def _extract_text_from_pdf_bytes(pdf_bytes: bytes) -> str:
    """Простейшая извлекающая функция — предполагает текстовый PDF."""
    reader = PdfReader(io.BytesIO(pdf_bytes))
    pages = []
    for p in reader.pages:
        text = p.extract_text()
        if text:
            pages.append(text)
    return "\n\n".join(pages)


def _split_into_chunks(text: str, max_chars: int = 16000):
    """Простейший блочный разрез по символам (не по токенам)."""
    for i in range(0, len(text), max_chars):
        yield text[i : i + max_chars]


def _call_gpt_clean_text(text_chunk: str) -> str:
    """Посылаем chunk в ChatGPT для "очистки" — возвращаем чистый текст."""
    system_msg = "Ты помощник, который получает текст из PDF и возвращает только чистый читаемый текст без технических пометок."
    user_msg = (
        "Ниже — фрагмент текста из PDF. Верни только чистый связный текст. "
        "Не добавляй заголовки, списки метаданных, фразы типа 'Output:' или какие-либо пояснения. "
        "Если PDF содержал номера страниц или колонтитулы — постарайся убрать их, объедини абзацы корректно.\n\n"
        "Фрагмент:\n\n" + text_chunk
    )

    resp = openai.ChatCompletion.create(
        model=DEFAULT_MODEL,
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
        temperature=0.0,
        # max_tokens оставляем по-умолчанию / достаточно большим — если нужно, выставьте больше
    )
    return resp["choices"][0]["message"]["content"].strip()


@app.post("/pdf_to_text/")
async def pdf_to_text(request: Request):
    """
    Поддерживает:
     - raw binary POST (Content-Type: application/pdf или application/octet-stream)
     - multipart/form-data с файлом
    Возвращает: plain text (text/plain) — готовый текст без лишних пометок.
    """
    content_type = request.headers.get("content-type", "")

    # 1) multipart form (файл в форме)
    pdf_bytes = b""
    if "multipart/form-data" in content_type:
        form = await request.form()
        # ищем первый файл в форме
        file_obj = None
        for v in form.values():
            if isinstance(v, UploadFile):
                file_obj = v
                break
        if file_obj is None:
            return Response(content="No file provided", status_code=400, media_type="text/plain")
        pdf_bytes = await file_obj.read()
    else:
        # 2) raw body (n8n при Binary file часто шлёт raw body)
        pdf_bytes = await request.body()
        if not pdf_bytes:
            return Response(content="Empty body", status_code=400, media_type="text/plain")

    # извлекаем текст (простая логика)
    raw_text = await _extract_text_from_pdf_bytes(pdf_bytes)

    # если PDF пустой / ничего не извлечено — возвращаем пустой текст
    if not raw_text.strip():
        return Response(content="", media_type="text/plain")

    # разбиваем на чанки и прогоняем через модель, объединяем результаты
    pieces = []
    for chunk in _split_into_chunks(raw_text, max_chars=16000):
        clean = _call_gpt_clean_text(chunk)
        pieces.append(clean)

    final_text = "\n\n".join(pieces).strip()
    return Response(content=final_text, media_type="text/plain")
