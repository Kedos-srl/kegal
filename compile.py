import logging as log

import uvicorn
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError, ValidationException
from starlette.responses import JSONResponse

from graph_compiler import GraphCompiler, GraphData, LlmResponse
from log.ke_logging import custom_file_handler

custom_file_handler()

app = FastAPI()

logging = log.getLogger("ke_log")
logging.info("KE LLM is Run!")


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, e: ValidationException):
    logging.debug(f"Info validation - request {request}")
    logging.debug(f"Info validation - request {e}")

    return JSONResponse(content=e.errors(), status_code=422)


@app.get("/")
async def root():
    return {"message": "ke_llm"}


@app.post("/compile")
async def compile(graph_data_: GraphData) -> list[LlmResponse]:
    try:
        compiler = GraphCompiler(graph_data_)
        outputs: list[LlmResponse] = compiler()
        return outputs
    except Exception as e:
        logging.error(f"Error compile(): {e}")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8090)
